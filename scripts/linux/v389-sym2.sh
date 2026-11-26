#!/bin/bash
find /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66 -maxdepth 8 -name 'kernel*' -size +5M 2>/dev/null | head -10
echo ---
find /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66 -maxdepth 8 -type d -name 'ios-obj' 2>/dev/null | head -5
echo ---
ls /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/ 2>/dev/null | head
