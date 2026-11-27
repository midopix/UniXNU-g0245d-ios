#!/usr/bin/env python3
"""g0245d v403: run the fDeviceInit sequence before the descriptor read.

v402 photo: 26 v402 o=0 t=3600 q=0001 r=f6 d=40 a=0000 s=9 p=000543 i=05.
Per UFS 4.0 spec / EDK2 (Table 10.46): 0x36 IS the QUERY RESPONSE
transaction code (REJECT is 0x3F; the local refs/ufs-linux-3.18 ufs.h
enum mis-copies these).  rsp[6]=0xF6 is QueryResp code
ParamNotReadable, byte5=0x01 is the QueryFunc echo: the whole query
pipeline works end-to-end.  The device says "parameter not readable"
because Linux ufshcd_complete_dev_init() sets fDeviceInit (SET FLAG
op=0x06 idn=0x01) and polls READ FLAG (op=0x05) until the device
clears it, BEFORE any descriptor read.  We skipped that.

v403 single suspect point: run the fDeviceInit sequence first, then
issue the same READ DESC(DEVICE) query.  Row layout unchanged (it
reports the post-init READ DESC); set/read flag results go to the
trace ring.  Only boot is flashed.
"""
import sys
from pathlib import Path

W = Path(__import__("os").environ["XNU_WORK"])
CPP = Path(__import__("os").environ["G0245D_DEV"]) / "drivers/NativeUfs8996/NativeUfs8996.cpp"
BSD = W / "bsd" / "kern" / "bsd_init.c"
for f in (CPP, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------ driver edits
src = CPP.read_text(encoding="utf-8")
if "v403FlagQuery" in src:
    print("patch_v403: driver fDeviceInit sequence already present -- skip")
else:
    anchor = (
        "// g0245d v402: response UPIU header dump (bytes 0-1 and 4-5\n"
        "// of the 512-byte response area) pinned on the console row.\n"
        "volatile uint32_t ufs8996_query_type = 0xffff;\n"
        "volatile uint32_t ufs8996_query_b45  = 0xffff;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v403: v402 globals anchor found %d times" % n)
    src = src.replace(
        anchor,
        anchor
        + "// g0245d v403: fDeviceInit sequence diagnostics.\n"
        + "volatile uint32_t ufs8996_query_setresp   = 0xfe;\n"
        + "volatile uint32_t ufs8996_query_readresp  = 0xfe;\n"
        + "volatile uint32_t ufs8996_query_initflag  = 0xffffffffu;\n"
        + "volatile uint32_t ufs8996_query_initpolls = 0xffffffffu;\n",
        1,
    )

    fn_anchor = "static DeviceDescriptorResult v394QueryDevice(\n"
    n = src.count(fn_anchor)
    if n != 1:
        sys.exit("patch_v403: query function anchor found %d times" % n)
    helper = """// g0245d v403: generic flag query (SET/READ FLAG).  Same UTRD, UTRL
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
  v403_ucd[5] = 0x01u;               // STANDARD_READ_REQUEST
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

"""
    src = src.replace(fn_anchor, helper + fn_anchor, 1)

    seq_anchor = (
        "  out.spins = 1000000u;\n"
        "  out.doorbell = 0u;\n"
        "\n"
        "  for (unsigned int i = 0; i < 4096u; i++) "
        "{ utrd[i] = 0; ucd[i] = 0; }\n"
    )
    n = src.count(seq_anchor)
    if n != 1:
        sys.exit("patch_v403: query prologue anchor found %d times" % n)
    seq = """  out.spins = 1000000u;
  out.doorbell = 0u;

  // g0245d v403: run the fDeviceInit sequence first (Linux
  // ufshcd_complete_dev_init): SET FLAG fDeviceInit, then poll READ
  // FLAG until the device clears it.  Without it the device answers
  // the descriptor read with rsp=0xF6 (PARAM NOT READABLE).
  {
    uint32_t v403_value = 0;
    unsigned int p;
    v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                  0x06u, 0x01u, &ufs8996_query_setresp, &v403_value);
    for (p = 0; p < 1000u; p++) {
      v403_value = 0xffffffffu;
      ufs8996_query_initpolls = p;
      v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                    0x05u, 0x01u,
                    &ufs8996_query_readresp, &v403_value);
      ufs8996_query_initflag = v403_value & 0xffu;
      if (ufs8996_query_initflag == 0u) { break; }
    }
    g0245d_trace_u("v403 setresp", ufs8996_query_setresp);
    g0245d_trace_u("v403 initflag", ufs8996_query_initflag);
    g0245d_trace_u("v403 initpolls", ufs8996_query_initpolls);
  }

  for (unsigned int i = 0; i < 4096u; i++) { utrd[i] = 0; ucd[i] = 0; }
"""
    src = src.replace(seq_anchor, seq, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v403: fDeviceInit sequence installed")

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
old_row = '    "v402 o=0 t=ffff q=ffff r=00 d=00 a=0000 s=9 p=0f4240 i=01";'
new_row = '    "v403 o=0 t=ffff q=ffff r=00 d=00 a=0000 s=9 p=0f4240 i=01";'
if '"v403 o=0 t=' in bs:
    print("patch_v403: bsdinit row already relabelled -- skip")
else:
    n = bs.count(old_row)
    if n != 1:
        sys.exit("patch_v403: v402 row anchor found %d times" % n)
    bs = bs.replace(old_row, new_row, 1)
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v403: bsdinit pinned row relabelled v403")

print("patch_v403: done")
