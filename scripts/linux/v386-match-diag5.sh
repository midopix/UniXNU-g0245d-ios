#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== IOService::startCandidate (4656+) =="
sed -n '4656,4750p' "$X/iokit/Kernel/IOService.cpp"

echo "== probe loop: where winner enters startDict (3779-3900) =="
sed -n '3779,3900p' "$X/iokit/Kernel/IOService.cpp" | grep -n "startDict\|probe(\|addObject\|score\|category" | head -20
