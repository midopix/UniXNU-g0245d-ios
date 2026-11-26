#!/bin/bash
# v391 diag5: read NioUfs linkstartup call site context
set -u
N=/home/myth/g0245d-clean/ios-ports/nio/drivers/NioUfs/NioUfs.cpp
sed -n '2505,2560p' $N
