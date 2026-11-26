#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== startCandidate 4750-4860 (path to service->start) =="
sed -n '4750,4860p' "$X/iokit/Kernel/IOService.cpp"

echo "== checkResources =="
grep -n "IOService::checkResources" "$X/iokit/Kernel/IOService.cpp"
