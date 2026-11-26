#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== IOService::attach =="
grep -n "bool IOService::attach" "$X/iokit/Kernel/IOService.cpp"
awk '/^bool IOService::attach\(/{f=1} f{print; if(/^}/) exit}' "$X/iokit/Kernel/IOService.cpp" | head -60

echo "== NO_KEXTD / config =="
grep -rn "NO_KEXTD" "$X/iokit/Kernel/IOService.cpp" | head -3
grep -rn "define NO_KEXTD\|NO_KEXTD=" "$X" --include=Makefile* --include=*.mk 2>/dev/null | head -5

echo "== ufs8996 globals in driver =="
sed -n '36,50p' /home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios/drivers/NativeUfs8996/NativeUfs8996.cpp
