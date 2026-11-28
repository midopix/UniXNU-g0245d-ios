#!/bin/bash
set -o pipefail
V365_BASE=/home/myth
V365_DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
O=$V365_BASE/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d
OUT=/home/myth/g0245d-auto/auto/v457prb
WIN=/mnt/d/G0245D/auto/v457prb
mkdir -p "$OUT"

echo "=== 1) authoritative probe patch log ==="
PL=$O/logs/payload-patch.log
cat "$PL"
grep -q 'panic screen' "$PL" || { echo NO_PANIC_SCREEN_PATCH; exit 1; }
grep -q 'stage 1 blue bar, stage 2 magenta bar' "$PL" || { echo NO_STAGE_BARS; exit 1; }
echo "PROBE_INJECTED_OK"

echo "=== 2) pack boot.img from the probe-injected payload ==="
P=$O/payload/payload.img
ls -l "$P"
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$OUT/boot.img" >"$OUT/pack.log" 2>&1 || { echo PACK_FAILED; tail -20 "$OUT/pack.log"; exit 1; }
cp "$P" "$OUT/payload.img"
cp "$PL" "$OUT/payload-patch.log"
(cd "$OUT" && md5sum boot.img payload.img > MD5.txt)
echo "BUILD_DONE v457prb boot.img md5=$(md5sum "$OUT/boot.img" | cut -d' ' -f1)"
echo "boot args in payload:"; grep -ao 'boot-progress=[0-9]' "$P" | head -2 || true

echo "=== 3) copy to Windows side ==="
mkdir -p "$WIN"
cp "$OUT"/* "$WIN"/
md5sum "$WIN/boot.img"
ls -la "$WIN" | head -12
