#!/bin/bash
# v391 diag4: read NioUfs UIC command helper + linkstartup call site
set -u
N=/home/myth/g0245d-clean/ios-ports/nio/drivers/NioUfs/NioUfs.cpp
echo "===== UIC helper section (2185-2260) ====="
sed -n '2185,2260p' $N
echo
echo "===== LINKSTARTUP call sites ====="
grep -n 'LinkStartup\|0x16\|UicCmd\|SendUic' $N | head -20
