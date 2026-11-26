#!/bin/bash
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work
echo "=== sleh.c 495-575 ==="
sed -n '495,575p' "$X/osfmk/arm64/sleh.c"
echo "=== v380 sp1 probes in sleh.c ==="
grep -n 'v380 sp1\|g0245d' "$X/osfmk/arm64/sleh.c" | head -30
