#!/usr/bin/env python3
"""g0245d v390: C2 step 1 -- actually enable the UFS host controller.

v389 verdict (photo 2026-11-26 22:24): the SP1 sync exception was a one-off;
boot returned to the documented lret=2 steady state (exec_mach_imgact+0xe6c).
C1a is fully green (driver t=5, CAP/VER good, no rematch).  Per the plan,
clocks are alive so we skip GCC and start real UFSHCI bring-up.

v390 does the HCE-enable sequence inside the driver (after step 5 publish,
before returning from start()):

    ufs8996_hce_before = read HCE (0x34)
    if bit0 == 0:  write HCE=1, poll HCS (0x30) bit0, bounded 200k iters
    else:          controller already enabled by LK, just record HCS
    ufs8996_step = 6

New pinned row (after the v388 row):

    v390 e=xxxxxxxx h=xxxxxxxx n=xxxxxxxx s=_

- e: HCE before (raw register)
- h: HCS after the enable sequence (bit0 = enabled)
- n: poll iterations (0 = already enabled, no poll)
- s: driver step (6 = HCE sequence done)

Judgement table:
- s=6, h bit0=1 (h odd)          => controller enabled, next: link start
- s=6, n>0, h even               => enable timeout, controller refuses
- s=6, n=0 (already enabled)     => LK left it on, go straight to link start
- anything else / bus exception  => v389 console lines catch the ESR/pc

Idempotent via "g0245d v390" markers.
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

# ------------------------------------------------------------- driver changes
src = CPP.read_text(encoding="utf-8")
if "g0245d v390" not in src:
    # 1) new probe-state globals
    anchor = "volatile uint32_t ufs8996_hce    = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v390: globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v390: C2 HCE-enable probe state.\n"
        "volatile uint32_t ufs8996_hce_before = 0;\n"
        "volatile uint32_t ufs8996_hcs_after  = 0;\n"
        "volatile uint32_t ufs8996_poll       = 0;\n"
        "volatile uint32_t ufs8996_en         = 0;\n", 1)

    # 2) write32 declaration next to read32
    anchor = "  static uint32_t read32(uintptr_t base, unsigned offset);\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v390: read32 decl anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "  static void write32(uintptr_t base, unsigned offset, uint32_t value);\n", 1)

    # 3) write32 definition after the read32 definition
    anchor = (
        "uint32_t NativeUfs8996::read32(uintptr_t base, unsigned offset)\n"
        "{\n"
        "  return *reinterpret_cast<volatile uint32_t *>(base + offset);\n"
        "}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v390: read32 def anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "\n"
        "void NativeUfs8996::write32(uintptr_t base, unsigned offset, uint32_t value)\n"
        "{\n"
        "  *reinterpret_cast<volatile uint32_t *>(base + offset) = value;\n"
        "}\n", 1)

    # 4) HCE-enable sequence between publish (step 5) and return true
    anchor = (
        "  registerService();\n"
        "  ufs8996_step = 5;\n"
        '  g0245d_trace("v385 ufs probed ok");\n'
        "  return true;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v390: start() tail anchor found %d times" % n)
    inject = (
        "  registerService();\n"
        "  ufs8996_step = 5;\n"
        '  g0245d_trace("v385 ufs probed ok");\n'
        "\n"
        "  /* g0245d v390: C2 step 1 -- enable the host controller (HCE).\n"
        "   * If LK already left it enabled, record HCS and move on. */\n"
        "  ufs8996_hce_before = read32(fBase, Ufs8996::REG_HCE);\n"
        "  if ((ufs8996_hce_before & 1u) == 0u) {\n"
        "    write32(fBase, Ufs8996::REG_HCE, 1u);\n"
        "    unsigned int v390_n;\n"
        "    for (v390_n = 0; v390_n < 200000u; v390_n++) {\n"
        "      ufs8996_hcs_after = read32(fBase, Ufs8996::REG_HCS);\n"
        "      if (ufs8996_hcs_after & 1u) { break; }\n"
        "    }\n"
        "    ufs8996_poll = v390_n;\n"
        "    ufs8996_en = (ufs8996_hcs_after & 1u) ? 1u : 2u;\n"
        "  } else {\n"
        "    ufs8996_hcs_after = read32(fBase, Ufs8996::REG_HCS);\n"
        "    ufs8996_poll = 0;\n"
        "    ufs8996_en = 3u; /* already enabled by LK */\n"
        "  }\n"
        "  ufs8996_step = 6;\n"
        '  g0245d_trace_u("v390 hce", ufs8996_hce_before);\n'
        '  g0245d_trace_u("v390 hcs", ufs8996_hcs_after);\n'
        "  return true;\n"
    )
    src = src.replace(anchor, inject, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v390: driver HCE-enable sequence added")
else:
    print("patch_v390: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v390" not in src:
    anchor = (
        "\t\t{ extern void g0245d_probe(const char *);\n"
        "\t\t  g0245d_probe(v388_buf); }\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v390: v388 row tail anchor in bsd_init.c found %d times" % n)
    probe = r'''
	/* g0245d v390: C2 HCE-enable result, on the pinned probe row.
	 * e = HCE before, h = HCS after (bit0 = enabled), n = poll iterations
	 * (0 = already enabled), s = driver step (6 = sequence done). */
	{
		static char v390_buf[] = "v390 e=00000000 h=00000000 n=00000000 s=0";
		extern volatile unsigned int ufs8996_hce_before;
		extern volatile unsigned int ufs8996_hcs_after;
		extern volatile unsigned int ufs8996_poll;
		extern volatile unsigned int ufs8996_step;
		unsigned int v390_j;
		for (v390_j = 0; v390_j < 8; v390_j++) {
			v390_buf[7 + v390_j] =
			    "0123456789abcdef"[(ufs8996_hce_before >> (28 - 4 * v390_j)) & 0xf];
			v390_buf[18 + v390_j] =
			    "0123456789abcdef"[(ufs8996_hcs_after >> (28 - 4 * v390_j)) & 0xf];
			v390_buf[29 + v390_j] =
			    "0123456789abcdef"[(ufs8996_poll >> (28 - 4 * v390_j)) & 0xf];
		}
		v390_buf[40] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v390_buf); }
	}
'''
    src = src.replace(anchor, anchor + probe, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v390: bsdinit pinned-row v390 probe inserted")
else:
    print("patch_v390: bsd_init.c already patched -- skip")

print("patch_v390: done")
