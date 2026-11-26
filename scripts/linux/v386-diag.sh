#!/bin/bash
# v386 diagnostic: check kernel.macho for v386 strings + why gate failed.
K=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/kernel/kernel.macho
O=/home/myth/g0245d-auto/auto/v386
W=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work
echo "== kernel.macho"; stat -c "%s bytes  mtime %y" "$K"
echo "== v386 strings in kernel.macho"; strings "$K" | grep -a v386 | head -10
echo "== kernel.log tail"; tail -8 "$O/kernel.log"
echo "== bsd_init.c mtime"; stat -c "%y" "$W/bsd/kern/bsd_init.c"
echo "== bsd_init.o"; ls -la "$W/bsd/kern/"*.o 2>/dev/null | head -3
echo "== bsd_init.o strings"; strings "$W/bsd/kern/bsd_init.o" 2>/dev/null | grep -a v386 | head -5
echo "== obj dir for bsd"; find "$W" -name "bsd_init.o" 2>/dev/null | head -5
