#!/bin/bash
# g0245d v358 -- build pipeline, dual-line / machine-independent.
#
# Required environment:
#   V358_BASE   clean base dir (holds UniXNU-runtime/ and assets/)
#   V358_DEV    UniXNU-g0245d-ios checkout (scripts/linux/patch_v358.py)
#   V358_SOC    UniXNU-msm8996-common checkout (local module)
#   V358_OUT    output directory, e.g. $HOME/g0245d-auto/auto/v358
# Optional:
#   V358_ENV    env.sh to source before building (toolchain paths, etc.)
#   V358_FB     fastboot binary (only needed with V358_FLASH=1)
#   V358_SERIAL device serial (only needed with V358_FLASH=1)
#   V358_FLASH  set to 1 to wait for fastboot and flash; default build only
#
# Works on both bring-up lines:
#   - dev line:          patch_v358 STEP1-4 add alignment + v355 + v356 + v357 probes if missing (dev line)
#   - ubuntu line:       STEP1-4 detect already-applied probes and skip (ubuntu line)
#   - both:              STEP2 adds v355 ASID probes if missing, STEP3 adds
#                        the four v358 bisect probes
set -o pipefail
: "${V358_BASE:?V358_BASE is required}"
: "${V358_DEV:?V358_DEV is required}"
: "${V358_SOC:?V358_SOC is required}"
: "${V358_OUT:?V358_OUT is required}"

if [ -n "$V358_ENV" ]; then
  echo "=== sourcing $V358_ENV ==="
  source "$V358_ENV"
fi

export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V358_BASE/.tools/share/bison}"
export M4="${M4:-$V358_BASE/.tools/bin/m4}"

UX=$V358_BASE/UniXNU-runtime
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
W=$O/tree/.cache/xnu-work
mkdir -p "$V358_OUT"
cd "$UX" || exit 1

echo "=== STEP0 patch v358 (dual-line, idempotent) ==="
XNU_WORK=$W python3 "$V358_DEV/scripts/linux/patch_v358.py" || { echo "PATCH FAILED"; exit 1; }

echo "=== STEP1 build kernel ==="
./unixnu build kernel -D "$V358_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V358_SOC" >"$V358_OUT/kernel.log" 2>&1
RC=$?
echo "build rc=$RC"
if [ $RC -ne 0 ]; then
  echo "BUILD FAILED"; grep -E "error:" "$V358_OUT/kernel.log" | head -12; exit 1
fi

echo "=== STEP2 settle kernel via a second prelink ==="
./unixnu prelink --skip-prelink -D "$V358_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V358_SOC" --unique-chip-id 0x47403234 \
  >"$V358_OUT/prelink.log" 2>&1
echo "prelink rc=$?"
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K")
echo "kernel.macho size=$SZ"
if [ "$SZ" -gt 25000000 ]; then echo "STILL UNSTRIPPED - ABORT"; exit 1; fi

echo "=== STEP3 probe gate ==="
MISS=0
for p in 'v358 spmap' 'v358 sdone' 'v358 pre' 'v358 post' \
         'v355 asid' 'v355 maxasid' 'v355 plru' \
         'v349 vs pmap' 'v349 pmap asid' 'v350 skip switchback' 'v331 map'; do
  N=$(grep -aoc "$p" "$K" 2>/dev/null || true)
  printf "  %-24s %s\n" "$p" "$N"
  [ "$N" -eq 0 ] && MISS=$((MISS+1))
done
printf "  %-24s %s\n" "md5" "$(md5sum "$K" | cut -c1-16)"
printf "  %-24s %s\n" "NativeUfs8996" "$(nm "$K" 2>/dev/null | grep -c NativeUfs8996 || true)"
if [ "$MISS" -ne 0 ]; then echo "PROBE GATE FAILED ($MISS missing) - ABORT"; exit 1; fi

echo "=== STEP4 payload ==="
./unixnu payload -D "$V358_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V358_SOC" --unique-chip-id 0x47403234 \
  >"$V358_OUT/payload.log" 2>&1
echo "payload rc=$?"
P=$O/payload/payload.img
ls -l "$P" 2>/dev/null || { echo "NO PAYLOAD"; tail -8 "$V358_OUT/payload.log"; exit 1; }

echo "=== STEP5 pack ==="
python3 "$V358_DEV/tools/pack_fd.py" \
  --base "$V358_BASE/assets/stock-boot-trimmed.img" \
  --fd "$V358_BASE/assets/GOOD-fd-bootshim-v195.bin" \
  --ramdisk "$P" --out "$V358_OUT/boot.img" >"$V358_OUT/pack.log" 2>&1
MD5=$(md5sum "$V358_OUT/boot.img" | cut -d' ' -f1)
echo "boot.img md5=$MD5 size=$(stat -c %s "$V358_OUT/boot.img")"
cp "$K" "$V358_OUT/kernel.macho"; cp "$P" "$V358_OUT/payload.img"
(cd "$V358_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)

if [ "$V358_FLASH" != "1" ]; then
  echo "PIPELINE_BUILD_DONE v358 boot.img md5=$MD5"
  exit 0
fi

echo "=== STEP6 wait + flash ==="
for i in $(seq 1 150); do
  if "$V358_FB" devices 2>/dev/null | grep -q "$V358_SERIAL"; then
    echo "fastboot ready (attempt $i)"
    "$V358_FB" -s "$V358_SERIAL" erase boot 2>&1 | tail -2
    "$V358_FB" -s "$V358_SERIAL" flash boot "$V358_OUT/boot.img" 2>&1 | tail -3
    "$V358_FB" -s "$V358_SERIAL" reboot 2>&1
    echo "PIPELINE_DONE v358 boot.img md5=$MD5"
    exit 0
  fi
  sleep 4
done
echo "TIMEOUT waiting fastboot"
exit 2
