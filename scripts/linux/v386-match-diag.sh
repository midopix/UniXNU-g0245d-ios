#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== startIOServiceMatching implementation =="
grep -rn "startIOServiceMatching" "$X/iokit" 2>/dev/null | grep -v "\.h:" | head

echo "== IOCatalogue startMatching =="
grep -n "startMatching\|probeCandidates\|startCandidates\|::start(" "$X/iokit/Kernel/IOCatalogue.cpp" 2>/dev/null | head -20

echo "== IOService matching flow (where start is called) =="
grep -n "startMatching\|probeCandidates\|startCandidates\|start( provider\|registerService" "$X/iokit/Kernel/IOService.cpp" 2>/dev/null | head -30
