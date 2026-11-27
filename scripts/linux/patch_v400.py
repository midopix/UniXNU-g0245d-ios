#!/usr/bin/env python3
"""g0245d v400: fix the UPIU header byte order.

Cross-repo audit (2026-11-27 11:35) found the real cause of the empty
descriptor in the MSM8996 firmware/kernel sources:

  Linux 3.18:
    header.dword_0 = UPIU_HEADER_DWORD(transaction, flags, lun, task_tag)
    -> memory bytes [transaction, flags, lun, task_tag]

  EDK2 MdePkg/IndustryStandard/Ufs.h:
    UTP_QUERY_REQ_UPIU { TransCode; Flags; Rsvd1; TaskTag; ... }
    -> memory bytes [transaction, flags, lun, task_tag]

Our v394 helper wrote [task_tag, lun, flags, transaction] -- completely
reversed.  The controller therefore saw transaction type 0 (NOP_OUT),
completed it with OCS=0, and returned an empty NOP_IN-shaped response.
That explains v397/v398: real OCS, empty data segment.

v400 changes exactly one hardware-affecting suspect point: swap UPIU
header bytes 0 and 3 (and keep LUN/flags at 1/2).

Read-only diagnostic correction in the same build: the UFS Query Response
code lives at response UPIU offset 6 (both Linux be32_to_cpu(... )>>8 and
EDK2 UTP_QUERY_RESP_UPIU.QueryResp), not offset 5.  v394-v399 read offset
5 (QueryFunc), so the `r` digit was not the response code.

Pinned row keeps the v399 p/i layout, label becomes v400.

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

import re
_bs = BSD.read_text(encoding="utf-8")
_tags = re.findall(r'"v(\d{3}) o=0 r=00 a=0000 b=0000 w=0 d=00 s=9', _bs)
if not _tags or _tags[0] != "399":
    print("patch_v400: newer pinned row present -- skip entire patch")
    print("patch_v400: done")
    sys.exit(0)

# ------------------------------------------------------------ driver edits
src = CPP.read_text(encoding="utf-8")

# 1) UPIU header: [transaction, flags, lun, task_tag].
old = """  v395_ucd[0] = 0u;                  // task tag = doorbell slot 0
  v395_ucd[1] = 0u;                  // LUN
  v395_ucd[2] = 0u;                  // flags: no data
  v395_ucd[3] = 0x16u;               // QUERY REQUEST
"""
new = """  // g0245d v400: Linux UPIU_HEADER_DWORD and EDK2 UTP_QUERY_REQ_UPIU
  // both put the transaction type in byte 0 and the task tag in byte 3.
  // v394-v399 had them reversed, so the controller saw NOP_OUT (0x00)
  // instead of QUERY_REQ (0x16), returned OCS=0 and an empty response.
  v395_ucd[0] = 0x16u;               // TRANSACTION_TYPE_QUERY_REQUEST
  v395_ucd[1] = 0u;                  // flags: no data
  v395_ucd[2] = 0u;                  // LUN
  v395_ucd[3] = 0u;                  // task tag = doorbell slot 0
"""
if "v395_ucd[0] = 0x16u;" in src:
    print("patch_v400: UPIU header byte order already fixed -- skip")
elif src.count(old) == 1:
    src = src.replace(old, new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v400: UPIU header bytes swapped to spec order")
else:
    sys.exit("patch_v400: header anchor found %d times" % src.count(old))

# 2) response code offset 5 -> 6 (both timeout and success paths).
old_resp = "  out.response = v395_ucd[512 + 5];\n"
new_resp = "  out.response = v395_ucd[512 + 6];\n"
n = src.count(old_resp)
if "v395_ucd[512 + 6]" in src:
    print("patch_v400: response code offset already corrected -- skip")
elif n == 2:
    src = src.replace(old_resp, new_resp)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v400: response code read moved from offset 5 to 6")
else:
    sys.exit("patch_v400: response-code anchor found %d times" % n)

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if '"v400 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";' in bs:
    print("patch_v400: bsdinit row already relabelled -- skip")
else:
    anchor = '    "v399 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";'
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v400: v399 row anchor found %d times" % n)
    bs = bs.replace(
        anchor,
        '    "v400 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";',
        1,
    )
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v400: bsdinit pinned row relabelled v400")

print("patch_v400: done")
