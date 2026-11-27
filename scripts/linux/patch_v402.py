#!/usr/bin/env python3
"""g0245d v402: read-only diagnostic -- dump the response UPIU header.

v401 photo: 26 v401 o=0 r=f6 a=0000 b=0000 w=0 d=40 s=9 p=000553 i=05.
The transport now works (p << 1000000, IS bit0 set, d=40 = 64-byte
descriptor length echoed back).  The request UPIU matches Linux 3.18
byte-for-byte, the UTRD matches, yet rsp[6] reads 0xf6 and the
descriptor data segment at rsp+32 is empty.  One byte is not enough to
decide the response layout, so pin more of the header on the console
row: t = rsp[0..1] (transaction type + flags), q = rsp[4..5] (dword1
byte4/5), r = rsp[6], d = data segment length, a = rsp[32..33] (first
descriptor bytes).  No hardware state changes.  Only boot is flashed.
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
if "ufs8996_query_type" in src:
    print("patch_v402: driver header-dump globals already present -- skip")
else:
    anchor = (
        "// g0245d v399: IS register value after the UTRL poll.\n"
        "volatile uint32_t ufs8996_query_is = 0;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v402: IS global anchor found %d times" % n)
    src = src.replace(
        anchor,
        anchor
        + "// g0245d v402: response UPIU header dump (bytes 0-1 and 4-5\n"
        + "// of the 512-byte response area) pinned on the console row.\n"
        + "volatile uint32_t ufs8996_query_type = 0xffff;\n"
        + "volatile uint32_t ufs8996_query_b45  = 0xffff;\n",
        1,
    )
    fill_anchor = '  g0245d_trace_u("v398 is", ufs8996_query_is);\n'
    n = src.count(fill_anchor)
    if n != 1:
        sys.exit("patch_v402: IS trace anchor found %d times" % n)
    src = src.replace(
        fill_anchor,
        fill_anchor
        + "  // g0245d v402: dump the response UPIU header bytes (read-only).\n"
        + "  ufs8996_query_type =\n"
        + "      ((uint32_t)v395_ucd[512 + 0] << 8) | v395_ucd[512 + 1];\n"
        + "  ufs8996_query_b45 =\n"
        + "      ((uint32_t)v395_ucd[512 + 4] << 8) | v395_ucd[512 + 5];\n",
        1,
    )
    CPP.write_text(src, encoding="utf-8")
    print("patch_v402: driver header-dump installed")

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
old_row = '    "v401 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";'
new_row = '    "v402 o=0 t=ffff q=ffff r=00 d=00 a=0000 s=9 p=0f4240 i=01";'
if '"v402 o=0 t=' in bs:
    print("patch_v402: bsdinit row already converted -- skip")
else:
    n = bs.count(old_row)
    if n != 1:
        sys.exit("patch_v402: v401 row anchor found %d times" % n)
    bs = bs.replace(old_row, new_row, 1)

    pat = re.compile(
        r"\t\tv394_buf\[7\] = \(ufs8996_query_ocs.*?"
        r"ufs8996_query_is & 0xf\]; \}",
        re.S,
    )
    if not pat.search(bs):
        sys.exit("patch_v402: pinned-row fill block not found")
    new_fill = """\t\t/* g0245d v402: response UPIU header dump on the pinned row. */
\t\t{
\t\t\textern volatile unsigned int ufs8996_query_ocs;
\t\t\textern volatile unsigned int ufs8996_query_type;
\t\t\textern volatile unsigned int ufs8996_query_b45;
\t\t\textern volatile unsigned int ufs8996_query_resp;
\t\t\textern volatile unsigned int ufs8996_query_len;
\t\t\textern volatile unsigned int ufs8996_query_bytes01;
\t\t\textern volatile unsigned int ufs8996_step;
\t\t\tstatic const char hx[] = "0123456789abcdef";
\t\t\tv394_buf[7] = (ufs8996_query_ocs < 16)
\t\t\t    ? hx[ufs8996_query_ocs] : '?';
\t\t\tv394_buf[11] = hx[(ufs8996_query_type >> 12) & 0xf];
\t\t\tv394_buf[12] = hx[(ufs8996_query_type >> 8) & 0xf];
\t\t\tv394_buf[13] = hx[(ufs8996_query_type >> 4) & 0xf];
\t\t\tv394_buf[14] = hx[ufs8996_query_type & 0xf];
\t\t\tv394_buf[18] = hx[(ufs8996_query_b45 >> 12) & 0xf];
\t\t\tv394_buf[19] = hx[(ufs8996_query_b45 >> 8) & 0xf];
\t\t\tv394_buf[20] = hx[(ufs8996_query_b45 >> 4) & 0xf];
\t\t\tv394_buf[21] = hx[ufs8996_query_b45 & 0xf];
\t\t\tv394_buf[25] = hx[(ufs8996_query_resp >> 4) & 0xf];
\t\t\tv394_buf[26] = hx[ufs8996_query_resp & 0xf];
\t\t\tv394_buf[30] = hx[(ufs8996_query_len >> 4) & 0xf];
\t\t\tv394_buf[31] = hx[ufs8996_query_len & 0xf];
\t\t\tv394_buf[35] = hx[(ufs8996_query_bytes01 >> 12) & 0xf];
\t\t\tv394_buf[36] = hx[(ufs8996_query_bytes01 >> 8) & 0xf];
\t\t\tv394_buf[37] = hx[(ufs8996_query_bytes01 >> 4) & 0xf];
\t\t\tv394_buf[38] = hx[ufs8996_query_bytes01 & 0xf];
\t\t\tv394_buf[42] = (ufs8996_step < 10)
\t\t\t    ? (char)('0' + ufs8996_step) : '?';
\t\t\t{
\t\t\t\textern volatile unsigned int ufs8996_query_spins;
\t\t\t\textern volatile unsigned int ufs8996_query_is;
\t\t\t\tunsigned int p = ufs8996_query_spins & 0xffffffu;
\t\t\t\tunsigned int k;
\t\t\t\tfor (k = 0; k < 6; k++)
\t\t\t\t\tv394_buf[51 - k] = hx[(p >> (4 * k)) & 0xf];
\t\t\t\tv394_buf[55] = hx[(ufs8996_query_is >> 4) & 0xf];
\t\t\t\tv394_buf[56] = hx[ufs8996_query_is & 0xf];
\t\t\t}
\t\t}"""
    bs = pat.sub(lambda _: new_fill, bs, count=1)
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v402: bsdinit pinned row converted to v402 layout")

print("patch_v402: done")
