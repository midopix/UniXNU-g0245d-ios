#!/usr/bin/env python3
"""g0245d v398: put UPIU query_func in the right header byte.

v397 verdict (photo 2026-11-27 10:45):
    v397 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9

Adding UTP_REQ_DESC_INT_CMD made the controller write a real OCS (0 =
success), so the interrupt-command bit fix worked.  But the descriptor
response length is 0 and the descriptor bytes are all 0.

Linux 3.18 `ufshcd_prepare_utp_query_req_upiu()` writes:

    header.dword_1 = UPIU_HEADER_DWORD(0, query_func, 0, 0);

`UPIU_HEADER_DWORD(byte3, byte2, byte1, byte0)` means query_func belongs
in **byte 2 of dword 1**, i.e. UCD offset 6.  Our v394 helper wrote it
at offset 5, leaving offset 6 = 0.  With query_func = 0 the device has
no standard read request to execute, which explains a successful OCS
with an empty response data segment.

v398 changes exactly one suspect point: `v395_ucd[5] = 1` ->
`v395_ucd[6] = 1` (offset 5 stays 0 from the page memset).

Read-only diagnostics in the same build (no hardware state change):
trace the IS poll spin count and the IS register value so the next photo
can tell whether IS bit0 was asserted, even if the descriptor is still
empty.  Nothing else is touched.

Pinned row (same layout, new label):

    v398 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9

Idempotent via independent marker checks; each edit is written as soon
as it is applied.
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
CPP = DEV / "drivers" / "NativeUfs8996" / "NativeUfs8996.cpp"
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
for f in (CPP, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------ driver edits
src = CPP.read_text(encoding="utf-8")

# 1) query_func: UCD offset 5 -> offset 6.
old = "  v395_ucd[5] = 0x01u;               // standard read request\n"
new = ("  // g0245d v398: Linux puts query_func in byte 2 of UPIU header\n"
       "  // dword_1, i.e. UCD offset 6.  v394 put it at offset 5 (byte 1),\n"
       "  // leaving the real query_func field = 0.  Offset 5 stays 0.\n"
       "  v395_ucd[6] = 0x01u;               // STANDARD_READ_REQUEST\n")
if "v395_ucd[6] = 0x01u;" in src:
    print("patch_v398: query_func already at UCD offset 6 -- skip")
elif src.count(old) == 1:
    src = src.replace(old, new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v398: query_func moved from offset 5 to offset 6")
else:
    sys.exit("patch_v398: query_func anchor found %d times" % src.count(old))

# 2) read-only IS/spins diagnostics into the trace ring.
diag_anchor = """  out.doorbell = v394Read32(base, Ufs8996::REG_UTRL_DB) & 0xfu;
  if (out.spins == 1000000u) {
"""
diag_new = """  out.doorbell = v394Read32(base, Ufs8996::REG_UTRL_DB) & 0xfu;
  // g0245d v398: read-only diagnostics -- did IS bit0 ever appear?
  // spins == 1000000 means no; a smaller value means IS was asserted.
  g0245d_trace_u("v398 spins", out.spins);
  g0245d_trace_u("v398 is", v394Read32(base, Ufs8996::REG_IS));
  if (out.spins == 1000000u) {
"""
if 'g0245d_trace_u("v398 spins"' in src:
    print("patch_v398: IS/spins diagnostics already installed -- skip")
elif src.count(diag_anchor) == 1:
    src = src.replace(diag_anchor, diag_new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v398: IS/spins diagnostics installed")
else:
    sys.exit("patch_v398: diagnostics anchor found %d times"
             % src.count(diag_anchor))

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if '"v398 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";' in bs:
    print("patch_v398: bsdinit pinned row already relabelled -- skip")
else:
    anchor = '    "v397 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";'
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v398: v397 row anchor found %d times" % n)
    bs = bs.replace(
        anchor,
        '    "v398 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";',
        1,
    )
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v398: bsdinit pinned row relabelled v398")

print("patch_v398: done")
