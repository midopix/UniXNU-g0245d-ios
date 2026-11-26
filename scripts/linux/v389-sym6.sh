#!/bin/bash
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped
S=/tmp/v388.syms
/usr/bin/llvm-nm -n "$K" > "$S" 2>/dev/null
echo "lines: $(wc -l < "$S")"
echo "== head 3 =="; head -3 "$S"
echo "== tail 3 =="; tail -3 "$S"
for A in fffffff00755f23c fffffff007bb31f0 fffffff007bb31f8; do
  printf '%s -> ' "$A"
  awk -v a="$A" '{v=strtonum("0x"$1); t=strtonum("0x"a); if (v<=t) {last=$1" "$2" "$3" +0x"sprintf("%x",t-v)}} END{print last}' "$S"
done
