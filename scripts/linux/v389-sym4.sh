#!/bin/bash
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
NM=/usr/bin/llvm-nm
"$NM" -n "$K" > /tmp/v388.syms 2>/dev/null
wc -l /tmp/v388.syms
for A in ffffff00755f23c ffffff007bb31f0 ffffff007bb31f8; do
  printf '%s -> ' "$A"
  awk -v a="$A" '{v=("0x"$1); if (v<=a) {last=$1" "$3; off=a-v} else exit} END{print last" +0x"off}' /tmp/v388.syms
done
