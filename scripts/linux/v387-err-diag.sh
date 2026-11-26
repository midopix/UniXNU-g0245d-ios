#!/usr/bin/env bash
set -u
L=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/logs/kernel.log
echo "== mtime/size =="; stat -c "%y %s" "$L"
echo "== errors =="
grep -niE "error:|undefined|multiple definition|redefinition|No such file" "$L" | head -30
echo "== last 30 =="
tail -30 "$L"
