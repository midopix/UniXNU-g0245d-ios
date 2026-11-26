#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== probeCandidates 3990-4082 (probe call + startDict insert) =="
sed -n '3990,4082p' "$X/iokit/Kernel/IOService.cpp"
