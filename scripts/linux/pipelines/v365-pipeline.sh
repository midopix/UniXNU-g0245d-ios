#!/bin/bash
# g0245d v365 -- build pipeline (dual-line, machine-independent).
# Applies the cumulative v355..v365 probe chain (all idempotent) on top of a
# v354 work tree, builds, settles via second prelink, gates probes, packs.
# Adapted from v358-pipeline.sh.  Flash is handled by a separate watchdog so a
# hung device (no USB enumeration) never stalls the build.
set -o pipefail
: "${V365_BASE:?V365_BASE is required}"
: "${V365_DEV:?V365_DEV is required}"
: "${V365_SOC:?V365_SOC is required}"
: "${V365_OUT:?V365_OUT is required}"
if [ -n "$V365_ENV" ]; then
  echo "=== sourcing $V365_ENV ==="
  source "$V365_ENV"
fi
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V365_BASE/.tools/share/bison}"
export M4="${M4:-$V365_BASE/.tools/bin/m4}"
UX=$V365_BASE/UniXNU-runtime
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
W=$O/tree/.cache/xnu-work
mkdir -p "$V365_OUT"
cd "$UX" || exit 1

echo "=== STEP0 apply v355..v365 (idempotent, in order) ==="
for v in 355 356 357 358 359 360 361 362 363 364 365; do
  XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v$v.py" || { echo "PATCH v$v FAILED"; exit 1; }
done

echo "=== STEP1 build kernel ==="
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V365_SOC" >"$V365_OUT/kernel.log" 2>&1
RC=$?
echo "build rc=$RC"
if [ $RC -ne 0 ]; then
  echo "BUILD FAILED"; grep -E "error:" "$V365_OUT/kernel.log" | head -12; exit 1
fi

echo "=== STEP2 settle kernel via a second prelink ==="
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 \
  >"$V365_OUT/prelink.log" 2>&1
echo "prelink rc=$?"
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K")
echo "kernel.macho size=$SZ"
if [ "$SZ" -gt 25000000 ]; then echo "STILL UNSTRIPPED - ABORT"; exit 1; fi

echo "=== STEP3 probe gate ==="
MISS=0
for p in 'v365 noSR' 'v362 s6' 'v362 s6c' 'v361' 'v360' 'v358 spmap' \
         'v354 ttep low' 'v352 switch done' 'v352 esr' 'v331 map'; do
  N=$(strings "$K" | grep -cF "$p" 2>/dev/null || true)
  printf "  %-22s %s\n" "$p" "$N"
done
# hard requirement: the v365 workaround marker must be present
N=$(strings "$K" | grep -cF 'v365 noSR' 2>/dev/null || true)
if [ "$N" -eq 0 ]; then echo "PROBE GATE FAILED: v365 noSR missing - ABORT"; exit 1; fi
printf "  %-22s %s\n" "md5" "$(md5sum "$K" | cut -c1-16)"
printf "  %-22s %s\n" "NativeUfs8996" "$(nm "$K" 2>/dev/null | grep -c NativeUfs8996 || true)"

echo "=== STEP4 payload ==="
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 \
  --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 \
  >"$V365_OUT/payload.log" 2>&1
echo "payload rc=$?"
P=$O/payload/payload.img
ls -l "$P" 2>/dev/null || { echo "NO PAYLOAD"; tail -8 "$V365_OUT/payload.log"; exit 1; }

echo "=== STEP5 pack ==="
python3 "$V365_DEV/tools/pack_fd.py" \
  --base "$V365_BASE/assets/stock-boot-trimmed.img" \
  --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" \
  --ramdisk "$P" --out "$V365_OUT/boot.img" >"$V365_OUT/pack.log" 2>&1
MD5=$(md5sum "$V365_OUT/boot.img" | cut -d' ' -f1)
echo "boot.img md5=$MD5 size=$(stat -c %s "$V365_OUT/boot.img")"
cp "$K" "$V365_OUT/kernel.macho"; cp "$P" "$V365_OUT/payload.img"
(cd "$V365_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v365 boot.img md5=$MD5"
