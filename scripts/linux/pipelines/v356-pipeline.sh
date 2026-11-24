#!/bin/bash
# g0245d v356 -- build pipeline, dual-line / machine-independent.
#
# Required environment:
#   V356_BASE   clean base dir (holds UniXNU-runtime/ and assets/)
#   V356_DEV    UniXNU-g0245d-ios checkout (scripts/linux/patch_v356.py)
#   V356_SOC    UniXNU-msm8996-common checkout (local module)
#   V356_OUT    output directory, e.g. $HOME/g0245d-auto/auto/v356
# Optional:
#   V356_ENV    env.sh to source before building (toolchain paths, etc.)
#   V356_FB     fastboot binary (only needed with V356_FLASH=1)
#   V356_SERIAL device serial (only needed with V356_FLASH=1)
#   V356_FLASH  set to 1 to wait for fastboot and flash; default build only
#
# Works on both bring-up lines:
#   - dev line:          patch_v356 STEP1 adds the v354 alignment fix
#   - ubuntu line:       STEP1 detects v354 fix and skips it
#   - both:              STEP2 adds v355 ASID probes if missing, STEP3 adds
#                        the four v356 bisect probes
set -o pipefail
: "${V356_BASE:?V356_BASE is required}"
: "${V356_DEV:?V356_DEV is required}"
: "${V356_SOC:?V356_SOC is required}"
: "${V356_OUT:?V356_OUT is required}"

if [ -n "$V356_ENV" ]; then
  echo "=== sourcing $V356_ENV ==="
  source "$V356_ENV"
fi

export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V356_BASE/.tools/share/bison}"
export M4="${M4:-$V356_BASE/.tools/bin/m4}"

UX=$V356_BASE/UniXNU-runtime
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
W=$O/tree/.cache/xnu-work
mkdir -p "$V356_OUT"
cd "$UX" || exit 1

echo "=== STEP0 patch v356 (dual-line, idempotent) ==="
XNU_WORK=$W python3 "$V356_DEV/scripts/linux/patch_v356.py" || { echo "PATCH FAILED"; exit 1; }

echo "=== STEP1 build kernel ==="
./unixnu build kernel -D "$V356_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V356_SOC" >"$V356_OUT/kernel.log" 2>&1
RC=$?
echo "build rc=$RC"
if [ $RC -ne 0 ]; then
  echo "BUILD FAILED"; grep -E "error:" "$V356_OUT/kernel.log" | head -12; exit 1
fi

echo "=== STEP2 settle kernel via a second prelink ==="
./unixnu prelink --skip-prelink -D "$V356_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V356_SOC" --unique-chip-id 0x47403234 \
  >"$V356_OUT/prelink.log" 2>&1
echo "prelink rc=$?"
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K")
echo "kernel.macho size=$SZ"
if [ "$SZ" -gt 25000000 ]; then echo "STILL UNSTRIPPED - ABORT"; exit 1; fi

echo "=== STEP3 probe gate ==="
MISS=0
for p in 'v356 spmap' 'v356 sdone' 'v356 pre' 'v356 post' \
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
./unixnu payload -D "$V356_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V356_SOC" --unique-chip-id 0x47403234 \
  >"$V356_OUT/payload.log" 2>&1
echo "payload rc=$?"
P=$O/payload/payload.img
ls -l "$P" 2>/dev/null || { echo "NO PAYLOAD"; tail -8 "$V356_OUT/payload.log"; exit 1; }

echo "=== STEP5 pack ==="
python3 "$V356_DEV/tools/pack_fd.py" \
  --base "$V356_BASE/assets/stock-boot-trimmed.img" \
  --fd "$V356_BASE/assets/GOOD-fd-bootshim-v195.bin" \
  --ramdisk "$P" --out "$V356_OUT/boot.img" >"$V356_OUT/pack.log" 2>&1
MD5=$(md5sum "$V356_OUT/boot.img" | cut -d' ' -f1)
echo "boot.img md5=$MD5 size=$(stat -c %s "$V356_OUT/boot.img")"
cp "$K" "$V356_OUT/kernel.macho"; cp "$P" "$V356_OUT/payload.img"
(cd "$V356_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)

if [ "$V356_FLASH" != "1" ]; then
  echo "PIPELINE_BUILD_DONE v356 boot.img md5=$MD5"
  exit 0
fi

echo "=== STEP6 wait + flash ==="
for i in $(seq 1 150); do
  if "$V356_FB" devices 2>/dev/null | grep -q "$V356_SERIAL"; then
    echo "fastboot ready (attempt $i)"
    "$V356_FB" -s "$V356_SERIAL" erase boot 2>&1 | tail -2
    "$V356_FB" -s "$V356_SERIAL" flash boot "$V356_OUT/boot.img" 2>&1 | tail -3
    "$V356_FB" -s "$V356_SERIAL" reboot 2>&1
    echo "PIPELINE_DONE v356 boot.img md5=$MD5"
    exit 0
  fi
  sleep 4
done
echo "TIMEOUT waiting fastboot"
exit 2
