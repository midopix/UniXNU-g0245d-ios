#!/usr/bin/env python3
"""g0245d v399: put the IS/spins diagnostics on the pinned console row.

v398 verdict (photo 2026-11-27 10:50):
    v398 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9
Still an empty descriptor.  The `v398 spins` / `v398 is` trace lines were
printed during bsd_init and had already scrolled out of the ring by the
time the photo was taken (ring showed 9168-9186).  The values must live
on the pinned row instead.

v399 changes only the observation channel, not any hardware state:
- add `p=<spins:6 hex>` and `i=<IS low byte:2 hex>` to the pinned row;
- relabel it v399.

Pinned row:

    v399 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01

If `p=0f4240` (1000000) then IS bit0 was never asserted; if `p` is small
and `i` has bit0 set, IS fired and the empty descriptor has another cause.

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

# ------------------------------------------------------------ driver edits
src = CPP.read_text(encoding="utf-8")

# 1) forward declaration before the helper uses the global.
decl = 'extern "C" void g0245d_trace_u(const char *label, unsigned int value);\n'
if "extern volatile uint32_t ufs8996_query_is;" in src:
    print("patch_v399: IS global declaration already present -- skip")
elif src.count(decl) == 1:
    src = src.replace(decl, decl +
        "extern volatile uint32_t ufs8996_query_is;\n", 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v399: IS global declaration added")
else:
    sys.exit("patch_v399: extern anchor found %d times" % src.count(decl))

# 2) definition next to the doorbell global.
defn = "volatile uint32_t ufs8996_query_doorbell = 0;\n"
if "volatile uint32_t ufs8996_query_is = 0;" in src:
    print("patch_v399: IS global definition already present -- skip")
elif src.count(defn) == 1:
    src = src.replace(defn, defn +
        "// g0245d v399: IS register value after the UTRL poll.\n"
        "volatile uint32_t ufs8996_query_is = 0;\n", 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v399: IS global definition added")
else:
    sys.exit("patch_v399: global definition anchor found %d times"
             % src.count(defn))

# 3) store the IS read into the global (replaces the trace-only read).
old_is = '  g0245d_trace_u("v398 is", v394Read32(base, Ufs8996::REG_IS));\n'
new_is = ('  // g0245d v399: pin the IS value instead of only tracing it.\n'
          '  ufs8996_query_is = v394Read32(base, Ufs8996::REG_IS);\n'
          '  g0245d_trace_u("v398 is", ufs8996_query_is);\n')
if "ufs8996_query_is = v394Read32(base, Ufs8996::REG_IS);" in src:
    print("patch_v399: IS value already stored -- skip")
elif src.count(old_is) == 1:
    src = src.replace(old_is, new_is, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v399: IS value stored in global")
else:
    sys.exit("patch_v399: IS trace anchor found %d times" % src.count(old_is))

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if '"v399 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";' in bs:
    print("patch_v399: bsdinit row already extended -- skip")
else:
    old = '    "v398 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";'
    n = bs.count(old)
    if n != 1:
        sys.exit("patch_v399: v398 row anchor found %d times" % n)
    bs = bs.replace(
        old,
        '    "v399 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9 p=0f4240 i=01";',
        1,
    )
    # Append p= (indices 43..48, 6 hex digits) and i= (indices 52..53).
    anchor = """\t\tv394_buf[39] = (ufs8996_step < 10)
\t\t    ? (char)('0' + ufs8996_step) : '?';
"""
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v399: row tail anchor found %d times" % n)
    extra = """\t\tv394_buf[39] = (ufs8996_step < 10)
\t\t    ? (char)('0' + ufs8996_step) : '?';
\t\t/* g0245d v399: IS poll spins and IS low byte on the pinned row. */
\t\t{ extern volatile unsigned int ufs8996_query_spins;
\t\t  extern volatile unsigned int ufs8996_query_is;
\t\t  unsigned int p = ufs8996_query_spins & 0xffffffu;
\t\t  unsigned int k;
\t\t  for (k = 0; k < 6; k++)
\t\t    v394_buf[48 - k] = "0123456789abcdef"[(p >> (4 * k)) & 0xf];
\t\t  v394_buf[52] =
\t\t      "0123456789abcdef"[(ufs8996_query_is >> 4) & 0xf];
\t\t  v394_buf[53] =
\t\t      "0123456789abcdef"[ufs8996_query_is & 0xf]; }
"""
    bs = bs.replace(anchor, extra, 1)
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v399: bsdinit row extended with p/i fields")

print("patch_v399: done")
