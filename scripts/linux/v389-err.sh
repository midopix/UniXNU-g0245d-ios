#!/bin/bash
L=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/logs/kernel.log
grep -n 'error:' "$L" | head -10
echo ---
grep -n -B2 -A4 'error:' "$L" | head -40
