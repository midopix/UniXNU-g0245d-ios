#!/usr/bin/env python3
"""g0245d v387: locate where IOKit matching stops before NativeUfs8996::start().

v386 verdict from the pinned boot row (photo, 2026-11-26 21:18):
    v386 c=0197001f v=00010100 p=01000000 m1 s0
- c/v/p: direct MMIO reads of CAP/VER/HCPID at 0x624000.
  VER=0x00010100 (non-zero, not all-ones) => UFSHCI register interface is
  alive => LK left the UFS clocks on => **C1a PASS** (no GCC driver needed).
- m1: NativeUfs8996::probe() ran and matched the root nub.
- s0: start() never ran (ufs8996_step == 0, "0 = personality never started").

Static analysis of iokit/Kernel/IOService.cpp says probe -> startDict ->
startCandidate -> attach -> start() has no obvious break, so v387 adds four
C-linkage counters inside IOService.cpp and prints them on the same pinned
row (g0245d_probe, called after the v386 call so it owns the row):

    v387 d=xxxx c=xxxx a=xxxx s=xxxx m=_ t=_

- d: candidate fetched from the start dict in probeCandidates()
- c: startCandidate() entered
- a: attach(provider) succeeded inside startCandidate()
- s: reached the service->start(provider) call
- m/t: v385 driver matched / start step (same as v386 m/s)

Also adds a unique IOMatchCategory to the v385 personality: if some other
root-nub client already consumed the default match category, our candidate
must stop before start even after a clean probe.

Idempotent via "g0245d v387" markers.
"""
import os
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
W = Path(W)

IO = W / "iokit" / "Kernel" / "IOService.cpp"
KCT = W / "iokit" / "KernelConfigTables.cpp"
BSD = W / "bsd" / "kern" / "bsd_init.c"
for f in (IO, KCT, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ---------------------------------------------------------------- IOService.cpp
src = IO.read_text(encoding="utf-8")
if "g0245d v387" not in src:
    # A) globals before probeCandidates (file scope, before all uses)
    anchor = (
        "/*\n"
        " * Alloc and probe matching classes,\n"
        " * called on the provider instance\n"
        " */\n"
        "\n"
        "void\n"
        "IOService::probeCandidates( OSOrderedSet * matches )\n"
    )
    if src.count(anchor) != 1:
        sys.exit("patch_v387: probeCandidates anchor found %d times" % src.count(anchor))
    src = src.replace(anchor, (
        "/* g0245d v387: IOKit matching stop-location counters (C linkage so\n"
        " * bsd/kern/bsd_init.c can read them for the pinned boot row). */\n"
        "extern \"C\" {\n"
        "volatile unsigned int g0245d_io_d = 0; /* startDict candidate fetch */\n"
        "volatile unsigned int g0245d_io_c = 0; /* startCandidate entered */\n"
        "volatile unsigned int g0245d_io_a = 0; /* attach ok in startCandidate */\n"
        "volatile unsigned int g0245d_io_s = 0; /* reached service->start */\n"
        "}\n"
        "\n" + anchor
    ), 1)

    # B) startCandidate entry counter
    anchor = (
        "IOService::startCandidate( IOService * service )\n"
        "{\n"
        "\tbool                ok;\n"
    )
    if src.count(anchor) != 1:
        sys.exit("patch_v387: startCandidate anchor found %d times" % src.count(anchor))
    src = src.replace(anchor, (
        "IOService::startCandidate( IOService * service )\n"
        "{\n"
        "\tg0245d_io_c++;\n"
        "\tbool                ok;\n"
    ), 1)

    # B) startDict loop: candidate fetched
    anchor = (
        "\t\t\t\tinst->retain();\n"
        "\t\t\t\tstartList->removeObject(inst);\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v387: startDict anchor found %d times" % n)
    src = src.replace(anchor, anchor + "\t\t\t\tg0245d_io_d++;\n", 1)

    # C) attach ok inside startCandidate
    anchor = (
        "\t} else {\n"
        "\t\tok = service->attach( this );\n"
        "\t}\n"
        "\tif (!ok) {\n"
        "\t\tOSSafeReleaseNULL(obj);\n"
        "\t\treturn false;\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v387: attach anchor found %d times" % n)
    src = src.replace(anchor, anchor + "\tg0245d_io_a++;\n", 1)

    # D) reached the start() call
    anchor = (
        "\tok = service->start(this);\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v387: start-call anchor found %d times" % n)
    src = src.replace(anchor, "\tg0245d_io_s++;\n" + anchor, 1)

    IO.write_text(src, encoding="utf-8")
    print("patch_v387: IOService.cpp counters inserted (d/c/a/s)")
else:
    print("patch_v387: IOService.cpp already patched -- skip")

# ---------------------------------------------------------- KernelConfigTables.cpp
src = KCT.read_text(encoding="utf-8")
if "'IOMatchCategory' = NativeUfs8996" not in src:
    cls = '    "     \'IOClass\'         = NativeUfs8996;"\n'
    name = '    "     \'IONameMatch\'     = \'device-tree\';"\n'
    if src.count(cls) != 1:
        sys.exit("patch_v387: KCT IOClass line not unique (%d)" % src.count(cls))
    i_cls = src.index(cls)
    i_name = src.index(name, i_cls)
    if src.count(name, i_cls) != 1:
        sys.exit("patch_v387: KCT IONameMatch not unique inside our block")
    addition = '    "     \'IOMatchCategory\' = NativeUfs8996;"\n'
    src = src[:i_name + len(name)] + addition + src[i_name + len(name):]
    KCT.write_text(src, encoding="utf-8")
    print("patch_v387: IOMatchCategory added to v385 personality")
else:
    print("patch_v387: IOMatchCategory already present -- skip")

# ------------------------------------------------------------------- bsd_init.c
src = BSD.read_text(encoding="utf-8")
if "g0245d v387" not in src:
    anchor = (
        '\t{ extern void g0245d_trace(const char *); '
        'g0245d_trace("v320 lip call"); }\n'
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v387: v320 lip anchor in bsd_init.c found %d times" % n)
    probe = r'''	/* g0245d v387: same pinned row, now reporting where IOKit matching
	 * stopped for the UFS driver: d = startDict candidate fetch,
	 * c = startCandidate entered, a = attach ok, s = reached start();
	 * m/t = v385 driver matched / start step.  This call is the last
	 * writer of the probe row, so it survives on screen. */
	{
		static char v387_buf[] = "v387 d=0000 c=0000 a=0000 s=0000 m=0 t=0";
		extern volatile unsigned int g0245d_io_d;
		extern volatile unsigned int g0245d_io_c;
		extern volatile unsigned int g0245d_io_a;
		extern volatile unsigned int g0245d_io_s;
		extern volatile unsigned int ufs8996_matched;
		extern volatile unsigned int ufs8996_step;
		unsigned int v387_vals[4];
		unsigned int v387_i, v387_j, v387_k;
		v387_vals[0] = g0245d_io_d;
		v387_vals[1] = g0245d_io_c;
		v387_vals[2] = g0245d_io_a;
		v387_vals[3] = g0245d_io_s;
		for (v387_k = 0; v387_k < 4; v387_k++) {
			v387_i = 7 + v387_k * 7;
			for (v387_j = 0; v387_j < 4; v387_j++) {
				v387_buf[v387_i + v387_j] =
				    "0123456789abcdef"[(v387_vals[v387_k] >> (12 - 4 * v387_j)) & 0xf];
			}
		}
		v387_buf[35] = (ufs8996_matched != 0) ? '1' : '0';
		v387_buf[39] = (ufs8996_step < 10) ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v387_buf); }
	}
'''
    src = src.replace(anchor, probe + anchor, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v387: bsdinit pinned-row counters probe inserted")
else:
    print("patch_v387: bsd_init.c already patched -- skip")

print("patch_v387: done")
