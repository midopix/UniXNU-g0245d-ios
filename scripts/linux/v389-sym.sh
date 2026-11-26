#!/bin/bash
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
NM=/usr/bin/llvm-nm
echo "== TEXT segment head =="
"$NM" -m "$K" 2>/dev/null | head -4
BASE=$("$NM" -m "$K" 2>/dev/null | awk '/Segment __TEXT: /{print $3; exit}')
echo "BASE=$BASE"
for A in ffffff800755f23c ffffff8007bb31f0 ffffff8007bb31f8; do
  OFF=$((0x$A - 0x$BASE))
  printf '%s off=0x%x -> ' "$A" "$OFF"
  "$NM" -n "$K" 2>/dev/null | awk -v o="$OFF" 'strtonum("0x"$1) <= o {last=$3" +0x" sprintf("%x", o-strtonum("0x"$1))} END{print last}'
done
