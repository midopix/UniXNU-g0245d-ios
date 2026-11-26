#!/usr/bin/env bash
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

echo "== IOPlatformExpertDevice::startIOServiceMatching =="
sed -n '2100,2160p' "$X/iokit/Kernel/IOPlatformExpert.cpp"

echo "== IOService::startMatching (1070) =="
sed -n '1070,1180p' "$X/iokit/Kernel/IOService.cpp"
