#!/usr/bin/env bash
set -u
K=/home/myth/g0245d-auto/auto/v388/kernel.macho
TC=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain
echo "== start_calls symbol in kernel =="
"$TC/CommandLineTools/usr/bin/llvm-nm" "$K" 2>/dev/null | grep -i "ufs8996_start_calls" || echo "SYMBOL NOT FOUND"
echo "== driver archive mtime vs source =="
A=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/nativeufs8996/libNativeUfs8996.a
S=/mnt/c/Users/Admin/WorkBuddy/2026-11-20-20-05-27/UniXNU-g0245d-ios/drivers/NativeUfs8996/NativeUfs8996.cpp
stat -c "%y %n" "$A" "$S"
