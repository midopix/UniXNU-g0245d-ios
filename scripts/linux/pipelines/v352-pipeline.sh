#!/bin/bash
# g0245d v352: read the fatal map switch from a photo (trace ring, not status row).
set -o pipefail
source /home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/env.sh
export BISON_PKGDATADIR=/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison
export M4=/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4
BASE=/home/myth/g0245d-clean
UX=$BASE/UniXNU-runtime
DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
OUT=/home/myth/g0245d-auto/auto/v352
SOC=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/local-src/device/UniXNU-msm8996-common
FB=/home/myth/.workbuddy/binaries/gitlocal/bin/fastboot
NM=/home/myth/.workbuddy/binaries/gitlocal/bin/llvm-nm
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
mkdir -p "$OUT"
cd "$UX" || exit 1

echo "=== STEP0 patch v352 ==="
XNU_WORK=$UX/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work \
  python3 "$DEV/scripts/linux/patch_v352.py" || { echo "PATCH FAILED"; exit 1; }

echo "=== STEP1 build kernel ==="
./unixnu build kernel -D "$DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$SOC" >"$OUT/kernel.log" 2>&1
RC=$?
echo "build rc=$RC"
if [ $RC -ne 0 ]; then echo "BUILD FAILED"; grep -E "error:" "$OUT/kernel.log" | head -8; exit 1; fi

echo "=== STEP2 settle kernel via a second prelink ==="
./unixnu prelink --skip-prelink -D "$DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$SOC" --unique-chip-id 0x47403234 >"$OUT/prelink.log" 2>&1
echo "prelink rc=$?"
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K")
echo "kernel.macho size=$SZ"
if [ "$SZ" -gt 25000000 ]; then echo "STILL UNSTRIPPED - ABORT"; exit 1; fi

echo "=== STEP3 probe gate ==="
MISS=0
for p in 'v352 vs call' 'v352 vs map' 'v352 vs old' 'v352 ttb in use' 'v352 ttep' 'v352 asid' 'v352 switch done' 'v352 esr' 'v352 far' 'v352 pc' 'v345 p prefault ok' 'v326 sc'; do
  N=$(strings "$K" | grep -cF "$p")
  printf "  %-22s %s\n" "$p" "$N"
  [ "$N" -eq 0 ] && MISS=$((MISS+1))
done
printf "  %-22s %s\n" "md5" "$(md5sum "$K" | cut -c1-16)"
printf "  %-22s %s\n" "NativeUfs8996" "$($NM "$K" 2>/dev/null | grep -c NativeUfs8996)"
if [ "$MISS" -ne 0 ]; then echo "PROBE GATE FAILED ($MISS missing) - ABORT"; exit 1; fi

echo "=== STEP4 payload ==="
./unixnu payload -D "$DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$SOC" --unique-chip-id 0x47403234 >"$OUT/payload.log" 2>&1
echo "payload rc=$?"
P=$O/payload/payload.img
ls -l "$P" 2>/dev/null || { echo "NO PAYLOAD"; tail -8 "$OUT/payload.log"; exit 1; }

echo "=== STEP5 pack ==="
python3 "$DEV/tools/pack_fd.py" --base "$BASE/assets/stock-boot-trimmed.img" \
  --fd "$BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$OUT/boot.img" >"$OUT/pack.log" 2>&1
MD5=$(md5sum "$OUT/boot.img" | cut -d' ' -f1)
echo "boot.img md5=$MD5 size=$(stat -c %s "$OUT/boot.img")"
cp "$K" "$OUT/kernel.macho"; cp "$P" "$OUT/payload.img"
(cd "$OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)

echo "=== STEP6 build only (no flash) ==="
echo "PIPELINE_BUILD_DONE v352 boot.img md5=$MD5"
exit 0

echo "=== STEP6 wait + flash ==="
for i in $(seq 1 150); do
  if $FB devices 2>/dev/null | grep -q S002170002517; then
    echo "fastboot ready (attempt $i)"
    $FB -s S002170002517 erase boot 2>&1 | tail -2
    $FB -s S002170002517 flash boot "$OUT/boot.img" 2>&1 | tail -3
    $FB -s S002170002517 reboot 2>&1
    echo "PIPELINE_DONE v352 boot.img md5=$MD5"
    exit 0
  fi
  sleep 4
done
echo "TIMEOUT waiting fastboot"
exit 2
