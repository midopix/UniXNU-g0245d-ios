#!/usr/bin/env bash
set -u
TC=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain
K=/home/myth/g0245d-auto/auto/v388/kernel.macho
echo "== nm ufs8996 in auto kernel =="
"$TC/CommandLineTools/usr/bin/llvm-nm" "$K" 2>&1 | grep -c ufs8996
"$TC/CommandLineTools/usr/bin/llvm-nm" "$K" 2>&1 | grep ufs8996 | head -25
echo "== strings: start_calls / v388 =="
strings "$K" | grep -E "ufs8996_start_calls|v388" | head -5
