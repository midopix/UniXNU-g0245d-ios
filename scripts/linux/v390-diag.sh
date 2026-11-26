#!/bin/bash
D=/mnt/c/Users/Admin/WorkBuddy/2026-11-20-20-05-27/UniXNU-g0245d-ios/drivers/NativeUfs8996
grep -n 'read32\|write32\|REG_HCE\|REG_HCS\|REG_IS\b\|degenerate' "$D/NativeUfs8996.cpp" | head -20
echo === header regs ===
grep -n 'REG_' "$D/Ufs8996Regs.h" | head -25
echo === tail of start() ===
sed -n '288,305p' "$D/NativeUfs8996.cpp"
