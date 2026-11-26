#!/usr/bin/env bash
# v386 verdict follow-up: C1a judged from the pinned row; now inspect
# how/when IOKit would call NativeUfs8996::start() in this tree.
set -u
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work
R=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios

echo "== StartIOKitMatching in pexpert/iokit =="
grep -rn "StartIOKitMatching" "$X/pexpert" "$X/iokit" 2>/dev/null | head -10

echo "== IOStartIOKit.cpp start-related functions =="
F="$X/iokit/Kernel/IOStartIOKit.cpp"
if [ -f "$F" ]; then
  grep -n "^[a-zA-Z].*(\|^void\|^kern_return_t\|^bool\|^static" "$F" | head -20
  echo "-- lines 190-260 --"
  sed -n '190,260p' "$F"
else
  echo "IOStartIOKit.cpp not found; searching tree:"
  find "$X/iokit" -name "IOStartIOKit*" 2>/dev/null
fi

echo "== kernel_bootstrap: iokit start order =="
grep -rn "StartIOKit\b\|start_IOKit\|iokit_start\|kernel_iokit" "$X/osfmk/kern/kernel_bootstrap.c" 2>/dev/null | head -10
grep -rn "kernel_bootstrap\|StartIOKit\|bsd_init" "$X/osfmk/kern/kernel_bootstrap.c" 2>/dev/null | sed -n '1,25p'

echo "== gIOKernelConfigTables usage =="
grep -rln "gIOKernelConfigTables" "$X/iokit" "$X/osfmk" 2>/dev/null | head -5
