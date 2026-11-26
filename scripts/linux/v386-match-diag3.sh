#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== IOService::registerService (1014) =="
sed -n '1014,1068p' "$X/iokit/Kernel/IOService.cpp"

echo "== doServiceMatch area: find it =="
grep -n "doServiceMatch\|startCandidates\|startCandidate\b" "$X/iokit/Kernel/IOService.cpp" | head -20
