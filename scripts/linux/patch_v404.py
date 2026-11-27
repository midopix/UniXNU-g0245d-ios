#!/usr/bin/env python3
"""g0245d v404: wake the device from UFS-PowerDown before descriptor reads.

v403 photo: 26 v403 o=0 t=3600 q=0001 r=f6 d=40 a=0000 s=9 p=000540 i=05.
Even after the fDeviceInit sequence the DEVICE descriptor read still
returns QueryResp=0xF6 (ParamNotReadable).  ShengUfs documents exactly
this device state on the same SoC family: at probe time the UFS device
sits in UFS-PowerDown (bCurrentPowerMode=0x33), answers NOP/attribute
queries, but reports descriptors PARAM NOT READABLE, and every LU
returns NOT READY.  Linux resumes it with START STOP UNIT (power
condition ACTIVE) to the UFS Device W-LUN 0xD0
(ufshcd_set_dev_pwr_mode); ShengUfs does the same before its first
command.

v404 single suspect point: wake the device with SSU (SCSI command,
CDB 1B 00 00 00 10 00, LUN 0xD0) between fDeviceInit and the
descriptor read.  Read-only diagnostics around it: READ ATTRIBUTE
bCurrentPowerMode (op=0x03 idn=0x02) before and after the SSU, and the
SSU result (ocs<<16|resp<<8|scsi) pinned on the row.  Only boot is
flashed.
"""
import re
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
if "v404SsuWake" in src:
    print("patch_v404: driver SSU wake already present -- skip")
else:
    anchor = (
        "// g0245d v403: fDeviceInit sequence diagnostics.\n"
        "volatile uint32_t ufs8996_query_setresp   = 0xfe;\n"
        "volatile uint32_t ufs8996_query_readresp  = 0xfe;\n"
        "volatile uint32_t ufs8996_query_initflag  = 0xffffffffu;\n"
        "volatile uint32_t ufs8996_query_initpolls = 0xffffffffu;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v404: v403 globals anchor found %d times" % n)
    src = src.replace(
        anchor,
        anchor
        + "// g0245d v404: power state + SSU wake diagnostics.\n"
        + "volatile uint32_t ufs8996_query_pmbefore = 0xffu;\n"
        + "volatile uint32_t ufs8996_query_pm       = 0xffu;\n"
        + "volatile uint32_t ufs8996_query_ssu      = 0xffffffu;\n",
        1,
    )

    fn_anchor = "static DeviceDescriptorResult v394QueryDevice(\n"
    n = src.count(fn_anchor)
    if n != 1:
        sys.exit("patch_v404: query function anchor found %d times" % n)
    helper = """// g0245d v404: START STOP UNIT (power condition ACTIVE) to the UFS
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

"""
    src = src.replace(fn_anchor, helper + fn_anchor, 1)

    seq_anchor = (
        '    g0245d_trace_u("v403 setresp", ufs8996_query_setresp);\n'
        '    g0245d_trace_u("v403 initflag", ufs8996_query_initflag);\n'
        '    g0245d_trace_u("v403 initpolls", ufs8996_query_initpolls);\n'
        "  }\n"
    )
    n = src.count(seq_anchor)
    if n != 1:
        sys.exit("patch_v404: fDeviceInit trace anchor found %d times" % n)
    seq = seq_anchor + """    // g0245d v404: read bCurrentPowerMode, wake the device with SSU
    // (power condition ACTIVE) to W-LUN 0xD0, read it again.
    v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                  0x03u, 0x02u, &ufs8996_query_readresp, &v403_value);
    ufs8996_query_pmbefore = v403_value & 0xffu;
    g0245d_trace_u("v404 pmbefore", ufs8996_query_pmbefore);
    v404SsuWake(base, utrd, ucd, utrd_phys, ucd_phys);
    v403FlagQuery(base, utrd, ucd, utrd_phys, ucd_phys,
                  0x03u, 0x02u, &ufs8996_query_readresp, &v403_value);
    ufs8996_query_pm = v403_value & 0xffu;
    g0245d_trace_u("v404 pm", ufs8996_query_pm);
"""
    src = src.replace(seq_anchor, seq, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v404: SSU wake sequence installed")

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
old_row = '    "v403 o=0 t=ffff q=ffff r=00 d=00 a=0000 s=9 p=0f4240 i=01";'
new_row = '    "v404 o=0 t=ff r=00 d=00 a=0000 ss=ffffff pm=ff s=9 i=01";'
if '"v404 o=0 t=' in bs:
    print("patch_v404: bsdinit row already converted -- skip")
else:
    n = bs.count(old_row)
    if n != 1:
        # Row already in a newer format: v404 was applied before.
        print("patch_v404: v403 row anchor absent (row already newer) -- skip")
    else:
        bs = bs.replace(old_row, new_row, 1)
        pat = re.compile(
            r"\t\t\tv394_buf\[7\] = \(ufs8996_query_ocs.*?"
            r"ufs8996_query_is & 0xf\];",
            re.S,
        )
        if not pat.search(bs):
            sys.exit("patch_v404: pinned-row fill block not found")
        new_fill = """\t\t\textern volatile unsigned int ufs8996_query_ssu;
\t\t\textern volatile unsigned int ufs8996_query_pm;
\t\t\tv394_buf[7] = (ufs8996_query_ocs < 16)
\t\t\t    ? hx[ufs8996_query_ocs] : '?';
\t\t\tv394_buf[11] = hx[(ufs8996_query_type >> 4) & 0xf];
\t\t\tv394_buf[12] = hx[ufs8996_query_type & 0xf];
\t\t\tv394_buf[16] = hx[(ufs8996_query_resp >> 4) & 0xf];
\t\t\tv394_buf[17] = hx[ufs8996_query_resp & 0xf];
\t\t\tv394_buf[21] = hx[(ufs8996_query_len >> 4) & 0xf];
\t\t\tv394_buf[22] = hx[ufs8996_query_len & 0xf];
\t\t\tv394_buf[26] = hx[(ufs8996_query_bytes01 >> 12) & 0xf];
\t\t\tv394_buf[27] = hx[(ufs8996_query_bytes01 >> 8) & 0xf];
\t\t\tv394_buf[28] = hx[(ufs8996_query_bytes01 >> 4) & 0xf];
\t\t\tv394_buf[29] = hx[ufs8996_query_bytes01 & 0xf];
\t\t\t{
\t\t\t\tunsigned int v = ufs8996_query_ssu & 0xffffffu;
\t\t\t\tunsigned int k;
\t\t\t\tfor (k = 0; k < 6; k++)
\t\t\t\t\tv394_buf[39 - k] = hx[(v >> (4 * k)) & 0xf];
\t\t\t}
\t\t\tv394_buf[44] = hx[(ufs8996_query_pm >> 4) & 0xf];
\t\t\tv394_buf[45] = hx[ufs8996_query_pm & 0xf];
\t\t\tv394_buf[49] = (ufs8996_step < 10)
\t\t\t    ? (char)('0' + ufs8996_step) : '?';
\t\t\tv394_buf[53] = hx[(ufs8996_query_is >> 4) & 0xf];
\t\t\tv394_buf[54] = hx[ufs8996_query_is & 0xf];"""
        bs = pat.sub(lambda _: new_fill, bs, count=1)
        BSD.write_text(bs, encoding="utf-8")
        print("patch_v404: bsdinit pinned row converted to v404 layout")

print("patch_v404: done")
