#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== probe loop 3860-3990 (categoryConsumed handling) =="
sed -n '3860,3990p' "$X/iokit/Kernel/IOService.cpp"
