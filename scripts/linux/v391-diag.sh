#!/bin/bash
# v391 diag: verify UIC command register offsets and DME_LINKSTARTUP opcode
# against the CAF 3.18 reference tree.
set -u
SOC=/home/myth/g0245d-clean/UniXNU-msm8996-common
echo "== candidate ufshci headers =="
find $SOC -iname '*ufshci*' -o -iname '*ufs*reg*' 2>/dev/null | head -10
echo
echo "== UIC command register offsets in reference =="
for f in $(find $SOC -iname '*ufshci*' 2>/dev/null | head -5); do
  echo "--- $f"
  grep -n 'UIC_COMMAND\|UICCMD\|0x60\|0x68\|0x70\|0x74\|0x78' "$f" 2>/dev/null | head -15
done
echo
echo "== DME LINKSTARTUP opcode in reference =="
grep -rn 'LINKSTARTUP\|LinkStartup' $SOC --include=*.h --include=*.c 2>/dev/null | head -10
