#!/usr/bin/env python3
"""g0245d v396: match UPIU task tag to the doorbell slot.

v395 verdict (photo 2026-11-27 10:00):
    v395 o=f r=fe a=0000 b=0000 d=00 s=9
o=f (OCS_INVALID) and r=fe (default) mean the UTRL transfer never
completed in 1,000,000 spins; the controller never accepted the request.

Root cause candidate: Linux 3.18 ufshcd.c sets lrbp->task_tag = tag,
writes that same tag into UPIU header byte 0, and rings doorbell (1 << tag).
v394/v395 used UPIU tag 1 but doorbell slot 0 (value 1).  A UFS controller
that checks tag==slot discards the request, so no completion and no OCS
update.  v396 sets the UPIU task tag to 0 so it matches doorbell slot 0.

A read-only diagnostic is added: the doorbell register value after the
poll is printed as 'w' in the pinned row.  No other hardware state changes.

New pinned row:

    v396 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9

- w = REG_UTRL_DB readback after the poll (0 means controller consumed it)
Idempotent via "g0245d v396" markers.
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
for f in (CPP,):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

src = CPP.read_text(encoding="utf-8")
if "g0245d v396" not in src:
    # 1) task tag 1 -> 0
    anchor = "  v395_ucd[0] = 1u;                  // task tag\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: task-tag anchor found %d times" % n)
    src = src.replace(
        anchor,
        "  // g0245d v396: Linux uses the same value for UPIU task tag and\n"
        "  // doorbell slot (lrbp->task_tag = tag; doorbell = 1 << tag).\n"
        "  // v395 had tag=1 with doorbell slot 0; make both 0.\n"
        "  v395_ucd[0] = 0u;                  // task tag = doorbell slot 0\n",
        1,
    )

    # 2) capture doorbell readback into the result struct
    anchor = """  uint32_t bytes23;
  uint32_t spins;
};
"""
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: result struct anchor found %d times" % n)
    src = src.replace(anchor, """  uint32_t bytes23;
  uint32_t spins;
  uint32_t doorbell;
};
""", 1)

    anchor = "  out.spins = 1000000u;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: out init anchor found %d times" % n)
    src = src.replace(anchor, "  out.spins = 1000000u;\n  out.doorbell = 0u;\n", 1)

    # 3) read the doorbell register after the wait loop
    anchor = """  if (out.spins == 1000000u) {
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
"""
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: timeout branch anchor found %d times" % n)
    src = src.replace(anchor, """  // g0245d v396: read-only diagnostic -- did the controller consume the
  // doorbell?  0 means it did; a set bit means the request was not taken.
  out.doorbell = v394Read32(base, Ufs8996::REG_UTRL_DB) & 0xfu;
  if (out.spins == 1000000u) {
    v394Write32(base, Ufs8996::REG_UTRL_RUN, 0u);
    return out;
  }
""", 1)

    # 4) propagate to global
    anchor = "volatile uint32_t ufs8996_query_spins   = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: query globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v396: doorbell readback after the UTRL poll.\n"
        "volatile uint32_t ufs8996_query_doorbell = 0;\n", 1)

    anchor = "      ufs8996_query_spins   = q.spins;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v396: result copy anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "      ufs8996_query_doorbell = q.doorbell;\n", 1)

    CPP.write_text(src, encoding="utf-8")
    print("patch_v396: task tag 0 + doorbell readback installed")
else:
    print("patch_v396: driver already patched -- skip")

# ------------------------------------------------------------- bsd_init.c
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
bs = BSD.read_text(encoding="utf-8")
if "g0245d v396" not in bs:
    anchor = '    "v395 o=0 r=00 a=0000 b=0000 d=00 s=9";'
    n = bs.count(anchor)
    if n != 1:
        # v402 replaced the pinned-row fill block, so the "g0245d v396"
        # marker comment is gone even though the patch is applied.  A
        # missing v395 anchor therefore means "already relabelled".
        print("patch_v396: v395 row anchor absent (row already newer) -- skip")
    else:
        bs = bs.replace(
            anchor,
            '    "v396 o=0 r=00 a=0000 b=0000 w=0 d=00 s=9";',
            1,
        )
        # Shift field writes first: d 30/31 -> 34/35, s 35 -> 39.
        # (Do this before inserting the w digit at 30 to avoid collisions.)
        bs = bs.replace("\t\tv394_buf[30] =\n", "\t\tv394_buf[34] =\n", 1)
        bs = bs.replace("\t\tv394_buf[31] =\n", "\t\tv394_buf[35] =\n", 1)
        bs = bs.replace("\t\tv394_buf[35] = (ufs8996_step",
                        "\t\tv394_buf[39] = (ufs8996_step", 1)
        # Now insert the doorbell digit at index 30 (the 'w' field).
        anchor = "\t\tv394_buf[34] =\n"
        n = bs.count(anchor)
        if n != 1:
            sys.exit("patch_v396: shifted data-len write anchor found %d times" % n)
        insert = """\t\t/* g0245d v396: doorbell readback digit (index 30). */
\t\t{ extern volatile unsigned int ufs8996_query_doorbell;
\t\t  v394_buf[30] = (ufs8996_query_doorbell < 16)
\t\t      ? "0123456789abcdef"[ufs8996_query_doorbell] : '?'; }
"""
        bs = bs.replace(anchor, insert + anchor, 1)
        BSD.write_text(bs, encoding="utf-8")
        print("patch_v396: bsdinit pinned row v396 + doorbell digit")
else:
    print("patch_v396: bsd_init.c already patched -- skip")

print("patch_v396: done")
