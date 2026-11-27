#!/usr/bin/env python3
"""g0245d v405: run fDeviceInit while ACTIVE, stop trusting failed polls.

v404 photo: 26 v404 o=0 t=00 r=f6 d=40 a=0000 ss=000102 pm=11 s=9 i=05.
The SSU wake worked -- the SCSI command path completed (ocs=0,
rsp[6]=0x01, rsp[7]=0x02 CHECK CONDITION) and bCurrentPowerMode now
reads 0x11 (Active).  But the descriptor read STILL returns
ParamNotReadable, and the t field only printed rsp[1] (field bug).

Prime suspect: the fDeviceInit sequence ran while the device was still
in PowerDown, where queries fail with 0xF6 -- and the poll loop read
the failed query's zero value field as "flag cleared".  v405:
1. move SET FLAG fDeviceInit + poll to AFTER the SSU wake;
2. only trust the flag when QueryResp==0x00 (SUCCESS);
3. second pinned row (v405b) with set/flag/polls/pm-before/idn-echo so
   no diagnostic scrolls away again;
4. row A t field now prints rsp[0] (transaction type).
Read-only besides the reordering.  Only boot is flashed.
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
if "v405 initflag" in src:
    print("patch_v405: driver already reordered -- skip")
else:
    anchor = (
        "volatile uint32_t ufs8996_query_pm       = 0xffu;\n"
        "volatile uint32_t ufs8996_query_ssu      = 0xffffffu;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v405: v404 globals anchor found %d times" % n)
    src = src.replace(
        anchor,
        anchor
        + "// g0245d v405: final READ DESC response TSF echo (idn byte).\n"
        + "volatile uint32_t ufs8996_query_echoidn  = 0xffu;\n",
        1,
    )

    # 1) remove the v403 fDeviceInit block from before the zero loop
    v403_block = """  // g0245d v403: run the fDeviceInit sequence first (Linux
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
"""
    n = src.count(v403_block)
    if n != 1:
        sys.exit("patch_v405: v403 block found %d times" % n)
    src = src.replace(v403_block, "", 1)

    # 2) insert the reordered fDeviceInit after the v404 PM block
    v404_end = (
        '      g0245d_trace_u("v404 pm", ufs8996_query_pm);\n'
        "    }\n"
    )
    n = src.count(v404_end)
    if n != 1:
        sys.exit("patch_v405: v404 PM block end found %d times" % n)
    v405_seq = v404_end + """    // g0245d v405: fDeviceInit must run while the device is ACTIVE.
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
"""
    src = src.replace(v404_end, v405_seq, 1)

    # 3) capture the idn echo byte of the final READ DESC response
    resp_anchor = (
        "  ufs8996_query_b45 =\n"
        "      ((uint32_t)v395_ucd[512 + 4] << 8) | v395_ucd[512 + 5];\n"
    )
    n = src.count(resp_anchor)
    if n != 1:
        sys.exit("patch_v405: b45 anchor found %d times" % n)
    src = src.replace(
        resp_anchor,
        resp_anchor
        + "  ufs8996_query_echoidn = v395_ucd[512 + 13];\n",
        1,
    )
    CPP.write_text(src, encoding="utf-8")
    print("patch_v405: driver reordered, poll hardened, echo captured")

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if '"v405b set=' in bs:
    print("patch_v405: bsdinit rows already converted -- skip")
else:
    old_row = '    "v404 o=0 t=ff r=00 d=00 a=0000 ss=ffffff pm=ff s=9 i=01";'
    new_row = '    "v405 o=0 t=ff r=00 d=00 a=0000 ss=ffffff pm=ff s=9 i=01";'
    n = bs.count(old_row)
    if n != 1:
        sys.exit("patch_v405: v404 row anchor found %d times" % n)
    bs = bs.replace(old_row, new_row, 1)

    # row A: t now shows rsp[0] (transaction type)
    old_t = (
        "\t\t\tv394_buf[11] = hx[(ufs8996_query_type >> 4) & 0xf];\n"
        "\t\t\tv394_buf[12] = hx[ufs8996_query_type & 0xf];\n"
    )
    if bs.count(old_t) != 1:
        sys.exit("patch_v405: row A t-field lines found %d times"
                 % bs.count(old_t))
    bs = bs.replace(
        old_t,
        "\t\t\tv394_buf[11] = hx[(ufs8996_query_type >> 12) & 0xf];\n"
        "\t\t\tv394_buf[12] = hx[(ufs8996_query_type >> 8) & 0xf];\n",
        1,
    )

    # row B: init-sequence diagnostics, printed right before row A
    probe_anchor = """\t\t{ extern void g0245d_probe(const char *);
\t\t  g0245d_probe(v394_buf); }
"""
    n = bs.count(probe_anchor)
    if n != 1:
        sys.exit("patch_v405: probe anchor found %d times" % n)
    row_b = """\t\t{
\t\t\tstatic char v405b_buf[] =
\t\t\t    "v405b set=fe fl=ff n=fff pmb=ff id=ff";
\t\t\textern volatile unsigned int ufs8996_query_setresp;
\t\t\textern volatile unsigned int ufs8996_query_initflag;
\t\t\textern volatile unsigned int ufs8996_query_initpolls;
\t\t\textern volatile unsigned int ufs8996_query_pmbefore;
\t\t\textern volatile unsigned int ufs8996_query_echoidn;
\t\t\tstatic const char hx2[] = "0123456789abcdef";
\t\t\tv405b_buf[10] = hx2[(ufs8996_query_setresp >> 4) & 0xf];
\t\t\tv405b_buf[11] = hx2[ufs8996_query_setresp & 0xf];
\t\t\tv405b_buf[16] = hx2[(ufs8996_query_initflag >> 4) & 0xf];
\t\t\tv405b_buf[17] = hx2[ufs8996_query_initflag & 0xf];
\t\t\tv405b_buf[21] =
\t\t\t    hx2[(ufs8996_query_initpolls >> 8) & 0xf];
\t\t\tv405b_buf[22] =
\t\t\t    hx2[(ufs8996_query_initpolls >> 4) & 0xf];
\t\t\tv405b_buf[23] = hx2[ufs8996_query_initpolls & 0xf];
\t\t\tv405b_buf[29] =
\t\t\t    hx2[(ufs8996_query_pmbefore >> 4) & 0xf];
\t\t\tv405b_buf[30] = hx2[ufs8996_query_pmbefore & 0xf];
\t\t\tv405b_buf[35] = hx2[(ufs8996_query_echoidn >> 4) & 0xf];
\t\t\tv405b_buf[36] = hx2[ufs8996_query_echoidn & 0xf];
\t\t\t{ extern void g0245d_probe(const char *);
\t\t\t  g0245d_probe(v405b_buf); }
\t\t}
""" + probe_anchor
    bs = bs.replace(probe_anchor, row_b, 1)
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v405: bsdinit rows converted to v405/v405b")

print("patch_v405: done")
