#!/bin/bash
X=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work
grep -rn 'get_saved_state_lr\|get_saved_state_pc' "$X/osfmk/arm64/proc_reg.h" "$X/osfmk/arm64/saved_state.h" 2>/dev/null | head -8
echo ---
grep -rn 'get_saved_state_lr' "$X/osfmk/arm64/" 2>/dev/null | grep -v Binary | head -5
