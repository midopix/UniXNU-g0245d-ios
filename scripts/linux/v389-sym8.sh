#!/bin/bash
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
S=/tmp/v389.syms
/usr/bin/llvm-nm -n "$K" > "$S" 2>/dev/null
for A in fffffff00783c2a8 fffffff00755f23c; do
  SYM=$(awk -v a="$A" 'length($1)==16 && $1<=a {last=$1" "$3} END{print last}' "$S")
  SA=${SYM%% *}; SN=${SYM##* }
  OFF=$((0x$A - 0x$SA))
  printf '%s -> %s +0x%x\n' "$A" "$SN" "$OFF"
done
