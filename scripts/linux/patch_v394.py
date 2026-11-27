#!/usr/bin/env python3
"""g0245d v394: C2 step 3 -- read the UFS device descriptor over UTP.

v393 verdict (photo 2026-11-27 09:27):
    v393 a=00000000 b=00000000 r=00000000 d=0000a1e1 q=1 s=7

DME_RESET and DME_ENABLE both returned 00, and the retried DME_LINKSTARTUP
also returned 00 after 0xa1e1 UCCS polls.  The serial link is UP.
(The displayed s=7 is a cosmetic bug: v393 set step=8 but the inherited
v391 line `ufs8996_step = 7;` ran afterwards and overwrote it.)

v394 changes exactly one suspect point: submit one UTP QUERY REQUEST UPIU
(READ_DESC, idn=DEVICE=0x00, length=64) through a single-slot UTRD/UCD and
pin the result bytes on a short console row.  This is the first real device
transaction; no SCSI command, no block device, no filesystem change.

New pinned row:

    v394 o=0 r=00 a=0000 b=0000 d=00 s=9

- o = UTRD OCS (0 = success, f = timed out)
- r = query response code (0 = success)
- a = descriptor bytes 0/1 (length, descriptor type)
- b = descriptor bytes 2/3
- d = response data segment length (64 = device descriptor)
- s = driver step (9 = descriptor query attempted)

Idempotent via "g0245d v394" markers.
"""
import os
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
DEV = Path(os.environ.get(
    "G0245D_DEV",
    str(Path(__file__).resolve().parents[2]),
))
HDR = DEV / "drivers" / "NativeUfs8996" / "Ufs8996Regs.h"
CPP = DEV / "drivers" / "NativeUfs8996" / "NativeUfs8996.cpp"
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
for f in (HDR, CPP, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------ header constants
src = HDR.read_text(encoding="utf-8")
if "g0245d v394" not in src:
    anchor = "constexpr unsigned UIC_DME_RESET   = 0x14u;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: header tail anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "\n"
        "// UTP transfer list (g0245d v394; msm-3.18 ufshci.h).\n"
        "constexpr unsigned REG_UTRL_BASE_L = 0x50;\n"
        "constexpr unsigned REG_UTRL_BASE_H = 0x54;\n"
        "constexpr unsigned REG_UTRL_DB     = 0x58;\n"
        "constexpr unsigned REG_UTRL_CLEAR  = 0x5c;\n"
        "constexpr unsigned REG_UTRL_RUN    = 0x60;\n"
        "constexpr unsigned IS_UTP_TRANSFER_COMP = (1u << 0);\n", 1)
    HDR.write_text(src, encoding="utf-8")
    print("patch_v394: UTP transfer-list constants added")
else:
    print("patch_v394: header already patched -- skip")

# ------------------------------------------------------------- driver changes
src = CPP.read_text(encoding="utf-8")
if "g0245d v394" not in src:
    # 1) kvtophys declaration
    anchor = 'extern "C" void g0245d_trace_u(const char *label, unsigned int value);\n'
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: extern anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        'extern "C" unsigned long long kvtophys(unsigned long long va);\n', 1)

    # 2) one-page UTRD/UCD buffers + bounded query helper, before namespace end
    anchor = "} // namespace\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: namespace tail anchor found %d times" % n)
    helper = r'''
// g0245d v394: one-page, page-aligned UTRD/UCD buffers.  mapPhysical() gives
// an uncached alias so the CPU sees what the controller DMA'd.
alignas(4096) static uint8_t g0245d_v394_utrd_page[4096];
alignas(4096) static uint8_t g0245d_v394_ucd_page[4096];

struct DeviceDescriptorResult {
  uint32_t ocs;
  uint32_t response;
  uint32_t data_len;
  uint32_t bytes01;
  uint32_t bytes23;
  uint32_t spins;
};

static inline void v394Write32(uintptr_t base, unsigned offset, uint32_t value)
{
  *reinterpret_cast<volatile uint32_t *>(base + offset) = value;
}

static inline uint32_t v394Read32(uintptr_t base, unsigned offset)
{
  return *reinterpret_cast<volatile uint32_t *>(base + offset);
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

  for (unsigned int i = 0; i < 4096u; i++) { utrd[i] = 0; ucd[i] = 0; }

  // UTRD slot 0: device-management command, no data, OCS invalid.
  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x20000000u;
  *reinterpret_cast<volatile uint32_t *>(utrd + 8) = 0x0fu;
  *reinterpret_cast<volatile uint32_t *>(utrd + 16) = (uint32_t)ucd_phys;
  *reinterpret_cast<volatile uint32_t *>(utrd + 20) = (uint32_t)(ucd_phys >> 32);
  // response_upiu_offset/length and prdt offset are all in dwords.
  *reinterpret_cast<volatile uint16_t *>(utrd + 24) = 128u; // 512 >> 2
  *reinterpret_cast<volatile uint16_t *>(utrd + 26) = 128u; // 512 >> 2
  *reinterpret_cast<volatile uint16_t *>(utrd + 28) = 0u;
  *reinterpret_cast<volatile uint16_t *>(utrd + 30) = 256u; // 1024 >> 2

  // Query Request UPIU header (network byte order).
  ucd[0] = 1u;                       // task tag
  ucd[1] = 0u;                       // LUN
  ucd[2] = 0u;                       // flags: no data
  ucd[3] = 0x16u;                    // QUERY REQUEST
  ucd[5] = 0x01u;                    // standard read request
  ucd[10] = 0u; ucd[11] = 64u;       // data segment length
  // Query Request fields at offset 12.
  ucd[12] = 0x01u;                   // READ_DESC
  ucd[13] = 0x00u;                   // DEVICE descriptor
  ucd[14] = 0u; ucd[15] = 0u;
  ucd[18] = 0u; ucd[19] = 64u;       // descriptor buffer length

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
  if (out.spins == 1000000u) {
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
  v394Write32(base, Ufs8996::REG_IS, Ufs8996::IS_UTP_TRANSFER_COMP);

  out.ocs = (*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu;
  out.response = ucd[512 + 5];
  out.data_len = ((uint32_t)ucd[512 + 10] << 8) | ucd[512 + 11];
  out.bytes01 = ((uint32_t)ucd[512 + 32] << 8) | ucd[512 + 33];
  out.bytes23 = ((uint32_t)ucd[512 + 34] << 8) | ucd[512 + 35];
  v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
  return out;
}
'''
    src = src.replace(anchor, helper + anchor, 1)

    # 3) result globals
    anchor = "volatile uint32_t ufs8996_recover_ready  = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v394: device-descriptor query result.\n"
        "volatile uint32_t ufs8996_query_ocs     = 0xf;\n"
        "volatile uint32_t ufs8996_query_resp    = 0;\n"
        "volatile uint32_t ufs8996_query_len     = 0;\n"
        "volatile uint32_t ufs8996_query_bytes01 = 0;\n"
        "volatile uint32_t ufs8996_query_bytes23 = 0;\n"
        "volatile uint32_t ufs8996_query_spins   = 0;\n", 1)

    # 4) fix v393's cosmetic step overwrite, then submit the query if link is up
    anchor = (
        "    g0245d_trace_u(\"v393 retry\", ufs8996_recover_result);\n"
        "  }\n"
        "  ufs8996_step = 7;\n"
        "  g0245d_trace_u(\"v391 ls\", ufs8996_uic_result);\n"
        "  return true;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: v393 tail anchor found %d times" % n)
    inject = r'''    g0245d_trace_u("v393 retry", ufs8996_recover_result);
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
      ufs8996_step = 9u;
      g0245d_trace_u("v394 desc", ufs8996_query_bytes01);
    }
    if (utrd_map) { utrd_map->release(); }
    if (ucd_map) { ucd_map->release(); }
  }
  return true;
'''
    src = src.replace(anchor, inject, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v394: UTP device-descriptor query added")
else:
    print("patch_v394: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v394" not in src:
    anchor = (
        "\t\t{ extern void g0245d_probe(const char *);\n"
        "\t\t  g0245d_probe(v393_buf); }\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v394: v393 row tail anchor in bsd_init.c found %d times" % n)
    probe = r'''
	/* g0245d v394: UTP READ_DESC(DEVICE) result. */
	{
		static char v394_buf[] = "v394 o=0 r=00 a=0000 b=0000 d=00 s=9";
		extern volatile unsigned int ufs8996_query_ocs;
		extern volatile unsigned int ufs8996_query_resp;
		extern volatile unsigned int ufs8996_query_len;
		extern volatile unsigned int ufs8996_query_bytes01;
		extern volatile unsigned int ufs8996_query_bytes23;
		extern volatile unsigned int ufs8996_step;
		v394_buf[7] = (ufs8996_query_ocs < 16)
		    ? "0123456789abcdef"[ufs8996_query_ocs] : '?';
		v394_buf[11] =
		    "0123456789abcdef"[(ufs8996_query_resp >> 4) & 0xf];
		v394_buf[12] =
		    "0123456789abcdef"[ufs8996_query_resp & 0xf];
		v394_buf[16] =
		    "0123456789abcdef"[(ufs8996_query_bytes01 >> 12) & 0xf];
		v394_buf[17] =
		    "0123456789abcdef"[(ufs8996_query_bytes01 >> 8) & 0xf];
		v394_buf[18] =
		    "0123456789abcdef"[(ufs8996_query_bytes01 >> 4) & 0xf];
		v394_buf[19] =
		    "0123456789abcdef"[ufs8996_query_bytes01 & 0xf];
		v394_buf[23] =
		    "0123456789abcdef"[(ufs8996_query_bytes23 >> 12) & 0xf];
		v394_buf[24] =
		    "0123456789abcdef"[(ufs8996_query_bytes23 >> 8) & 0xf];
		v394_buf[25] =
		    "0123456789abcdef"[(ufs8996_query_bytes23 >> 4) & 0xf];
		v394_buf[26] =
		    "0123456789abcdef"[ufs8996_query_bytes23 & 0xf];
		v394_buf[30] =
		    "0123456789abcdef"[(ufs8996_query_len >> 4) & 0xf];
		v394_buf[31] =
		    "0123456789abcdef"[ufs8996_query_len & 0xf];
		v394_buf[35] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v394_buf); }
	}
'''
    src = src.replace(anchor, anchor + probe, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v394: bsdinit pinned-row v394 probe inserted")
else:
    print("patch_v394: bsd_init.c already patched -- skip")

print("patch_v394: done")
