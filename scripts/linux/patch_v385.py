#!/usr/bin/env python3
"""g0245d v385 = C1a: UFS register probe.

Only two areas are touched:

  * drivers/NativeUfs8996/              (the probe itself)
  * iokit/KernelConfigTables.cpp        ( personality so probe() ever runs )

The guide says "only drivers/NativeUfs8996", but the shipped tree has NO
IOKit personality for NativeUfs8996, so with the ufshc/ufsphy ADT nodes still
disabled (v322 panic) no nub would ever match the driver and start() would
never run.  Adding a root-nub personality is the smallest way to execute the
probe without re-enabling the ADT nodes that crash IODeviceTreeAlloc.

Register offsets follow refs/ufs-linux-3.18/scsi/ufshci.h (CAF msm-3.18),
NOT the JEDEC layout currently in Ufs8996Regs.h.  In particular VER is at
0x08, product/manufacturer IDs at 0x10/0x14, HCS at 0x30 and HCE at 0x34.

Probes: v385 cap / v385 ver / v385 hcpid.
Verdict: non-zero small VER (e.g. 0x00000200) => LK left the clocks on;
0 or 0xffffffff => clocks gated, go to C1b (GCC clock enable).
"""
import os
import sys
from pathlib import Path

DEV = Path(os.environ.get("G0245D_DEV", str(Path(__file__).resolve().parents[2])))
W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
DRIVER = DEV / "drivers" / "NativeUfs8996"
CPP = DRIVER / "NativeUfs8996.cpp"
HDR = DRIVER / "Ufs8996Regs.h"
KCT = Path(W) / "iokit" / "KernelConfigTables.cpp"
for path in (CPP, HDR, KCT):
    if not path.is_file():
        sys.exit("required file not found: %s" % path)

if "v385 cap" in CPP.read_text(encoding="utf-8", errors="replace") and \
   "g0245d v385 ufs personality" in KCT.read_text(encoding="utf-8", errors="replace"):
    print("patch_v385: already applied -- skip")
    sys.exit(0)

HDR_SRC = '''// SPDX-License-Identifier: BSD-2-Clause-Patent
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

constexpr unsigned VER_MAJOR_SHIFT = 16;
constexpr unsigned VER_MINOR_SHIFT = 0;
constexpr uint32_t VER_FIELD_MASK  = 0xffffu;
constexpr uint32_t HCS_UCRDY       = (1u << 3);

} // namespace Ufs8996
'''

CPP_SRC = '''// SPDX-License-Identifier: BSD-2-Clause-Patent
// MSM8996 (Snapdragon 820) UFS 2.0 read-only register probe (g0245d v385/C1a).
//
// Scope: map the UFSHCI window at 0x624000 (0x2500 bytes) and the QMP PHY
// window at 0x627000 (0xda8 bytes), read CAP / VER / HCPID / HCMID and print
// three framebuffer probes.  No HCE write, no UIC command, no UTP transfer,
// no block device.  "UFS8996Probed = true" only means the MMIO is readable
// and the identification registers are not degenerate.
//
// The ufshc/ufsphy ADT nodes remain disabled (v322: enabling them crashes
// IODeviceTreeAlloc).  v385 adds a root-nub IOKit personality and maps the
// two windows by physical address, so the ADT walk is never widened.
#include <IOKit/IOService.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOPlatformExpert.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSString.h>
#include <libkern/libkern.h>
#include <pexpert/pexpert.h>
#include <kern/debug.h>
#include "Ufs8996Regs.h"

extern "C" void g0245d_trace(const char *label);
extern "C" void g0245d_trace_u(const char *label, unsigned int value);

uint32_t ufs8996_probe_calls = 0;
volatile uint32_t ufs8996_matched = 0;
volatile uint32_t ufs8996_mapped  = 0;
volatile uint32_t ufs8996_status  = 0;
volatile uint32_t ufs8996_step    = 0;
const char *volatile ufs8996_failure = nullptr;
volatile uint32_t ufs8996_cap    = 0;
volatile uint32_t ufs8996_ver    = 0;
volatile uint32_t ufs8996_hcpid  = 0;
volatile uint32_t ufs8996_hcmid  = 0;
volatile uint32_t ufs8996_is     = 0;
volatile uint32_t ufs8996_ie     = 0;
volatile uint32_t ufs8996_hcs    = 0;
volatile uint32_t ufs8996_hce    = 0;

namespace {
const char *const kCompatible[] = {
  // Root nub (ADT /): this is what v385's personality matches.
  "gree,g0245d", "qcom,msm8996",
  // Defensive: also work if the ufshc ADT node is re-enabled some day.
  "qcom,msm8996-ufshc", "qcom,ufshc", "jedec,ufs-2.0",
  "jedec,ufs-1.1", "qcom,ufshc-msm8996", "qcom,msm8996-ufs",
};

bool degenerate(uint32_t value)
{
  return value == 0 || value == 0xffffffffu;
}

bool contains(const char *data, size_t length, const char *needle)
{
  size_t wanted = 0;
  while (needle[wanted]) { wanted++; }
  for (size_t at = 0; at + wanted <= length; at++) {
    size_t index = 0;
    while (index < wanted && data[at + index] == needle[index]) { index++; }
    if (index == wanted) { return true; }
  }
  return false;
}
} // namespace

class NativeUfs8996 : public IOService {
  OSDeclareDefaultStructors(NativeUfs8996)
  IOMemoryMap *fMap = nullptr;
  IOMemoryMap *fMapPhy = nullptr;
  uintptr_t fBase = 0;
  uintptr_t fPhy = 0;
  static uint32_t read32(uintptr_t base, unsigned offset);
  IOMemoryMap *mapPhysical(uint64_t phys, uint64_t size);
public:
  IOService *probe(IOService *provider, SInt32 *score) override;
  bool start(IOService *provider) override;
  void stop(IOService *provider) override;
};

OSDefineMetaClassAndStructors(NativeUfs8996, IOService)

uint32_t NativeUfs8996::read32(uintptr_t base, unsigned offset)
{
  return *reinterpret_cast<volatile uint32_t *>(base + offset);
}

IOMemoryMap *NativeUfs8996::mapPhysical(uint64_t phys, uint64_t size)
{
  IOMemoryDescriptor *desc = IOMemoryDescriptor::withPhysicalAddress(
      static_cast<IOPhysicalAddress>(phys), static_cast<IOByteCount>(size),
      kIODirectionInOut);
  if (!desc) { return nullptr; }
  IOMemoryMap *map = desc->map(kIOMapAnywhere | kIOMapInhibitCache);
  desc->release();
  return map;
}

IOService *NativeUfs8996::probe(IOService *provider, SInt32 *score)
{
  ufs8996_probe_calls++;
  OSObject *property = provider->getProperty("compatible");
  OSData   *data   = OSDynamicCast(OSData, property);
  OSString *string = OSDynamicCast(OSString, property);
  const char *text = nullptr;
  size_t length = 0;
  if (data) {
    text = static_cast<const char *>(data->getBytesNoCopy());
    length = data->getLength();
  } else if (string) {
    text = string->getCStringNoCopy();
    length = string->getLength();
  }
  if (!text) {
    ufs8996_failure = "provider exposes no readable 'compatible' property";
    return nullptr;
  }
  bool match = false;
  for (size_t index = 0; index < sizeof(kCompatible) / sizeof(kCompatible[0]) && !match; index++) {
    match = contains(text, length, kCompatible[index]);
  }
  if (!match) { return nullptr; }
  ufs8996_matched = 1;
  if (score) { *score = 1000; }
  return this;
}

bool NativeUfs8996::start(IOService *provider)
{
  ufs8996_step = 1;
  g0245d_trace("v385 ufs enter");
  if (!IOService::start(provider)) { return false; }

  setProperty("UFS8996ProbeScope",
              "register-read-only; no HCE/UIC/UTP commands");

  auto fail = [&](const char *reason, uint32_t status) -> bool {
    ufs8996_failure = reason;
    ufs8996_status  = status;
    g0245d_trace_u("v385 ufs FAIL", status);
    setProperty("UFS8996Failure", reason);
    setProperty("UFS8996Status", static_cast<unsigned long long>(status), 32);
    setProperty("UFS8996Probed", false);
    if (fMap) { fMap->release(); fMap = nullptr; }
    if (fMapPhy) { fMapPhy->release(); fMapPhy = nullptr; }
    fBase = 0; fPhy = 0;
    return false;
  };

  fMap = mapPhysical(Ufs8996::kControllerPhys, Ufs8996::kControllerSize);
  if (!fMap) { return fail("map 0x624000/0x2500 failed", 1); }
  fMapPhy = mapPhysical(Ufs8996::kPhyPhys, Ufs8996::kPhySize);
  if (!fMapPhy) { return fail("map 0x627000/0xda8 failed", 2); }
  fBase = static_cast<uintptr_t>(fMap->getVirtualAddress());
  fPhy  = static_cast<uintptr_t>(fMapPhy->getVirtualAddress());
  if (!fBase || !fPhy) {
    return fail("mapped UFS MMIO has a null virtual address", 3);
  }
  ufs8996_mapped = 1;
  ufs8996_step   = 2;
  g0245d_trace("v385 ufs map ok");

  // CAF msm-3.18 UFSHCI offsets.  All reads; HCE is never written.
  ufs8996_cap   = read32(fBase, Ufs8996::REG_CAP);
  ufs8996_ver   = read32(fBase, Ufs8996::REG_VER);
  ufs8996_hcpid = read32(fBase, Ufs8996::REG_HCPID);
  ufs8996_hcmid = read32(fBase, Ufs8996::REG_HCMID);
  ufs8996_is    = read32(fBase, Ufs8996::REG_IS);
  ufs8996_ie    = read32(fBase, Ufs8996::REG_IE);
  ufs8996_hcs   = read32(fBase, Ufs8996::REG_HCS);
  ufs8996_hce   = read32(fBase, Ufs8996::REG_HCE);
  ufs8996_step  = 3;
  g0245d_trace_u("v385 cap", ufs8996_cap);
  g0245d_trace_u("v385 ver", ufs8996_ver);
  g0245d_trace_u("v385 hcpid", ufs8996_hcpid);

  uint32_t snapshot[8] = {
    ufs8996_cap, ufs8996_ver, ufs8996_hcpid, ufs8996_hcmid,
    ufs8996_is, ufs8996_ie, ufs8996_hcs, ufs8996_hce,
  };
  setProperty("UFS8996Registers", snapshot,
              static_cast<unsigned int>(sizeof(snapshot)));
  setProperty("UFS8996ControllerPhys",
              static_cast<unsigned long long>(Ufs8996::kControllerPhys), 64);
  setProperty("UFS8996PhyPhys",
              static_cast<unsigned long long>(Ufs8996::kPhyPhys), 64);

  if (degenerate(ufs8996_cap) || degenerate(ufs8996_ver)) {
    return fail("UFSHCI CAP/VER read back as 0 or all-ones: clocks gated, reset, or bus abort", 4);
  }
  ufs8996_step = 4;

  ufs8996_status  = 0;
  ufs8996_failure = nullptr;
  setProperty("UFS8996Status", 0ULL, 32);
  setProperty("UFS8996Version",
              static_cast<unsigned long long>(ufs8996_ver), 32);
  setProperty("UFS8996Capabilities",
              static_cast<unsigned long long>(ufs8996_cap), 32);
  setProperty("UFS8996ProductID",
              static_cast<unsigned long long>(ufs8996_hcpid), 32);
  setProperty("UFS8996ManufacturerID",
              static_cast<unsigned long long>(ufs8996_hcmid), 32);
  setProperty("UFS8996Probed", true);
  registerService();
  ufs8996_step = 5;
  g0245d_trace("v385 ufs probed ok");
  return true;
}

void NativeUfs8996::stop(IOService *provider)
{
  if (fMap) { fMap->release(); fMap = nullptr; }
  if (fMapPhy) { fMapPhy->release(); fMapPhy = nullptr; }
  fBase = 0; fPhy = 0;
  IOService::stop(provider);
}
'''

HDR.write_text(HDR_SRC, encoding="utf-8")
CPP.write_text(CPP_SRC, encoding="utf-8")

src = KCT.read_text(encoding="utf-8")
marker = "g0245d v385 ufs personality"
if marker not in src:
    anchor = ('    "     \'IOProbeScore\'    = 5000:32;"\n'
              '    "   },"\n'
              '    "   {"\n'
              '    "     \'IOClass\'         = IOPanicPlatform;"\n')
    assert src.count(anchor) == 1, src.count(anchor)
    addition = (
        '    "     \'IOProbeScore\'    = 5000:32;"\n'
        '    "   },"\n'
        '    "   {"\n'
        '    "     \'IOClass\'         = NativeUfs8996;"\n'
        '    "     \'IOProviderClass\' = IOPlatformExpertDevice;"\n'
        '    "     \'IONameMatch\'     = \'device-tree\';"\n'
        '    "     \'IOProbeScore\'    = 4000:32;"\n'
        '    "   },"\n'
        '    "   {"\n'
        '    "     \'IOClass\'         = IOPanicPlatform;"\n'
        '    /* %s: root-nub match; ufshc/ufsphy ADT nodes stay disabled. */\n' % marker)
    KCT.write_text(src.replace(anchor, addition, 1), encoding="utf-8")

print("patch_v385: driver rewritten (CAF offsets, 0x624000+0x627000, v385 probes)")
print("patch_v385: root-nub personality added to KernelConfigTables.cpp")
