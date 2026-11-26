#!/usr/bin/env bash
set -u
TC=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain
K=/home/myth/g0245d-auto/auto/v388/kernel.macho
A=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/kernel/kernel.macho
echo "== mtimes =="
stat -c "%y %n" "$K" "$A" /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/nativeufs8996/libNativeUfs8996.a
echo "== ufs8996 symbols in built kernel =="
"$TC/CommandLineTools/usr/bin/llvm-nm" "$A" 2>/dev/null | grep -c ufs8996
"$TC/CommandLineTools/usr/bin/llvm-nm" "$A" 2>/dev/null | grep ufs8996 | head -20
