#!/usr/bin/env python3
"""g0245d v401: put query_func back at UCD offset 5.

Cross-repo audit of ALL device repos (2026-11-27 11:51) found a working
UFS query implementation in UniXNU/ShengUfs (SM8550) that confirms:

    ucd[0] = 0x16;   // QUERY REQUEST
    ucd[3] = tag;    // task tag
    ucd[5] = 0x01;   // query function: standard read request
    response code = rsp[6]

That matches EDK2 UTP_QUERY_REQ_UPIU:
    DW1 byte0 = Rsvd2 (offset 4)
    DW1 byte1 = QueryFunc (offset 5)
and Linux:
    UPIU_HEADER_DWORD(0, query_func, 0, 0)
    -> cpu_to_be32(0x00010000) -> memory bytes [00,01,00,00]

v398 moved query_func to offset 6 based on a misreading; offset 6 is the
response code position, not the request query_func.  v400 already fixed
the header byte order and the response-code read offset (both correct).
v401 changes exactly one thing: query_func offset 6 -> 5.

Pinned row keeps the v400 p/i layout, label becomes v401.

Idempotent via independent marker checks.
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

src = CPP.read_text(encoding="utf-8")
old = "  v395_ucd[6] = 0x01u;               // STANDARD_READ_REQUEST\n"
new = ("  // g0245d v401: ShengUfs/EDK2/Linux all put query_func at UCD\n"
       "  // offset 5 (DW1 byte1).  v398 put it at offset 6, which is the\n"
       "  // response-code position.  Restore offset 5.\n"
       "  v395_ucd[5] = 0x01u;               // STANDARD_READ_REQUEST\n")
if "v395_ucd[5] = 0x01u;" in src:
    print("patch_v401: query_func already at offset 5 -- skip")
elif src.count(old) == 1:
    src = src.replace(old, new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v401: query_func moved from offset 6 back to 5")
else:
    sys.exit("patch_v401: query_func anchor found %d times" % src.count(old))

bs = BSD.read_text(encoding="utf-8")
if '"v401 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";' in bs:
    print("patch_v401: bsdinit row already relabelled -- skip")
else:
    anchor = '    "v400 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";'
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v401: v400 row anchor found %d times" % n)
    bs = bs.replace(
        anchor,
        '    "v401 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";',
        1,
    )
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v401: bsdinit pinned row relabelled v401")

print("patch_v401: done")
