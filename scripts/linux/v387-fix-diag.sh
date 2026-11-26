#!/usr/bin/env bash
set -u
F=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work/iokit/Kernel/IOService.cpp
echo "== damaged area 4645-4700 =="
sed -n '4645,4700p' "$F"
echo "== probeCandidates header area (search) =="
grep -n "IOService::probeCandidates( OSOrderedSet" "$F"
N=$(grep -n "IOService::probeCandidates( OSOrderedSet" "$F" | head -1 | cut -d: -f1)
S=$((N-6))
sed -n "${S},$((N+3))p" "$F"
