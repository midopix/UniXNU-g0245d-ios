#!/usr/bin/env bash
set -u
D=/mnt/c/Users/Admin/WorkBuddy/2026-11-20-20-05-27/UniXNU-g0245d-ios/drivers/NativeUfs8996
echo "== mapPhysical helper (84-100) =="
sed -n '84,100p' "$D/NativeUfs8996.cpp"
echo "== Ufs8996Regs.h constants =="
grep -n "kController\|kPhy\|REG_" "$D/Ufs8996Regs.h" | head -25
