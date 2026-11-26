#!/usr/bin/env bash
set -u
D=/mnt/c/Users/Admin/WorkBuddy/2026-11-20-20-05-27/UniXNU-g0245d-ios/drivers/NativeUfs8996
echo "== constants =="
grep -n "kControllerPhys\|kControllerSize\|kPhy\|0x624000\|0x627000\|Ufs8996::" "$D/NativeUfs8996.cpp" "$D/Ufs8996Regs.h" | head -20
echo "== start() map area =="
sed -n '140,200p' "$D/NativeUfs8996.cpp"
echo "== build-arm-driver source dir =="
grep -n "drivers\|DRIVER\|source" /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/scripts/build-arm-driver.py 2>/dev/null | head -10
