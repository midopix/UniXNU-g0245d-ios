#!/usr/bin/env python3
"""g0245d v397: set UTP_REQ_DESC_INT_CMD in UTRD dword0.

v396 verdict (photo 2026-11-27 10:34):
    v396 o=f r=fe a=0000 b=0000 w=0 d=00 s=9

The doorbell was consumed (w=0), and the alignment/tag changes did not
move the result.  Linux 3.18's ufshcd_exec_dev_cmd() marks device
management commands as intr_cmd, and ufshcd_prepare_req_desc_hdr() ORs
UTP_REQ_DESC_INT_CMD (0x01000000) into UTRD dword0.  Our v394 helper only
wrote 0x20000000.  If IS bit0 is only asserted when that bit is set, the
completion poll times out even after the controller has completed the
request.

v397 changes exactly one suspect point: UTRD dword0 0x20000000 ->
0x21000000.  The only extra change is a read-only diagnostic: on the IS
timeout path, read OCS and the response UPIU before returning so o/r/a/b/d
become real values instead of initialisation sentinels.  HCE, UIC, clocks,
PHY, link, task tag, doorbell and UCD layout are untouched.

Pinned row (same layout, new label):

    v397 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9

Idempotent via independent marker checks; each edit is written as soon as
it is applied so a partial run can be re-driven.
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

# 1) UTRD dword0: add UTP_REQ_DESC_INT_CMD (bit24).
old = "  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x20000000u;\n"
new = ("  // g0245d v397: ufshcd_exec_dev_cmd() marks device-management\n"
       "  // commands intr_cmd, so Linux ORs UTP_REQ_DESC_INT_CMD (bit24)\n"
       "  // into UTRD dword0.  Without it the controller may complete the\n"
       "  // transfer without ever asserting IS bit0.\n"
       "  *reinterpret_cast<volatile uint32_t *>(utrd + 0) = 0x21000000u;\n")
if "= 0x21000000u;" in src:
    print("patch_v397: UTRD dword0 already has bit24 -- skip")
elif src.count(old) == 1:
    src = src.replace(old, new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v397: UTRD dword0 bit24 installed")
else:
    sys.exit("patch_v397: UTRD dword0 anchor found %d times" % src.count(old))

# 2) Read OCS/response on the IS-timeout path (read-only; no writes added).
timeout_anchor = """  if (out.spins == 1000000u) {
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
"""
timeout_new = """  if (out.spins == 1000000u) {
    // g0245d v397: read-only diagnostics.  v394-v396 left the o/r/a/b/d
    // fields at their sentinel values on timeout, so the photo could not
    // tell whether the controller had written OCS/response at all.
    out.ocs = (*reinterpret_cast<volatile uint32_t *>(utrd + 8)) & 0xfu;
    // g0245d v397: volatile byte reads forbid 32-bit merge (v394 fault).
    out.response = v395_ucd[512 + 5];
    out.data_len =
        ((uint32_t)v395_ucd[512 + 10] << 8) | v395_ucd[512 + 11];
    out.bytes01 =
        ((uint32_t)v395_ucd[512 + 32] << 8) | v395_ucd[512 + 33];
    out.bytes23 =
        ((uint32_t)v395_ucd[512 + 34] << 8) | v395_ucd[512 + 35];
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
"""
if "g0245d v397: read-only diagnostics" in src:
    print("patch_v397: timeout OCS/response read already installed -- skip")
elif src.count(timeout_anchor) == 1:
    src = src.replace(timeout_anchor, timeout_new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v397: timeout OCS/response read installed")
else:
    sys.exit("patch_v397: timeout anchor found %d times"
             % src.count(timeout_anchor))

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if '"v397 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";' in bs:
    print("patch_v397: bsdinit pinned row already relabelled -- skip")
else:
    anchor = '    "v396 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";'
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v397: v396 row anchor found %d times" % n)
    bs = bs.replace(
        anchor,
        '    "v397 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";',
        1,
    )
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v397: bsdinit pinned row relabelled v397")

print("patch_v397: done")
