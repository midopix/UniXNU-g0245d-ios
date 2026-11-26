#!/bin/bash
# v391 diag3: read UIC register offsets + LINKSTARTUP from references
set -u
echo "===== EDK2 UfsHci.h: UIC command registers ====="
F=/home/myth/g0245d-clean/Mu-Silicium/Mu_Basecore/MdePkg/Include/IndustryStandard/UfsHci.h
grep -n 'UicCommand\|UIC_COMMAND\|UicCmd\|0x60\|0x68\|0x70\|0x74\|0x78\|Uccs\|UCCS' $F | head -25
echo
echo "===== EDK2: LINKSTARTUP opcode ====="
grep -rn 'LinkStartup\|LINKSTARTUP\|UicOpcode\|UFS_UIC' /home/myth/g0245d-clean/Mu-Silicium/Mu_Basecore/MdeModulePkg/Bus/Ufs/UfsPassThruDxe/*.h 2>/dev/null | head -15
echo
echo "===== NioUfs.cpp: UIC / linkstartup usage ====="
N=/home/myth/g0245d-clean/ios-ports/nio/drivers/NioUfs/NioUfs.cpp
grep -n 'UIC\|Uic\|0x60\|0x70\|0x68\|LINKSTARTUP\|LinkStartup\|DME' $N | head -30
