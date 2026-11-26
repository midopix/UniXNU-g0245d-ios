#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== probeCandidates around startCandidate (4080-4160) =="
sed -n '4080,4160p' "$X/iokit/Kernel/IOService.cpp"
