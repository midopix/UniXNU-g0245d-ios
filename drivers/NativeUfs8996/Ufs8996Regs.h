// SPDX-License-Identifier: BSD-2-Clause-Patent
// MSM8996 UFS 2.0 host-controller register layout (g0245d v385 / C1a).
//
// Offsets are taken from refs/ufs-linux-3.18/scsi/ufshci.h, the CAF msm-3.18
// source that the stock G0245D boot.img was built from.  The previous JEDEC
// layout in this header put VER at 0x04 and the IDs at 0x08/0x0C, which are
// REG_UFS_VERSION/REG_CONTROLLER_DEV_ID on this controller; reading those
// wrong offsets is why the old probe could only report degenerate values.
//
// Transfer-layer registers (>= 0x30 except HCS/HCE) are still intentionally
// undefined: C1a is a read-only identification probe.  No register is written.
#pragma once

#include <stdint.h>

namespace Ufs8996 {

// Controller MMIO window (msm8996.dtsi ufshc@624000, vendor board.dtb).
constexpr uint64_t kControllerPhys = 0x624000ull;
constexpr uint64_t kControllerSize = 0x2500ull;
constexpr unsigned kControllerIrq  = 265;

// QMP UFS PHY window (vendor board.dtb ufsphy@627000, qcom,ufs-phy-qmp-14nm).
constexpr uint64_t kPhyPhys = 0x627000ull;
constexpr uint64_t kPhySize = 0xda8ull;

// UFSHCI register offsets (CAF msm-3.18 ufshci.h).
constexpr unsigned REG_CAP   = 0x00;  // REG_CONTROLLER_CAPABILITIES
constexpr unsigned REG_VER   = 0x08;  // REG_UFS_VERSION (major:31:16, minor:15:0)
constexpr unsigned REG_HCPID = 0x10;  // REG_CONTROLLER_DEV_ID
constexpr unsigned REG_HCMID = 0x14;  // REG_CONTROLLER_PROD_ID
constexpr unsigned REG_IS    = 0x20;  // REG_INTERRUPT_STATUS
constexpr unsigned REG_IE    = 0x24;  // REG_INTERRUPT_ENABLE
constexpr unsigned REG_HCS   = 0x30;  // REG_CONTROLLER_STATUS
constexpr unsigned REG_HCE   = 0x34;  // REG_CONTROLLER_ENABLE (read-only here)

// UIC command interface (g0245d v391; offsets from the silicon's own
// UfsHostBridge.h as listed by NioUfs.cpp -- NOT the JEDEC 0x60 map).
constexpr unsigned REG_UICCMD     = 0x90;  // command opcode
constexpr unsigned REG_UICCMDARG1 = 0x94;
constexpr unsigned REG_UICCMDARG2 = 0x98;
constexpr unsigned REG_UICCMDARG3 = 0x9c;
constexpr unsigned IS_UCCS        = (1u << 10);  // command completion
constexpr unsigned UIC_DME_LINK_STARTUP = 0x16u;

// UIC layer error-code registers (g0245d v392; read-only decode of
// the v391 q=01 result; offsets from msm-3.18 scsi/ufshci.h).
constexpr unsigned REG_UIC_ERR_PA  = 0x38;
constexpr unsigned REG_UIC_ERR_DL  = 0x3c;
constexpr unsigned REG_UIC_ERR_NL  = 0x40;
constexpr unsigned REG_UIC_ERR_TL  = 0x44;
constexpr unsigned REG_UIC_ERR_DME = 0x48;

constexpr unsigned VER_MAJOR_SHIFT = 16;
constexpr unsigned VER_MINOR_SHIFT = 0;
constexpr uint32_t VER_FIELD_MASK  = 0xffffu;
constexpr uint32_t HCS_UCRDY       = (1u << 3);

} // namespace Ufs8996
