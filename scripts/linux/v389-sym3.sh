#!/bin/bash
ls -la /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/kernel/ 2>/dev/null
echo --- obj dir ---
ls -la /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/build/xnu/obj/ 2>/dev/null | head -20
echo --- find unstripped ---
find /home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66 -maxdepth 9 -size +8M -type f 2>/dev/null | head -10
