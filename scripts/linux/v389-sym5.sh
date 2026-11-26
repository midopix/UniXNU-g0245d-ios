#!/bin/bash
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
/usr/bin/llvm-nm -n "$K" > /tmp/v388.syms 2>/dev/null
wc -l /tmp/v388.syms
for A in ffffff00755f23c ffffff007bb31f0 ffffff007bb31f8; do
  printf '%s -> ' "$A"
  awk -v a="$A" '{v=strtonum("0x"$1); t=strtonum("0x"a); if (v<=t && $2 ~ /[tTdDbB]/) {last=$3" +0x"sprintf("%x",t-v)}} END{print last}' /tmp/v388.syms
done
