#!/bin/bash
# v391 diag2: search wider for ufshci reference headers
set -u
echo "== search other trees for ufshci =="
for base in /home/myth/g0245d-clean /home/myth/g0245d-exact /home/myth/g0245d-base /home/myth/UniXNU-runtime; do
  find $base -maxdepth 6 \( -iname '*ufshci*' -o -iname '*ufs*hw*' \) 2>/dev/null | head -5
done
echo
echo "== linker / ddx sources referencing UICCMD =="
grep -rln 'UIC_COMMAND\|UICCMD\|REG_UIC' /home/myth/g0245d-clean 2>/dev/null | head -5
