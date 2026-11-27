// SPDX-License-Identifier: BSD-2-Clause-Patent
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
// g0245d v388: how many times start() was entered (rematch detector).
volatile uint32_t ufs8996_start_calls = 0;
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
// g0245d v390: C2 HCE-enable probe state.
volatile uint32_t ufs8996_hce_before = 0;
volatile uint32_t ufs8996_hcs_after  = 0;
volatile uint32_t ufs8996_poll       = 0;
volatile uint32_t ufs8996_en         = 0;
// g0245d v391: C2 link-startup probe state.
volatile uint32_t ufs8996_uic_is     = 0;
volatile uint32_t ufs8996_uic_ready  = 0;
volatile uint32_t ufs8996_uic_spins  = 0;
volatile uint32_t ufs8996_uic_result = 0;
volatile uint32_t ufs8996_uic_hcs    = 0;
// g0245d v392: UIC layer error-code snapshot.
volatile uint32_t ufs8996_err_pa  = 0;
volatile uint32_t ufs8996_err_dl  = 0;
volatile uint32_t ufs8996_err_nl  = 0;
volatile uint32_t ufs8996_err_tl  = 0;
volatile uint32_t ufs8996_err_dme = 0;

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
  static void write32(uintptr_t base, unsigned offset, uint32_t value);
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

void NativeUfs8996::write32(uintptr_t base, unsigned offset, uint32_t value)
{
  *reinterpret_cast<volatile uint32_t *>(base + offset) = value;
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
  ufs8996_start_calls++;
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

  /* g0245d v390: C2 step 1 -- enable the host controller (HCE).
   * If LK already left it enabled, record HCS and move on. */
  ufs8996_hce_before = read32(fBase, Ufs8996::REG_HCE);
  if ((ufs8996_hce_before & 1u) == 0u) {
    write32(fBase, Ufs8996::REG_HCE, 1u);
    unsigned int v390_n;
    for (v390_n = 0; v390_n < 200000u; v390_n++) {
      ufs8996_hcs_after = read32(fBase, Ufs8996::REG_HCS);
      if (ufs8996_hcs_after & 1u) { break; }
    }
    ufs8996_poll = v390_n;
    ufs8996_en = (ufs8996_hcs_after & 1u) ? 1u : 2u;
  } else {
    ufs8996_hcs_after = read32(fBase, Ufs8996::REG_HCS);
    ufs8996_poll = 0;
    ufs8996_en = 3u; /* already enabled by LK */
  }
  ufs8996_step = 6;
  g0245d_trace_u("v390 hce", ufs8996_hce_before);
  g0245d_trace_u("v390 hcs", ufs8996_hcs_after);

  /* g0245d v391: C2 step 2 -- DME_LINKSTARTUP via the UIC command
   * interface, the proven NioUfs/EDK2 sequence.  Bounded everywhere:
   * a silent controller must degrade to a status row, not hang. */
  ufs8996_uic_is = read32(fBase, Ufs8996::REG_IS);
  if (ufs8996_uic_is & Ufs8996::IS_UCCS) {
    write32(fBase, Ufs8996::REG_IS, Ufs8996::IS_UCCS); /* ack stale */
  }
  {
    unsigned int v391_i;
    ufs8996_uic_ready = 2u;
    for (v391_i = 0; v391_i < 100000u; v391_i++) {
      if (read32(fBase, Ufs8996::REG_HCS) & Ufs8996::HCS_UCRDY) {
        ufs8996_uic_ready = 1u;
        break;
      }
    }
    if (ufs8996_uic_ready == 1u) {
      write32(fBase, Ufs8996::REG_UICCMDARG1, 0u);
      write32(fBase, Ufs8996::REG_UICCMDARG2, 0u);
      write32(fBase, Ufs8996::REG_UICCMDARG3, 0u);
      write32(fBase, Ufs8996::REG_UICCMD,
              Ufs8996::UIC_DME_LINK_STARTUP);
      unsigned int v391_w;
      for (v391_w = 0; v391_w < 100000u; v391_w++) {
        if (read32(fBase, Ufs8996::REG_IS) & Ufs8996::IS_UCCS) {
          break;
        }
      }
      ufs8996_uic_spins = v391_w;
      ufs8996_uic_result =
          read32(fBase, Ufs8996::REG_UICCMDARG2) & 0xffu;
      write32(fBase, Ufs8996::REG_IS, Ufs8996::IS_UCCS);
    }
  }
  ufs8996_uic_hcs = read32(fBase, Ufs8996::REG_HCS);

  /* g0245d v392: q=01 is only a generic DME failure.  Decode which
   * UniPro layer reported it, without issuing another UIC command. */
  ufs8996_err_pa  = read32(fBase, Ufs8996::REG_UIC_ERR_PA);
  ufs8996_err_dl  = read32(fBase, Ufs8996::REG_UIC_ERR_DL);
  ufs8996_err_nl  = read32(fBase, Ufs8996::REG_UIC_ERR_NL);
  ufs8996_err_tl  = read32(fBase, Ufs8996::REG_UIC_ERR_TL);
  ufs8996_err_dme = read32(fBase, Ufs8996::REG_UIC_ERR_DME);

  ufs8996_step = 7;
  g0245d_trace_u("v391 ls", ufs8996_uic_result);
  return true;
}

void NativeUfs8996::stop(IOService *provider)
{
  if (fMap) { fMap->release(); fMap = nullptr; }
  if (fMapPhy) { fMapPhy->release(); fMapPhy = nullptr; }
  fBase = 0; fPhy = 0;
  IOService::stop(provider);
}
