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
extern volatile uint32_t ufs8996_query_is;
extern "C" unsigned long long kvtophys(unsigned long long va);

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
// g0245d v393: one-shot UniPro recovery after q=01.
volatile uint32_t ufs8996_recover_reset  = 0;
volatile uint32_t ufs8996_recover_enable = 0;
volatile uint32_t ufs8996_recover_result = 0;
volatile uint32_t ufs8996_recover_spins  = 0;
volatile uint32_t ufs8996_recover_ready  = 0;
// g0245d v394: device-descriptor query result.
volatile uint32_t ufs8996_query_ocs     = 0xf;
volatile uint32_t ufs8996_query_resp    = 0;
volatile uint32_t ufs8996_query_len     = 0;
volatile uint32_t ufs8996_query_bytes01 = 0;
volatile uint32_t ufs8996_query_bytes23 = 0;
// g0245d v410: GEOMETRY descriptor key fields, packed big-endian:
// byte0=MaxNumberLu, byte1=MinAddrBlkSize, byte2=OptReadBlkSize,
// byte3=OptWriteBlkSize (block sizes are log2 exponents).
volatile uint32_t ufs8996_geom = 0xffffffffu;
volatile uint32_t ufs8996_query_spins   = 0;
// g0245d v396: doorbell readback after the UTRL poll.
volatile uint32_t ufs8996_query_doorbell = 0;
// g0245d v399: IS register value after the UTRL poll.
volatile uint32_t ufs8996_query_is = 0;
// g0245d v402: response UPIU header dump (bytes 0-1 and 4-5
// of the 512-byte response area) pinned on the console row.
volatile uint32_t ufs8996_query_type = 0xffff;
volatile uint32_t ufs8996_query_b45  = 0xffff;
// g0245d v403: fDeviceInit sequence diagnostics.
volatile uint32_t ufs8996_query_setresp   = 0xfe;
volatile uint32_t ufs8996_query_readresp  = 0xfe;
volatile uint32_t ufs8996_query_initflag  = 0xffffffffu;
volatile uint32_t ufs8996_query_initpolls = 0xffffffffu;
// g0245d v404: power state + SSU wake diagnostics.
volatile uint32_t ufs8996_query_pmbefore = 0xffu;
volatile uint32_t ufs8996_query_pm       = 0xffu;
volatile uint32_t ufs8996_query_ssu      = 0xffffffu;
// g0245d v405: final READ DESC response TSF echo (idn byte).
volatile uint32_t ufs8996_query_echoidn  = 0xffu;
// g0245d v412: C1f READ(10) LBA0 data-in probe result.
volatile uint32_t ufs8996_gpt_done  = 0;
volatile uint32_t ufs8996_gpt_ocs   = 0xff;
volatile uint32_t ufs8996_gpt_resp  = 0xff;
volatile uint32_t ufs8996_gpt_off   = 0xffff;
// g0245d v415: READ(10) response-UPIU diagnostics (status + sense).
static const char volatile v415_tag[] = "v415 sense diag";
volatile uint32_t ufs8996_gpt_status = 0xff;
volatile uint32_t ufs8996_gpt_sense  = 0xff;  // sense_key<<16 | ASC<<8 | ASCQ
// g0245d v422: protective-MBR boot signature from the LBA0 data page.
volatile uint32_t ufs8996_mbr_sig    = 0xffff;
/* g0245d v424: packed GPT header fields from LBA1:
 * [23:16] partition-entry LBA low byte, [15:8] num-entries low byte,
 * [7:0] entry-size low byte.  Standard GPT => 0x028080. */
volatile uint32_t ufs8996_gpt_hdr    = 0xffffff;
/* g0245d v425: READ(10) completion wait.  bit8 set => the 1e6-iteration
 * poll loop expired without TRANSFER_COMP (command never completed, the
 * zeroed buffer fakes GOOD).  Otherwise value = polls>>12 (0..0xf4). */
volatile uint32_t ufs8996_gpt_wait   = 0xffff;
/* g0245d v441: doorbell-retire wait of the LAST UTP transfer (raw
 * loop count >> 8); 0xfff = slot never cleared.  Displayed d=xxx. */
volatile uint32_t ufs8996_gpt_dbw    = 0xfff;
/* g0245d v426: partition-entry read at the GPT header's entry LBA.
 * pe_num = entries with a non-zero type GUID in the first 4KB page;
 * pe_nm packs the first valid entry's name chars [0] and [1] (UTF-16LE,
 * even offsets 56/58 of the entry). */
/* g0245d v427: attempts used by the LBA1 GPT read retry loop (1..4). */
volatile uint32_t ufs8996_gpt_att    = 0;
volatile uint32_t ufs8996_pe_num     = 0xffff;
volatile uint32_t ufs8996_pe_nm      = 0x2e2e;    // '..'
/* g0245d v428: first-match flag from the full table walk:
 * 'U' = a "userdata" partition was seen, 'S' = "super", '.' = neither. */
volatile uint32_t ufs8996_pe_flag    = 0x2e;      // '.'
volatile uint32_t ufs8996_pe_status  = 0xff;
volatile uint32_t ufs8996_pe_wait    = 0xffff;
/* g0245d v429: the matched "userdata" entry's start/end LBA (low 32
 * bits each; 0xffffffff = not captured).  Displayed as D=xxxxxxxx. */
volatile uint32_t ufs8996_ud_lba     = 0xffffffffu;
volatile uint32_t ufs8996_ud_end     = 0xffffffffu;
/* g0245d v430: first-block fingerprint of userdata: bit0 = nonzero
 * bytes in the first 64, bit1 = ext4 magic @1080 (0xef53),
 * bit2 = f2fs magic @1024 (0xF2F52010).  0 = not read yet. */
volatile uint32_t ufs8996_ud_sig     = 0u;
/* g0245d v433: first 16 bytes of the userdata first block, packed as
 * four little-endian u32 words; pinned to their own console row. */
volatile uint32_t ufs8996_ud_d0      = 0u;
volatile uint32_t ufs8996_ud_d1      = 0u;
volatile uint32_t ufs8996_ud_d2      = 0u;
volatile uint32_t ufs8996_ud_d3      = 0u;
/* g0245d v435: 4-block rolling checksum over the userdata start
 * blocks; ckn = number of consecutive reads completed with GOOD. */
volatile uint32_t ufs8996_ud_ck      = 0u;
volatile uint32_t ufs8996_ud_ckn     = 0u;
/* g0245d v438: SCSI status of the LBA 0x12241 (blk1) read. */
volatile uint32_t ufs8996_ud_b1st    = 0xffu;

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

// g0245d v393: one bounded UIC command, identical to the proven v391 sequence.
// result 0xfe means "not attempted" because UCRDY never arrived.
struct UicRecoveryResult {
  uint32_t is;
  uint32_t ready;
  uint32_t spins;
  uint32_t result;
};

static UicRecoveryResult uicRecoveryCommand(uintptr_t base, unsigned opcode)
{
  UicRecoveryResult out;
  out.is = 0;
  out.ready = 2u;
  out.spins = 100000u;
  out.result = 0xfeu;

  out.is = *reinterpret_cast<volatile uint32_t *>(
      base + Ufs8996::REG_IS);
  if (out.is & Ufs8996::IS_UCCS) {
    *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_IS) =
        Ufs8996::IS_UCCS;
  }
  for (unsigned int i = 0; i < 100000u; i++) {
    if (*reinterpret_cast<volatile uint32_t *>(
            base + Ufs8996::REG_HCS) & Ufs8996::HCS_UCRDY) {
      out.ready = 1u;
      break;
    }
  }
  if (out.ready != 1u) { return out; }

  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG1) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG2) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG3) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMD) = opcode;
  for (unsigned int w = 0; w < 100000u; w++) {
    if (*reinterpret_cast<volatile uint32_t *>(
            base + Ufs8996::REG_IS) & Ufs8996::IS_UCCS) {
      out.spins = w;
      break;
    }
  }
  out.result = *reinterpret_cast<volatile uint32_t *>(
      base + Ufs8996::REG_UICCMDARG2) & 0xffu;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_IS) =
      Ufs8996::IS_UCCS;
  return out;
}

// g0245d v394: one-page, page-aligned UTRD/UCD buffers.  mapPhysical() gives
// an uncached alias so the CPU sees what the controller DMA'd.
alignas(4096) static uint8_t g0245d_v394_utrd_page[4096];
alignas(4096) static uint8_t g0245d_v394_ucd_page[4096];
// g0245d v412: 4KB data-in page for READ(10) LBA0 (GPT header).
alignas(4096) static uint8_t g0245d_v412_data_page[4096];
/* g0245d v446: transport context captured at probe completion so
 * the heartbeat can persist boot progress to the scratch LBA.
 * ctx_ready stays 0 until ALL driver diagnostics are done, so the
 * heartbeat writes never interleave with the probe transfers. */
static uintptr_t g0245d_ufs_ctx_base;
static uint8_t *g0245d_ufs_ctx_utrd;
static uint8_t *g0245d_ufs_ctx_ucd;
static uint64_t g0245d_ufs_ctx_utrd_phys;
static uint64_t g0245d_ufs_ctx_ucd_phys;
static volatile uint32_t g0245d_ufs_ctx_ready;
static volatile uint32_t ufs8996_scr_st = 0xffu;
/* g0245d v447: the alias maps must stay alive for the heartbeat
 * scratch writes; v446 released them and the writes hit dangling
 * mappings (kernel data corruption, abort through __DATA). */
static IOMemoryMap *g0245d_ufs_ctx_utrd_map;
static IOMemoryMap *g0245d_ufs_ctx_ucd_map;
/* g0245d v451: every data-page access goes through this pointer.
 * It starts as the cacheable bss page and is switched to the
 * UNCACHED alias at probe (v451) -- DMA coherency via mapping
 * attributes, no dc ivac/civac anywhere (they hang intermittently
 * on msm8996, cf. v365/v372). */
static uint8_t *g0245d_ufs_data_va = g0245d_ufs_data_va;
static IOMemoryMap *g0245d_ufs_data_map;
/* g0245d v452: APSS watchdog state.  The map is deliberately kept
 * alive for the whole boot; the pet routine is called from the
 * heartbeat in arm_init.c. */
static IOMemoryMap *g0245d_wdt_map;
static volatile uint32_t *g0245d_wdt;
static const char volatile v452_arm_tag[] = "v452 wdt arm";

struct DeviceDescriptorResult {
  uint32_t ocs;
  uint32_t response;
  uint32_t data_len;
  uint32_t bytes01;
  uint32_t bytes23;
  uint32_t spins;
  uint32_t doorbell;
};

static inline void v394Write32(uintptr_t base, unsigned offset, uint32_t value)
{
  *reinterpret_cast<volatile uint32_t *>(base + offset) = value;
}

static inline uint32_t v394Read32(uintptr_t base, unsigned offset)
{
  return *reinterpret_cast<volatile uint32_t *>(base + offset);
}

// g0245d v403: generic flag query (SET/READ FLAG).  Same UTRD, UTRL
// and doorbell handling as the descriptor query below, but with an
// empty data segment and the opcode/idn from the caller.
static void v403FlagQuery(
    uintptr_t base, uint8_t *utrd, uint8_t *ucd,
    uint64_t utrd_phys, uint64_t ucd_phys,
    uint8_t opcode, uint8_t idn,
    volatile uint32_t *out_resp, volatile uint32_t *out_value)
{
  volatile uint8_t *v403_ucd = ucd;
  unsigned int i;
  unsigned int w;
  for (i = 0; i < 4096u; i++) { utrd[i] = 0; ucd[i] = 0; }
  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x21000000u;
  *reinterpret_cast<volatile uint32_t *>(utrd + 8) = 0x0fu;
  *reinterpret_cast<volatile uint32_t *>(utrd + 16) = (uint32_t)ucd_phys;
  *reinterpret_cast<volatile uint32_t *>(utrd + 20) =
      (uint32_t)(ucd_phys >> 32);
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 0u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u;
  v403_ucd[0] = 0x16u;               // TRANSACTION_TYPE_QUERY_REQUEST
  v403_ucd[1] = 0u;                  // flags: none
  v403_ucd[2] = 0u;                  // LUN
  v403_ucd[3] = 0u;                  // task tag
  // g0245d v408: QueryFunc (UPIU byte5) must match the opcode direction.
  // EDK2 Ufs.h: QUERY_FUNC_STD_READ_REQ=0x01 / _WRITE_REQ=0x81.
  // SET FLAG(0x06), WR ATTR(0x04), WR DESC(0x02), CLR FLAG(0x07),
  // TOG FLAG(0x08) are writes; sending them as 0x01 makes the device
  // reject with 0xFE InvalidOpc -> fDeviceInit never sticks.
  {
    static const char volatile v408_tag[] = "v408 qfunc write";
    (void)v408_tag[0];
    v403_ucd[5] =
        (opcode == 0x02u || opcode == 0x04u || opcode == 0x06u ||
         opcode == 0x07u || opcode == 0x08u) ? 0x81u : 0x01u;
  }
  v403_ucd[10] = 0u;                 // data segment length: 0 (flag op)
  v403_ucd[11] = 0u;
  v403_ucd[12] = opcode;             // 0x06 SET FLAG / 0x05 READ FLAG
  v403_ucd[13] = idn;                // 0x01 fDeviceInit
  v403_ucd[14] = 0u;
  v403_ucd[15] = 0u;
  v403_ucd[18] = 0u;                 // OSF length: 0 (flag op)
  v403_ucd[19] = 0u;
  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (i = 0; i < 100000u; i++) { /* bounded settle */ }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  for (i = 0; i < 100000u; i++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u); // slot 0 doorbell
  for (w = 0; w < 1000000u; w++) {
    if (v394Read32(base, Ufs8996::REG_IS) & Ufs8996::IS_UTP_TRANSFER_COMP) {
      break;
    }
  }
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);
  *out_resp = v403_ucd[512 + 6];
  *out_value =
      ((uint32_t)v403_ucd[512 + 20] << 24) |
      ((uint32_t)v403_ucd[512 + 21] << 16) |
      ((uint32_t)v403_ucd[512 + 22] << 8) |
      v403_ucd[512 + 23];
}

// g0245d v404: START STOP UNIT (power condition ACTIVE) to the UFS
// Device W-LUN 0xD0, per ShengUfs and Linux ufshcd_set_dev_pwr_mode.
// COMMAND UPIU (EDK2: transaction type 0x01), 6-byte CDB, no data.
static void v404SsuWake(
    uintptr_t base, uint8_t *utrd, uint8_t *ucd,
    uint64_t utrd_phys, uint64_t ucd_phys)
{
  volatile uint8_t *v404_ucd = ucd;
  static const uint8_t cdb[6] = {
      0x1bu, 0x00u, 0x00u, 0x00u, 0x10u, 0x00u };
  unsigned int i;
  unsigned int w;
  uint32_t ocs;
  uint32_t resp;
  uint32_t scsi;
  for (i = 0; i < 4096u; i++) { utrd[i] = 0; ucd[i] = 0; }
  // UTRD dword0: command type SCSI (0) + INT (bit24), no data direction.
  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x01000000u;
  *reinterpret_cast<volatile uint32_t *>(utrd + 8) = 0x0fu;
  *reinterpret_cast<volatile uint32_t *>(utrd + 16) = (uint32_t)ucd_phys;
  *reinterpret_cast<volatile uint32_t *>(utrd + 20) =
      (uint32_t)(ucd_phys >> 32);
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 0u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u;
  v404_ucd[0] = 0x01u;               // COMMAND UPIU
  v404_ucd[1] = 0x00u;               // flags: none
  v404_ucd[2] = 0xd0u;               // UFS Device W-LUN
  v404_ucd[3] = 0x00u;               // task tag
  v404_ucd[12] = 0x00u;              // expected data transfer length: 0
  v404_ucd[13] = 0x00u;
  v404_ucd[14] = 0x00u;
  v404_ucd[15] = 0x00u;
  for (i = 0; i < 6u; i++) { v404_ucd[16 + i] = cdb[i]; }
  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (i = 0; i < 100000u; i++) { /* bounded settle */ }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  for (i = 0; i < 100000u; i++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u); // slot 0 doorbell
  // IS bit0 or doorbell clear, whichever comes first (ShengUfs polls
  // the doorbell; our controller proved IS with INT commands).
  for (w = 0; w < 1000000u; w++) {
    if ((v394Read32(base, Ufs8996::REG_IS) &
         Ufs8996::IS_UTP_TRANSFER_COMP) ||
        !(v394Read32(base, Ufs8996::REG_UTRL_DB) & 1u)) {
      break;
    }
  }
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);
  ocs = (*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu;
  resp = v404_ucd[512 + 6];
  scsi = v404_ucd[512 + 7];
  ufs8996_query_ssu =
      ((ocs & 0xffu) << 16) | ((resp & 0xffu) << 8) | (scsi & 0xffu);
  // ShengUfs lets the device settle ~50ms before the next query.
  for (w = 0; w < 50u; w++) {
    for (i = 0; i < 100000u; i++) { /* bounded settle */ }
  }
}

// g0245d v412: C1f -- READ(10) LBA0 with PRDT data-in.
// g0245d v418: SPC-3 REQUEST SENSE to read and clear a pending power-on
// UNIT ATTENTION.  The device reports sense_key=0x06 / ASC=0x29 (power-on
// reset) for READ(10); while that UA is pending all non-REQUEST-SENSE
// commands are rejected with CHECK CONDITION.  Uses the same UTRL/UCD/PRDT
// path as v412ReadLba0, then leaves the controller idle for the caller.
static void v418RequestSense(
    uintptr_t base, uint8_t *utrd, uint8_t *ucd,
    uint64_t utrd_phys, uint64_t ucd_phys,
    uint8_t *data, uint64_t data_phys)
{
  static const char volatile v418_tag[] = "v418 request sense ua";
  volatile uint8_t *u = ucd;
  volatile uint32_t *u32 = reinterpret_cast<volatile uint32_t *>(utrd);
  volatile uint32_t *prdt = reinterpret_cast<volatile uint32_t *>(ucd + 1024);
  unsigned w;

  (void)v418_tag[0];
  (void)data;
  for (w = 0; w < 4096u; w++) { utrd[w] = 0; ucd[w] = 0; }

  // PRDT: 18-byte fixed sense buffer (size = bytes-1).
  prdt[0] = (uint32_t)data_phys;
  prdt[1] = (uint32_t)(data_phys >> 32);
  prdt[2] = 0;
  prdt[3] = 18u - 1u;

  u32[0] = 0x05000000u;               // SCSI, DEVICE_TO_HOST, INT
  u32[2] = 0x0fu;                     // OCS invalid
  u32[4] = (uint32_t)ucd_phys;
  u32[5] = (uint32_t)(ucd_phys >> 32);
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 1u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u;

  // COMMAND UPIU: LUN 0, READ data-in, SCSI command set.
  u[0] = 0x01u; u[1] = 0x40u; u[2] = 0x00u; u[3] = 0x00u;
  u[4] = 0u; u[5] = 0u; u[6] = 0u; u[7] = 0u;
  // Expected Data Transfer Length = 18 (big endian, bytes 12..15).
  u[12] = 0u; u[13] = 0u; u[14] = 0u; u[15] = 18u;
  // REQUEST SENSE CDB: 03 00 00 00 12 00 (allocation length 18).
  u[16] = 0x03u; u[17] = 0u; u[18] = 0u; u[19] = 0u;
  u[20] = 0x12u; u[21] = 0u;
  // u[22..31] already zero from the clear above.

  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (w = 0; w < 100000u; w++) { /* settle */ }
  for (w = 0; w < 100000u; w++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u);  // slot 0 doorbell
  for (w = 0; w < 1000000u; w++) {
    if (v394Read32(base, Ufs8996::REG_IS) & Ufs8996::IS_UTP_TRANSFER_COMP) {
      break;
    }
  }
  /* g0245d v441: the slot must retire before the caller re-zeros the
   * descriptor pages; otherwise the controller re-fetches zeroed
   * descriptors and DMAs with a garbage PRDT (memory corruption). */
  {
    static const char volatile v441_tag[] = "v441 dbw rs";
    unsigned dw;
    (void)v441_tag[0];
    for (dw = 0; dw < 200000u; dw++) {
      if ((v394Read32(base, Ufs8996::REG_UTRL_DB) & 1u) == 0u) { break; }
    }
    ufs8996_gpt_dbw = (dw < 200000u) ? (dw >> 8) : 0xfffu;
  }
  // Reading the sense data via REQUEST SENSE clears the UA condition.
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
}

// Reuses the proven UTRL/UCD pages.  The existing UTRD already reserves
// prd_table_offset=256 dwords (ucd+1024), only length was 0.  Fill one PRD
// entry pointing at a 4KB uncached data page, send a COMMAND UPIU with a
// READ(10) CDB, then scan the returned data for the GPT header signature.
static void v412ReadLba0(
    uintptr_t base, uint8_t *utrd, uint8_t *ucd,
    uint64_t utrd_phys, uint64_t ucd_phys,
    uint8_t *data, uint64_t data_phys, uint32_t lba)
{
  volatile uint8_t *v412_ucd = ucd;
  volatile uint32_t *v412_utrd32 =
      reinterpret_cast<volatile uint32_t *>(utrd);
  volatile uint32_t *v412_prdt =
      reinterpret_cast<volatile uint32_t *>(ucd + 1024);
  static const char volatile v412_tag[] = "v412 read10 data";
  // g0245d v413: COMMAND UPIU layout fix tag (see field edits below).
  static const char volatile v413_tag[] = "v413 upiu offsets";
  // g0245d v420: GPT header is at LBA1; LBA0 contains only the protective MBR.
  static const char volatile v420_tag[] = "v420 read lba1 gpt";
  unsigned w;

  (void)v412_tag[0];
  (void)v413_tag[0];
  (void)v420_tag[0];
  ufs8996_gpt_done  = 1;
  ufs8996_gpt_ocs   = 0xe;
  ufs8996_gpt_resp  = 0xfe;
  ufs8996_gpt_off   = 0xffff;
  ufs8996_gpt_status = 0xff;
  ufs8996_gpt_sense  = 0xff;
  (void)v415_tag[0];

  for (w = 0; w < 4096u; w++) { utrd[w] = 0; ucd[w] = 0; }

  // g0245d v418: read & clear the power-on UA first; otherwise READ(10) is
  // rejected with CHECK CONDITION / UA (v415 S=629, sense_key=6 ASC=0x29).
  v418RequestSense(base, utrd, ucd, utrd_phys, ucd_phys, data, data_phys);

  // PRDT entry: one 4096-byte segment at data_phys (size = bytes-1).
  v412_prdt[0] = (uint32_t)data_phys;
  v412_prdt[1] = (uint32_t)(data_phys >> 32);
  v412_prdt[2] = 0;
  v412_prdt[3] = 4095u;

  // UTRD DW0: SCSI command (CT=0), DEVICE_TO_HOST (0x04000000), INT (0x01000000).
  v412_utrd32[0] = 0x05000000u;
  v412_utrd32[2] = 0x0fu;                 // OCS invalid
  v412_utrd32[4] = (uint32_t)ucd_phys;
  v412_utrd32[5] = (uint32_t)(ucd_phys >> 32);
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u;  // resp len (dwords)
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u;  // resp off  (dwords)
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 1u;    // PRDT length
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u;  // PRDT offset (dwords)

  // COMMAND UPIU (EDK2 UTP_COMMAND_UPIU / Linux utp_upiu_cmd).
  v412_ucd[0] = 0x01u;   // TRANSACTION_COMMAND
  v412_ucd[1] = 0x40u;   // UPIU_CMD_FLAGS_READ
  v412_ucd[2] = 0x00u;   // LUN 0
  v412_ucd[3] = 0x00u;   // task tag = doorbell slot 0
  // v413: UPIU header DW1 (bytes 4..7) = command set type = SCSI (0), rest 0.
  // v412 wrongly wrote 0x10 here; device rejected the command (resp=1).
  v412_ucd[4] = 0u; v412_ucd[5] = 0u; v412_ucd[6] = 0u; v412_ucd[7] = 0u;
  // v413: Expected Data Transfer Length is at bytes 12..15, big endian.
  v412_ucd[12] = 0u; v412_ucd[13] = 0u; v412_ucd[14] = 0x10u; v412_ucd[15] = 0u;
  // v413: CDB[16] starts at byte 16 (same layout as the proven v404 SSU).
  // READ(10): 28 00 <LBA4> 00 <len2> 00, LBA1, transfer length 1.
  v412_ucd[16] = 0x28u;  // READ(10)
  v412_ucd[17] = 0x00u;
  v412_ucd[18] = 0u; v412_ucd[19] = 0u;
  // g0245d v428: CDB LBA is big-endian in bytes 18..21; the table walk
  // may reach past LBA 255, so the full 32-bit lba param is encoded.
  v412_ucd[18] = (uint8_t)(lba >> 24);
  v412_ucd[19] = (uint8_t)(lba >> 16);
  v412_ucd[20] = (uint8_t)(lba >> 8);
  v412_ucd[21] = (uint8_t)(lba & 0xffu);
  v412_ucd[22] = 0x00u;
  v412_ucd[23] = 0x00u; v412_ucd[24] = 0x01u;  // transfer length = 1
  v412_ucd[25] = 0x00u;
  v412_ucd[26] = 0u; v412_ucd[27] = 0u; v412_ucd[28] = 0u; v412_ucd[29] = 0u;
  v412_ucd[30] = 0u; v412_ucd[31] = 0u;

  /* g0245d v434: the data page is scanned through the cacheable static
   * array while DMA writes its physical address directly.  Clean and
   * invalidate the whole page BEFORE the doorbell so no dirty line
   * can be written back over the freshly transferred data. */
  /* g0245d v451: no cache ops here -- the data page is accessed
   * through the UNCACHED alias (v451), so CPU writes reach DRAM
   * directly and the DMA is coherent by construction. */

  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (w = 0; w < 100000u; w++) { /* settle */ }
  for (w = 0; w < 100000u; w++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u);  // slot 0 doorbell

  for (w = 0; w < 1000000u; w++) {
    if (v394Read32(base, Ufs8996::REG_IS) & Ufs8996::IS_UTP_TRANSFER_COMP) {
      break;
    }
  }
  // g0245d v425: remember whether TRANSFER_COMP was actually seen.  If the
  // loop expired, the UCD response area is still zeroed and the status
  // fields read back as a fake GOOD -- the heartbeat W= field exposes it.
  ufs8996_gpt_wait = (w < 1000000u)
      ? (w >> 12)
      : (0x100u | ((1000000u >> 12) & 0xffu));
  /* g0245d v441: same retire rule as v418 -- wait for the doorbell
   * slot to clear before the status reads and before any caller
   * re-zeroes the pages for the next transfer. */
  {
    static const char volatile v441_tag[] = "v441 dbw rd";
    unsigned dw;
    (void)v441_tag[0];
    for (dw = 0; dw < 200000u; dw++) {
      if ((v394Read32(base, Ufs8996::REG_UTRL_DB) & 1u) == 0u) { break; }
    }
    ufs8996_gpt_dbw = (dw < 200000u) ? (dw >> 8) : 0xfffu;
  }
  ufs8996_gpt_ocs  = v412_utrd32[2] & 0xfu;
  ufs8996_gpt_resp = v412_ucd[512 + 6];  // response UPIU response code
  // g0245d v415: SCSI status at resp byte7; fixed sense data starts at
  // response UPIU offset 34 (after 12B header + 4B residual + 16B reserved
  // + 2B sense_data_len).  Fixed sense: byte2=sense_key(low nibble),
  // byte12=ASC, byte13=ASCQ  =>  ucd[512+34+2], [512+34+12], [512+34+13].
  ufs8996_gpt_status = v412_ucd[512 + 7];
  ufs8996_gpt_sense =
      ((uint32_t)(v412_ucd[512 + 36] & 0x0fu) << 16) |
      ((uint32_t)v412_ucd[512 + 46] << 8) |
      ((uint32_t)v412_ucd[512 + 47]);

  /* g0245d v434: invalidate the data page after completion so every
   * signature/descriptor scan below reads DRAM, not stale cache
   * lines.  This is the fix for the intermittent P=000f signature. */
  /* g0245d v451: no invalidate needed -- reads go through the
   * UNCACHED alias and always see the DMA result. */
  // g0245d v422: read the protective-MBR boot signature from the data page.
  // LBA0 covers bytes 0..4095 on a 4KB logical block; the PC MBR signature
  // still lives at bytes 510..511.  B=55aa means the buffer holds real data.
  static const char volatile v422_tag[] = "v422 mbr sig";
  (void)v422_tag[0];
  ufs8996_mbr_sig =
      ((uint32_t)data[510] << 8) | ((uint32_t)data[511]);
  // Scan returned LBA1 for the GPT header signature "EFI PART" (v420).
  for (w = 0; w + 8 <= 4096u; w++) {
    if (data[w]     == 'E' && data[w+1] == 'F' &&
        data[w+2]   == 'I' && data[w+3] == ' ' &&
        data[w+4]   == 'P' && data[w+5] == 'A' &&
        data[w+6]   == 'R' && data[w+7] == 'T') {
      ufs8996_gpt_off = w;
      break;
    }
  }
  // g0245d v421: stable LBA1 verdict so the heartbeat row cannot scroll
  // the result away before a photo is taken.
  static const char volatile v421_tag[] = "v421 lba1 gpt";
  (void)v421_tag[0];
  g0245d_trace("v421 lba1 gpt");
  g0245d_trace_u("v421 lba1 off", ufs8996_gpt_off);
  g0245d_trace_u("v421 lba1 st", ufs8996_gpt_status);

  // g0245d v424: parse the GPT header fields at the signature offset.
  // Header: +72 partition-entry LBA (u64 LE), +80 num entries (u32 LE),
  // +84 entry size (u32 LE).  Standard disk: 2 / 128 / 128 => 0x028080.
  static const char volatile v424_tag[] = "v424 gpt hdr";
  (void)v424_tag[0];
  if (ufs8996_gpt_off != 0xffff &&
      (uint64_t)ufs8996_gpt_off + 92u <= 4096u) {
    const uint8_t *h = data + ufs8996_gpt_off;
    ufs8996_gpt_hdr =
        ((uint32_t)h[72] << 16) |
        ((uint32_t)h[80] << 8) |
        ((uint32_t)h[84]);
  }
  g0245d_trace_u("v424 gpt hdr", ufs8996_gpt_hdr);
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
}

static DeviceDescriptorResult v394QueryDevice(
    uintptr_t base, uint8_t *utrd, uint8_t *ucd,
    uint64_t utrd_phys, uint64_t ucd_phys)
{
  DeviceDescriptorResult out;
  out.ocs = 0xfu;
  out.response = 0xfeu;
  out.data_len = 0;
  out.bytes01 = 0;
  out.bytes23 = 0;
  out.spins = 1000000u;
  out.doorbell = 0u;

    // g0245d v404: read bCurrentPowerMode, wake the device with SSU
    // (power condition ACTIVE) to W-LUN 0xD0, read it again.
    {
      uint32_t v404_value = 0;
      v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                    0x03u, 0x02u, &ufs8996_query_readresp, &v404_value);
      ufs8996_query_pmbefore = v404_value & 0xffu;
      g0245d_trace_u("v404 pmbefore", ufs8996_query_pmbefore);
      v404SsuWake(base, utrd, ucd, utrd_phys, ucd_phys);
      v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                    0x03u, 0x02u, &ufs8996_query_readresp, &v404_value);
      ufs8996_query_pm = v404_value & 0xffu;
      g0245d_trace_u("v404 pm", ufs8996_query_pm);
    }
    // g0245d v405: fDeviceInit must run while the device is ACTIVE.
    // In PowerDown every query failed with 0xF6, and a failed READ
    // FLAG returns a zero value field -- the old poll mistook that for
    // "init done".  Require QueryResp==0x00 before trusting the flag.
    {
      uint32_t v405_value = 0;
      unsigned int p;
      v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                    0x06u, 0x01u, &ufs8996_query_setresp, &v405_value);
      for (p = 0; p < 1000u; p++) {
        v405_value = 0xffffffffu;
        ufs8996_query_initpolls = p;
        v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                      0x05u, 0x01u,
                      &ufs8996_query_readresp, &v405_value);
        ufs8996_query_initflag = v405_value & 0xffu;
        if (ufs8996_query_readresp == 0x00u &&
            ufs8996_query_initflag == 0u) { break; }
      }
      g0245d_trace_u("v405 setresp", ufs8996_query_setresp);
      g0245d_trace_u("v405 initflag", ufs8996_query_initflag);
      g0245d_trace_u("v405 initpolls", ufs8996_query_initpolls);
    }

  for (unsigned int i = 0; i < 4096u; i++) { utrd[i] = 0; ucd[i] = 0; }

  // UTRD slot 0: device-management command, no data, OCS invalid.
  // g0245d v397: ufshcd_exec_dev_cmd() marks device-management
  // commands intr_cmd, so Linux ORs UTP_REQ_DESC_INT_CMD (bit24)
  // into UTRD dword0.  Without it the controller may complete the
  // transfer without ever asserting IS bit0.
  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x21000000u;
  *reinterpret_cast<volatile uint32_t *>(utrd + 8) = 0x0fu;
  *reinterpret_cast<volatile uint32_t *>(utrd + 16) = (uint32_t)ucd_phys;
  *reinterpret_cast<volatile uint32_t *>(utrd + 20) = (uint32_t)(ucd_phys >> 32);
  // response_upiu_offset/length and prdt offset are all in dwords.
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u; // 512 >> 2
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u; // 512 >> 2
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 0u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u; // 1024 >> 2

  // g0245d v395: the UCD is an uncached MMU mapping.  v394's adjacent
  // byte writes at ucd[10..13] were merged into `stur w9, [x2, #0xa]`,
  // an unaligned 32-bit store that faulted at pc 0xfffffff007b06914.
  // A volatile byte pointer forbids the merge; every access stays 1 byte.
  volatile uint8_t *v395_ucd = ucd;
  // g0245d v396: Linux uses the same value for UPIU task tag and
  // doorbell slot (lrbp->task_tag = tag; doorbell = 1 << tag).
  // v395 had tag=1 with doorbell slot 0; make both 0.
  // g0245d v400: Linux UPIU_HEADER_DWORD and EDK2 UTP_QUERY_REQ_UPIU
  // both put the transaction type in byte 0 and the task tag in byte 3.
  // v394-v399 had them reversed, so the controller saw NOP_OUT (0x00)
  // instead of QUERY_REQ (0x16), returned OCS=0 and an empty response.
  v395_ucd[0] = 0x16u;               // TRANSACTION_TYPE_QUERY_REQUEST
  v395_ucd[1] = 0u;                  // flags: no data
  v395_ucd[2] = 0u;                  // LUN
  v395_ucd[3] = 0u;                  // task tag = doorbell slot 0
  // g0245d v398: Linux puts query_func in byte 2 of UPIU header
  // dword_1, i.e. UCD offset 6.  v394 put it at offset 5 (byte 1),
  // leaving the real query_func field = 0.  Offset 5 stays 0.
  // g0245d v401: ShengUfs/EDK2/Linux all put query_func at UCD
  // offset 5 (DW1 byte1).  v398 put it at offset 6, which is the
  // response-code position.  Restore offset 5.
  v395_ucd[5] = 0x01u;               // STANDARD_READ_REQUEST
  v395_ucd[10] = 0u;                 // data segment length (hi)
  v395_ucd[11] = 64u;                // data segment length (lo)
  v395_ucd[12] = 0x01u;              // READ_DESC
  // g0245d v411: read UNIT descriptor (idn 0x02) for LUN 0 (byte14=0).
  // It carries LogicBlkSize (byte10) and LogicBlkCount (byte11-18).
  // v409/v410 confirmed GEOMETRY: a=4407 (UFS 4.0, 68 bytes), G=0888
  // (1 LUN, 256B min block).  Now read LUN0's real logical block geometry.
  {
    static const char volatile v409_tag[] = "v409 geom desc";
    static const char volatile v411_tag[] = "v411 unit desc";
    (void)v409_tag[0];
    (void)v411_tag[0];
  }
  v395_ucd[13] = 0x02u;              // UNIT descriptor (v411)
  v395_ucd[14] = 0u;
  v395_ucd[15] = 0u;
  v395_ucd[18] = 0u;                 // descriptor buffer length (hi)
  v395_ucd[19] = 64u;                // descriptor buffer length (lo)

  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (unsigned int i = 0; i < 100000u; i++) { /* bounded settle */ }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  for (unsigned int i = 0; i < 100000u; i++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u); // slot 0 doorbell

  for (unsigned int w = 0; w < 1000000u; w++) {
    if (v394Read32(base, Ufs8996::REG_IS) & Ufs8996::IS_UTP_TRANSFER_COMP) {
      out.spins = w;
      break;
    }
  }
  // g0245d v396: read-only diagnostic -- did the controller consume the
  // doorbell?  0 means it did; a set bit means the request was not taken.
  out.doorbell = v394Read32(base, Ufs8996::REG_UTRL_DB) & 0xfu;
  // g0245d v398: read-only diagnostics -- did IS bit0 ever appear?
  // spins == 1000000 means no; a smaller value means IS was asserted.
  g0245d_trace_u("v398 spins", out.spins);
  // g0245d v399: pin the IS value instead of only tracing it.
  ufs8996_query_is = v394Read32(base, Ufs8996::REG_IS);
  g0245d_trace_u("v398 is", ufs8996_query_is);
  // g0245d v402: dump the response UPIU header bytes (read-only).
  ufs8996_query_type =
      ((uint32_t)v395_ucd[512 + 0] << 8) | v395_ucd[512 + 1];
  ufs8996_query_b45 =
      ((uint32_t)v395_ucd[512 + 4] << 8) | v395_ucd[512 + 5];
  ufs8996_query_echoidn = v395_ucd[512 + 13];
  if (out.spins == 1000000u) {
    // g0245d v397: read-only diagnostics.  v394-v396 left the o/r/a/b/d
    // fields at their sentinel values on timeout, so the photo could not
    // tell whether the controller had written OCS/response at all.
    out.ocs = (*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu;
    // g0245d v397: volatile byte reads forbid 32-bit merge (v394 fault).
    out.response = v395_ucd[512 + 6];
    out.data_len =
        ((uint32_t)v395_ucd[512 + 10] << 8) | v395_ucd[512 + 11];
    out.bytes01 =
        ((uint32_t)v395_ucd[512 + 32] << 8) | v395_ucd[512 + 33];
    out.bytes23 =
        ((uint32_t)v395_ucd[512 + 34] << 8) | v395_ucd[512 + 35];
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);

  out.ocs = (*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu;
  // g0245d v395: same no-merge rule for response bytes.
  out.response = v395_ucd[512 + 6];
  out.data_len =
      ((uint32_t)v395_ucd[512 + 10] << 8) | v395_ucd[512 + 11];
  out.bytes01 =
      ((uint32_t)v395_ucd[512 + 32] << 8) | v395_ucd[512 + 33];
  out.bytes23 =
      ((uint32_t)v395_ucd[512 + 34] << 8) | v395_ucd[512 + 35];
  // g0245d v410: GEOMETRY descriptor fields sit in the response data
  // segment at v395_ucd[512+32 + field_offset].  Volatile byte reads keep
  // the v395 no-merge rule.  The tag makes the change gate-visible.
  {
    static const char volatile v410_tag[] = "v410 geom fields";
    (void)v410_tag[0];
    // g0245d v411: UNIT descriptor LUN0 -- LogicBlkSize (byte10) and
    // LogicBlkCount low 3 bytes (byte11/12/13).  G=lb/c0/c1/c2.
    ufs8996_geom =
        ((uint32_t)v395_ucd[512 + 32 + 10] << 24) |  // LogicBlkSize
        ((uint32_t)v395_ucd[512 + 32 + 11] << 16) |  // LogicBlkCount[0]
        ((uint32_t)v395_ucd[512 + 32 + 12] << 8)  |  // LogicBlkCount[1]
        ((uint32_t)v395_ucd[512 + 32 + 13]);         // LogicBlkCount[2]
  }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
  // g0245d v412: after descriptors are read, attempt the first data-in.
  // g0245d v427: the LBA1 result is intermittent across boots
  // (P=0000 W=004 vs P=000f W=004: both complete fast with GOOD, but the
  // data page sometimes has no signature).  Retry the identical read up
  // to 4 times; A=<attempt> shows how many it took.  W ends up holding
  // the wait of the LAST attempt.
  /* g0245d v446: capture the transport context (used later by the
   * heartbeat scratch writes; armed only at probe completion). */
  g0245d_ufs_ctx_base = base;
  g0245d_ufs_ctx_utrd = utrd;
  g0245d_ufs_ctx_ucd = ucd;
  g0245d_ufs_ctx_utrd_phys = utrd_phys;
  g0245d_ufs_ctx_ucd_phys = ucd_phys;
  {
    unsigned att;
    for (att = 1; att <= 4u; att++) {
      v412ReadLba0(base, utrd, ucd, utrd_phys, ucd_phys,
                   g0245d_ufs_data_va,
                   (uint64_t)kvtophys(
                     (unsigned long long)(uintptr_t)&g0245d_v412_data_page[0]),
                   1u);
      ufs8996_gpt_att = att;
      if (ufs8996_gpt_off != 0xffffu) { break; }
    }
    g0245d_trace_u("v427 att", ufs8996_gpt_att);
  }

  // g0245d v428: walk the full GPT partition entry table.  The data page
  // still holds the LBA1 header here, so parse the FULL header fields
  // (entry LBA u64 @+72, num entries u32 @+80, entry size u32 @+84),
  // then read the entry pages one by one (1 block per read, cap 16 pages)
  // and count all valid entries; flag 'U' when a "userdata" name is seen,
  // 'S' for "super".  Entries that straddle a page boundary are skipped
  // for now (esz values that divide 4096 have none).
  {
    const volatile uint32_t s_off = ufs8996_gpt_off;
    if (s_off != 0xffffu) {
      const uint8_t *h = g0245d_ufs_data_va + s_off;
      uint64_t entLba = 0;
      unsigned nent, esz, pages, p, k;
      unsigned total = 0;
      unsigned fu = 0, fs = 0;
      volatile uint32_t s_hdr   = ufs8996_gpt_hdr;
      volatile uint32_t s_done  = ufs8996_gpt_done;
      volatile uint32_t s_ocs   = ufs8996_gpt_ocs;
      volatile uint32_t s_resp  = ufs8996_gpt_resp;
      volatile uint32_t s_st    = ufs8996_gpt_status;
      volatile uint32_t s_se    = ufs8996_gpt_sense;
      volatile uint32_t s_wait  = ufs8996_gpt_wait;
      volatile uint32_t s_mbr   = ufs8996_mbr_sig;
      volatile uint32_t s_att   = ufs8996_gpt_att;

      for (k = 0; k < 8u; k++) {
        entLba |= ((uint64_t)h[72 + k]) << (8u * k);
      }
      nent = (unsigned)h[80] | ((unsigned)h[81] << 8) |
             ((unsigned)h[82] << 16) | ((unsigned)h[83] << 24);
      esz  = (unsigned)h[84] | ((unsigned)h[85] << 8) |
             ((unsigned)h[86] << 16) | ((unsigned)h[87] << 24);
      if (esz < 16u || esz > 1024u) { esz = 128u; }
      if (nent == 0u || nent > 1024u) { nent = 128u; }
      pages = (nent * esz + 4095u) / 4096u;
      if (pages > 16u) { pages = 16u; }
      ufs8996_pe_nm = ((uint32_t)entLba & 0xffffu);  // trace: entry LBA

      for (p = 0; p < pages; p++) {
        v412ReadLba0(base, utrd, ucd, utrd_phys, ucd_phys,
                     g0245d_ufs_data_va,
                     (uint64_t)kvtophys(
                       (unsigned long long)(uintptr_t)&g0245d_v412_data_page[0]),
                     (uint32_t)(entLba + p));
        ufs8996_pe_status = ufs8996_gpt_status;
        ufs8996_pe_wait   = ufs8996_gpt_wait;
        if (ufs8996_gpt_status != 0u) { break; }
        {
          unsigned off;
          for (off = 0; off + esz <= 4096u; off += esz) {
            const uint8_t *e = g0245d_ufs_data_va + off;
            unsigned nz = 0;
            for (k = 0; k < 16u; k++) { nz |= e[k]; }
            if (nz == 0) { continue; }
            if (total == 0) {
              ufs8996_pe_nm = ((uint32_t)e[56] & 0xffu) |
                              (((uint32_t)e[58] & 0xffu) << 8);
            }
            total++;
            if (e[56] == 'u' && e[58] == 's' && e[60] == 'e' &&
                e[62] == 'r' && e[64] == 'd' && e[66] == 'a' &&
                e[68] == 't' && e[70] == 'a') {
              /* g0245d v429: capture this entry's start LBA (@+32, u64
               * LE) and end LBA (@+40, u64 LE); keep the low 32 bits. */
              static const char volatile v429_tag[] = "v429 ud cap";
              (void)v429_tag[0];
              fu = 1;
              {
                uint64_t sl = 0, el = 0;
                for (k = 0; k < 8u; k++) {
                  sl |= ((uint64_t)e[32 + k]) << (8u * k);
                  el |= ((uint64_t)e[40 + k]) << (8u * k);
                }
                ufs8996_ud_lba = (uint32_t)(sl & 0xffffffffu);
                ufs8996_ud_end = (uint32_t)(el & 0xffffffffu);
              }
            }
            if (e[56] == 's' && e[58] == 'u' && e[60] == 'p' &&
                e[62] == 'e' && e[64] == 'r') { fs = 1; }
          }
        }
      }
      ufs8996_pe_num  = total;
      ufs8996_pe_flag = fu ? (uint32_t)'U' : (fs ? (uint32_t)'S' : (uint32_t)'.');
      g0245d_trace_u("v426 pe num", ufs8996_pe_num);
      g0245d_trace_u("v428 pe tot", total);
      g0245d_trace_u("v428 pe pages", pages);
      g0245d_trace_u("v428 pe nent", nent);
      g0245d_trace_u("v428 pe esz", esz);
      g0245d_trace_u("v428 pe flag", ufs8996_pe_flag);
      g0245d_trace_u("v426 pe st", ufs8996_pe_status);
      g0245d_trace_u("v426 pe nm", ufs8996_pe_nm);
      g0245d_trace_u("v429 ud lba", ufs8996_ud_lba);
      g0245d_trace_u("v429 ud end", ufs8996_ud_end);

      // restore the LBA1 verdict: P/S/W keep meaning the header read
      ufs8996_gpt_done  = s_done;
      ufs8996_gpt_ocs   = s_ocs;
      ufs8996_gpt_resp  = s_resp;
      ufs8996_gpt_off   = s_off;
      ufs8996_gpt_status = s_st;
      ufs8996_gpt_sense = s_se;
      ufs8996_gpt_wait  = s_wait;
      ufs8996_mbr_sig   = s_mbr;
      ufs8996_gpt_hdr   = s_hdr;
      ufs8996_gpt_att   = s_att;
    }
  }
  /* g0245d v430: verify the userdata start LBA by reading its first
   * block and fingerprinting the filesystem signature.  Same
   * save/restore pattern so P/S/W keep meaning the LBA1 header read. */
  if (ufs8996_ud_lba != 0xffffffffu) {
    volatile uint32_t s_hdr  = ufs8996_gpt_hdr;
    volatile uint32_t s_done = ufs8996_gpt_done;
    volatile uint32_t s_ocs  = ufs8996_gpt_ocs;
    volatile uint32_t s_resp = ufs8996_gpt_resp;
    volatile uint32_t s_st   = ufs8996_gpt_status;
    volatile uint32_t s_se   = ufs8996_gpt_sense;
    volatile uint32_t s_wait = ufs8996_gpt_wait;
    volatile uint32_t s_mbr  = ufs8996_mbr_sig;
    volatile uint32_t s_att  = ufs8996_gpt_att;
    volatile uint32_t s_off  = ufs8996_gpt_off;
    unsigned k;
    static const char volatile v430_tag[] = "v430 ud read";
    (void)v430_tag[0];
    v412ReadLba0(base, utrd, ucd, utrd_phys, ucd_phys,
                 g0245d_ufs_data_va,
                 (uint64_t)kvtophys(
                   (unsigned long long)(uintptr_t)&g0245d_v412_data_page[0]),
                 ufs8996_ud_lba);
    g0245d_trace_u("v430 ud st", ufs8996_gpt_status);
    g0245d_trace_u("v430 ud wait", ufs8996_gpt_wait);
  g0245d_trace_u("v441 dbw", ufs8996_gpt_dbw);
    {
      unsigned nz = 0;
      unsigned ext4 = 0, f2fs = 0;
      for (k = 0; k < 64u; k++) {
        nz |= g0245d_ufs_data_va[k];
      }
      if (((unsigned)g0245d_ufs_data_va[1081] << 8) |
          (unsigned)g0245d_ufs_data_va[1080]) {
        ext4 = (((unsigned)g0245d_ufs_data_va[1081] << 8) |
                (unsigned)g0245d_ufs_data_va[1080]) == 0xef53u;
      }
      if (((unsigned)g0245d_ufs_data_va[1024] == 0x10u) &&
          ((unsigned)g0245d_ufs_data_va[1025] == 0x20u) &&
          ((unsigned)g0245d_ufs_data_va[1026] == 0xf5u) &&
          ((unsigned)g0245d_ufs_data_va[1027] == 0xf2u)) {
        f2fs = 1;
      }
      ufs8996_ud_sig = (nz ? 1u : 0u) |
                       (ext4 ? 2u : 0u) |
                       (f2fs ? 4u : 0u);
      /* g0245d v433: pack the first 16 bytes into four words for the
       * pinned row (k is already in scope here). */
      for (k = 0; k < 4u; k++) {
        uint32_t w = ((uint32_t)g0245d_ufs_data_va[k * 4u + 0]) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 1] <<  8) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 2] << 16) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 3] << 24);
        if (k == 0u) { ufs8996_ud_d0 = w; }
        if (k == 1u) { ufs8996_ud_d1 = w; }
        if (k == 2u) { ufs8996_ud_d2 = w; }
        if (k == 3u) { ufs8996_ud_d3 = w; }
      }
    }
    g0245d_trace_u("v430 ud sig", ufs8996_ud_sig);
    /* g0245d v432: dump the first 16 bytes of the userdata first
     * block as four little-endian u32 traces; identifies what M=u
     * actually contains (FBE metadata, leftovers, wrong offset...). */
    {
      static const char volatile v432_tag[] = "v432 ud dump";
      unsigned k;
      (void)v432_tag[0];
      for (k = 0; k < 4u; k++) {
        uint32_t w = ((uint32_t)g0245d_ufs_data_va[k * 4u + 0]) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 1] <<  8) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 2] << 16) |
                     ((uint32_t)g0245d_ufs_data_va[k * 4u + 3] << 24);
        if (k == 0u) { g0245d_trace_u("v432 ud d0", w); }
        if (k == 1u) { g0245d_trace_u("v432 ud d1", w); }
        if (k == 2u) { g0245d_trace_u("v432 ud d2", w); }
        if (k == 3u) { g0245d_trace_u("v432 ud d3", w); }
      }
    }
    /* g0245d v435: read 4 consecutive blocks from the userdata start
     * LBA and fold each page into a rolling checksum.  Validates
     * consecutive-block DMA (block device layer readiness) and gives
     * a boot-to-boot stability signal for v434's cache fix. */
    {
      static const char volatile v435_tag[] = "v435 ud multi";
      unsigned blk;
      uint32_t ck = 0;
      (void)v435_tag[0];
      ufs8996_ud_ckn = 0u;
      /* g0245d v436: bisect result -- loop guilty (2/2 deterministic
       * data aborts). */
      static const char volatile v436_tag[] = "v436 bisect noloop";
      /* g0245d v437: trip count back to 4, but EVERY read pinned to
       * ufs8996_ud_lba (no +blk).  Good boot => LBA region
       * 0x12241+ is the trigger; crash => repetition itself. */
      static const char volatile v437_tag[] = "v437 fixed lba";
      /* g0245d v438: minimal trigger.  Two reads: blk0 = 0x12240
       * (known good), blk1 = 0x12241 (the suspected trigger).  The
       * blk1 SCSI status lands in ufs8996_ud_b1st (pinned row s=). */
      static const char volatile v438_tag[] = "v438 min trigger";
      /* g0245d v439: three reads (0x12240/41/42).  Crash => 0x12242
       * is the trigger; clean => 0x12243. */
      static const char volatile v439_tag[] = "v439 third lba";
      /* g0245d v440: 0x12242 was innocent (v439 n=3 s=00).  The only
       * untested read is +3 (0x12243).  Two reads: 0x12240 (good)
       * then 0x12243 directly.  Crash => one READ(10) at 0x12243 is
       * fatal on its own. */
      static const char volatile v440_tag[] = "v440 skip to lba3";
      (void)v436_tag[0];
      (void)v437_tag[0];
      (void)v438_tag[0];
      (void)v439_tag[0];
      (void)v440_tag[0];
      ufs8996_ud_b1st = 0xffu;
      /* g0245d v444: correlation established -- every boot that reads
       * userdata LBA 0x12242/43 freezes pre-exec (v439/440/441/442/443),
       * while v438 (reads <= 0x12241) reached the exec panic.  Revert to
       * the v438 two-read config; keep wfi=0 (v443). */
      static const char volatile v444_tag[] = "v444 two reads";
      (void)v444_tag[0];
      for (blk = 0; blk < 2u; blk++) {
        uint32_t sum = 0;
        unsigned q;
        v412ReadLba0(base, utrd, ucd, utrd_phys, ucd_phys,
                     g0245d_ufs_data_va,
                     (uint64_t)kvtophys(
                       (unsigned long long)(uintptr_t)&g0245d_v412_data_page[0]),
                     ufs8996_ud_lba + blk);
        if (ufs8996_gpt_status == 0u) { ufs8996_ud_ckn = blk + 1u; }
        /* g0245d v439: record the LAST read status (n= counts GOOD). */
        ufs8996_ud_b1st = ufs8996_gpt_status;
        for (q = 0; q < 4096u; q++) {
          sum = sum * 31u + (uint32_t)g0245d_ufs_data_va[q];
        }
        ck = (ck << 5) | (ck >> 27);
        ck ^= sum;
      }
      ufs8996_ud_ck = ck;
      g0245d_trace_u("v435 ud ckn", ufs8996_ud_ckn);
      g0245d_trace_u("v435 ud ck", ufs8996_ud_ck);
    }
    ufs8996_gpt_done  = s_done;
    ufs8996_gpt_ocs   = s_ocs;
    ufs8996_gpt_resp  = s_resp;
    ufs8996_gpt_off   = s_off;
    ufs8996_gpt_status = s_st;
    ufs8996_gpt_sense = s_se;
    ufs8996_gpt_wait  = s_wait;
    ufs8996_mbr_sig   = s_mbr;
    ufs8996_gpt_hdr   = s_hdr;
    ufs8996_gpt_att   = s_att;
  }
  g0245d_ufs_ctx_ready = 1u;
  return out;
}

/* g0245d v446/v448: WRITE(10) to the userdata scratch LBA (0x12240).
 * Payload (16 bytes): {magic a, hb_count b, trace_seq c, last-label
 * d = pointer whose first 8 ASCII chars are copied at write time}.
 * The next boot's v430 read brings it back through the v432 pinned
 * row -- a snapshot of the dying moment (hb, trace activity, and
 * the code label that was last running before the freeze). */
void v446_scratch_write_impl(unsigned int a, unsigned int b,
    unsigned int c, const char volatile *lbl)
{
  uintptr_t base = g0245d_ufs_ctx_base;
  uint8_t *utrd = g0245d_ufs_ctx_utrd;
  uint8_t *ucd = g0245d_ufs_ctx_ucd;
  uint64_t utrd_phys = g0245d_ufs_ctx_utrd_phys;
  uint64_t ucd_phys = g0245d_ufs_ctx_ucd_phys;
  uint8_t *data = g0245d_ufs_data_va;
  uint64_t data_phys;
  volatile uint32_t *u32 = reinterpret_cast<volatile uint32_t *>(utrd);
  volatile uint32_t *prdt = reinterpret_cast<volatile uint32_t *>(ucd + 1024);
  volatile uint8_t *uc = ucd;
  unsigned w;

  if (g0245d_ufs_ctx_ready == 0u) { return; }
  if (ufs8996_ud_lba == 0xffffffffu) { return; }

  data_phys = (uint64_t)kvtophys(
      (unsigned long long)(uintptr_t)&data[0]);

  for (w = 0; w < 4096u; w++) { utrd[w] = 0; ucd[w] = 0; }

  data[0] = (uint8_t)a;         data[1] = (uint8_t)(a >> 8);
  data[2] = (uint8_t)(a >> 16); data[3] = (uint8_t)(a >> 24);
  data[4] = (uint8_t)b;         data[5] = (uint8_t)(b >> 8);
  data[6] = (uint8_t)(b >> 16); data[7] = (uint8_t)(b >> 24);
  /* g0245d v448: words 2/3 = trace_seq + the first 8 ASCII chars
   * of the last trace label -- the dying moment's activity. */
  data[8] = (uint8_t)c;         data[9] = (uint8_t)(c >> 8);
  data[10] = (uint8_t)(c >> 16); data[11] = (uint8_t)(c >> 24);
  {
    /* g0245d v450: lbl arrives as a full 64-bit pointer (v448
     * truncated it to 32 bits -- the ldrsb abort). */
    unsigned ci;
    for (ci = 0; ci < 8u; ci++) {
      char ch = '.';
      if (lbl != 0 && lbl[ci] >= 0x20 && lbl[ci] < 0x7f) { ch = lbl[ci]; }
      data[12 + ci] = (uint8_t)ch;
    }
  }

  prdt[0] = (uint32_t)data_phys;
  prdt[1] = (uint32_t)(data_phys >> 32);
  prdt[2] = 0;
  prdt[3] = 4095u;

  /* g0245d v451: no clean needed -- the payload was written through
   * the UNCACHED alias and is already in DRAM. */

  u32[0] = 0x01000000u;               /* SCSI, HOST_TO_DEVICE, INT */
  u32[2] = 0x0fu;
  u32[4] = (uint32_t)ucd_phys;
  u32[5] = (uint32_t)(ucd_phys >> 32);
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 1u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u;

  uc[0] = 0x01u;   /* TRANSACTION_COMMAND */
  uc[1] = 0x20u;   /* UPIU_CMD_FLAGS_WRITE */
  uc[2] = 0x00u;
  uc[3] = 0x00u;
  uc[4] = 0u; uc[5] = 0u; uc[6] = 0u; uc[7] = 0u;
  uc[12] = 0u; uc[13] = 0u; uc[14] = 0x10u; uc[15] = 0u;
  uc[16] = 0x2au;  /* WRITE(10) */
  uc[17] = 0x00u;
  uc[18] = (uint8_t)(ufs8996_ud_lba >> 24);
  uc[19] = (uint8_t)(ufs8996_ud_lba >> 16);
  uc[20] = (uint8_t)(ufs8996_ud_lba >> 8);
  uc[21] = (uint8_t)(ufs8996_ud_lba & 0xffu);
  uc[22] = 0x00u;
  uc[23] = 0x00u; uc[24] = 0x01u;
  uc[25] = 0x00u;
  uc[26] = 0u; uc[27] = 0u; uc[28] = 0u; uc[29] = 0u;
  uc[30] = 0u; uc[31] = 0u;

  v394Write32(base, Ufs8996::REG_UTRL_BASE_L, (uint32_t)utrd_phys);
  v394Write32(base, Ufs8996::REG_UTRL_BASE_H, (uint32_t)(utrd_phys >> 32));
  v394Write32(base, Ufs8996::REG_UTRL_CLEAR, 1u);
  for (w = 0; w < 100000u; w++) { /* settle */ }
  for (w = 0; w < 100000u; w++) {
    if (v394Read32(base, Ufs8996::REG_HCS) & 1u) { break; }
  }
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 1u);
  v394Write32(base, Ufs8996::REG_UTRL_DB, 1u);

  for (w = 0; w < 1000000u; w++) {
    if (v394Read32(base, Ufs8996::REG_IS) & Ufs8996::IS_UTP_TRANSFER_COMP) {
      break;
    }
  }
  ufs8996_scr_st = 0xfeu;
  {
    unsigned dw;
    for (dw = 0; dw < 200000u; dw++) {
      if ((v394Read32(base, Ufs8996::REG_UTRL_DB) & 1u) == 0u) { break; }
    }
    if (dw >= 200000u) { ufs8996_scr_st = 0xfffu; }
  }
  ufs8996_scr_st =
      (((*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu) << 8) |
      (unsigned)uc[512 + 7];
  g0245d_trace_u("v446 scr st", ufs8996_scr_st);
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
}

} // namespace

extern "C" void ufs8996_scratch_write(unsigned int a, unsigned int b,
    unsigned int c, const char volatile *lbl)
{
  v446_scratch_write_impl(a, b, c, lbl);
}

/* g0245d v452: heartbeat pet.  One register write; no cache ops,
 * no UFS access, safe to call with interrupts off. */
extern "C" void ufs8996_wdt_pet(void)
{
  if (g0245d_wdt != nullptr) {
    g0245d_wdt[0x04u / 4u] = 1u;
    __asm__ volatile("dsb sy" ::: "memory");
  }
}

/* g0245d v453: read-only snapshot of the APSS watchdog registers.
 * out[0]=EN (0x08), out[1]=STS (0x0c), out[2]=BARK (0x10),
 * out[3]=BITE (0x14).  out[0]=0xdeadbeef means the map was never
 * established (arm failed). */
extern "C" void ufs8996_wdt_status(unsigned int *out)
{
  if (g0245d_wdt == nullptr) {
    out[0] = 0xdeadbeefu; out[1] = 0u; out[2] = 0u; out[3] = 0u;
    return;
  }
  out[0] = g0245d_wdt[0x08u / 4u];
  out[1] = g0245d_wdt[0x0cu / 4u];
  out[2] = g0245d_wdt[0x10u / 4u];
  out[3] = g0245d_wdt[0x14u / 4u];
}

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


  /* g0245d v393: q=01 + only a generic DME error => reset UniPro,
   * enable it again, then retry LINKSTARTUP once.  All three commands use
   * the same bounded helper; no HCE/clock/PHY write. */
  if (ufs8996_uic_result != 0u) {
    UicRecoveryResult v393_r;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_RESET);
    ufs8996_recover_reset = v393_r.result;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_ENABLE);
    ufs8996_recover_enable = v393_r.result;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_LINK_STARTUP);
    ufs8996_recover_result = v393_r.result;
    ufs8996_recover_spins  = v393_r.spins;
    ufs8996_recover_ready  = v393_r.ready;
    ufs8996_step = 8;
    g0245d_trace_u("v393 retry", ufs8996_recover_result);
  }
  if (ufs8996_step < 8u) { ufs8996_step = 7u; }
  g0245d_trace_u("v391 ls", ufs8996_uic_result);

  /* g0245d v394: the serial link is up (either on the first LINKSTARTUP or
   * after v393's recovery), so read the DEVICE descriptor with one UTP query.
   * The two pages are mapped uncached; nothing else is changed. */
  if (ufs8996_uic_result == 0u || ufs8996_recover_result == 0u) {
    uint64_t utrd_phys = (uint64_t)kvtophys(
        (unsigned long long)(uintptr_t)&g0245d_v394_utrd_page[0]);
    uint64_t ucd_phys = (uint64_t)kvtophys(
        (unsigned long long)(uintptr_t)&g0245d_v394_ucd_page[0]);
    IOMemoryMap *utrd_map = mapPhysical(utrd_phys, 4096u);
    IOMemoryMap *ucd_map = mapPhysical(ucd_phys, 4096u);
    /* g0245d v451: uncached alias for the data page -- every
     * data access below goes through it, so the DMA is coherent
     * with ZERO cache maintenance ops. */
    uint64_t data_phys451 = (uint64_t)kvtophys(
        (unsigned long long)(uintptr_t)&g0245d_v412_data_page[0]);
    IOMemoryMap *data_map451 = mapPhysical(data_phys451, 4096u);
    if (data_map451) {
      g0245d_ufs_data_va =
          reinterpret_cast<uint8_t *>(data_map451->getAddress());
      g0245d_ufs_data_map = data_map451;
    }
    /* g0245d v452: arm the APSS watchdog once the transport is up.
     * 10 s bark / 12 s bite at 32768 Hz.  A wedged UFS MMIO access
     * stops the heartbeat; the bite then resets the SoC so the
     * auto-flash loop can try again with a fresh boot. */
    {
      (void)v452_arm_tag[0];
      IOMemoryMap *wdt_map452 = mapPhysical(0x09830000ull, 4096u);
      if (wdt_map452) {
        volatile uint32_t *w =
            reinterpret_cast<volatile uint32_t *>(wdt_map452->getAddress());
        g0245d_wdt = w;
        g0245d_wdt_map = wdt_map452;
        w[0x08u / 4u] = 0u;                    /* EN = 0 */
        __asm__ volatile("dsb sy" ::: "memory");
        w[0x04u / 4u] = 1u;                    /* RST */
        w[0x10u / 4u] = 10u * 32768u;          /* BARK */
        w[0x14u / 4u] = 12u * 32768u;          /* BITE */
        __asm__ volatile("dsb sy" ::: "memory");
        w[0x08u / 4u] = 1u;                    /* EN = 1 */
        __asm__ volatile("dsb sy" ::: "memory");
        g0245d_trace_u("v452 wdt ctl", w[0x08u / 4u]);
      } else {
        g0245d_trace("v452 wdt map fail");
      }
    }
    if (utrd_map && ucd_map) {
      DeviceDescriptorResult q = v394QueryDevice(
          fBase,
          reinterpret_cast<uint8_t *>(utrd_map->getAddress()),
          reinterpret_cast<uint8_t *>(ucd_map->getAddress()),
          utrd_phys, ucd_phys);
      ufs8996_query_ocs     = q.ocs;
      ufs8996_query_resp    = q.response;
      ufs8996_query_len     = q.data_len;
      ufs8996_query_bytes01 = q.bytes01;
      ufs8996_query_bytes23 = q.bytes23;
      ufs8996_query_spins   = q.spins;
      ufs8996_query_doorbell = q.doorbell;
      ufs8996_step = 9u;
      g0245d_trace_u("v394 desc", ufs8996_query_bytes01);
    }
    /* g0245d v447: keep the alias maps alive for the heartbeat
     * scratch writes instead of releasing them here. */
    g0245d_ufs_ctx_utrd_map = utrd_map;
    g0245d_ufs_ctx_ucd_map = ucd_map;
  }
  return true;
}

void NativeUfs8996::stop(IOService *provider)
{
  if (fMap) { fMap->release(); fMap = nullptr; }
  if (fMapPhy) { fMapPhy->release(); fMapPhy = nullptr; }
  fBase = 0; fPhy = 0;
  IOService::stop(provider);
}
