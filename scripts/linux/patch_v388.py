#!/usr/bin/env python3
"""g0245d v388: show what the UFS driver itself read, on the pinned row.

v387 verdict (photo 2026-11-26 21:39):
    v387 d=0004 c=0003 a=0003 s=0003 m=1 t=3
- d4 c3 a3 s3: the whole match chain works -- three candidates went through
  attach/start (the unique IOMatchCategory fixed the never-started issue).
- t=3: NativeUfs8996::start() ran, mapped 0x624000/0x2500 + 0x627000/0xda8,
  read the registers -- and then stopped between "registers read" (3) and
  "readback plausible" (4).  The only gate there is
  degenerate(cap) || degenerate(ver).
- Contradiction: the v386 bsdinit probe reads the SAME addresses later in
  boot and gets good values (c=0197001f v=00010100).  So either the driver
  saw different bus behaviour at the earlier point in boot, or start() ran
  more than once (rematch after registerService()) and a later attempt is
  what the row shows.

v388 therefore reports the driver's own view on the pinned row (called after
the v387 probe, so it owns the row):

    v388 t=_ f=__ n=__ c=xxxxxxxx v=xxxxxxxx

- t: ufs8996_step   (1 entered, 2 mapped, 3 read, 4 plausible, 5 published)
- f: ufs8996_status (fail reason; 4 = degenerate CAP/VER, 0 = no failure)
- n: ufs8996_start_calls (new counter; >1 proves a rematch happened)
- c/v: the DRIVER's own CAP/VER reads (not the bsdinit ones)

Idempotent via "g0245d v388" markers.
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

# ------------------------------------------------------------ driver counter
src = CPP.read_text(encoding="utf-8")
if "g0245d v388" not in src:
    anchor = "uint32_t ufs8996_probe_calls = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v388: driver globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v388: how many times start() was entered (rematch detector).\n"
        "volatile uint32_t ufs8996_start_calls = 0;\n", 1)

    anchor = "bool NativeUfs8996::start(IOService *provider)\n{\n  ufs8996_step = 1;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v388: start() anchor found %d times" % n)
    src = src.replace(anchor, anchor.replace(
        "  ufs8996_step = 1;\n",
        "  ufs8996_step = 1;\n  ufs8996_start_calls++;\n"), 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v388: driver ufs8996_start_calls counter added")
else:
    print("patch_v388: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v388" not in src:
    anchor = (
        '\t{ extern void g0245d_trace(const char *); '
        'g0245d_trace("v320 lip call"); }\n'
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v388: v320 lip anchor in bsd_init.c found %d times" % n)
    probe = r'''	/* g0245d v388: the UFS driver's own view, on the pinned probe row.
	 * t = ufs8996_step, f = ufs8996_status (fail reason), n = number of
	 * start() entries (rematch detector), c/v = the driver's own CAP/VER
	 * reads.  Last writer of the probe row; survives on screen. */
	{
		static char v388_buf[] = "v388 t=0 f=00 n=00 c=00000000 v=00000000";
		extern volatile unsigned int ufs8996_step;
		extern volatile unsigned int ufs8996_status;
		extern volatile unsigned int ufs8996_start_calls;
		extern volatile unsigned int ufs8996_cap;
		extern volatile unsigned int ufs8996_ver;
		unsigned int v388_j;
		v388_buf[7] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		for (v388_j = 0; v388_j < 2; v388_j++) {
			v388_buf[11 + v388_j] =
			    "0123456789abcdef"[(ufs8996_status >> (4 - 4 * v388_j)) & 0xf];
			v388_buf[16 + v388_j] =
			    "0123456789abcdef"[(ufs8996_start_calls >> (4 - 4 * v388_j)) & 0xf];
		}
		for (v388_j = 0; v388_j < 8; v388_j++) {
			v388_buf[21 + v388_j] =
			    "0123456789abcdef"[(ufs8996_cap >> (28 - 4 * v388_j)) & 0xf];
			v388_buf[32 + v388_j] =
			    "0123456789abcdef"[(ufs8996_ver >> (28 - 4 * v388_j)) & 0xf];
		}
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v388_buf); }
	}
'''
    src = src.replace(anchor, probe + anchor, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v388: bsdinit pinned-row driver-view probe inserted")
else:
    print("patch_v388: bsd_init.c already patched -- skip")

print("patch_v388: done")
