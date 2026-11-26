#!/usr/bin/env python3
"""g0245d v391: C2 step 2 -- DME_LINKSTARTUP over the UIC command interface.

v390 verdict (photo 2026-11-26 22:40): e=00000001 h=0000010f n=00000000 s=6.
LK left HCE enabled before hand-off (e bit0=1, no poll needed) and HCS reads
0x0000010f: UTRLRDY/UTMRLRDY/UICRDY all set, bit8 = UIC command interface
ready on this class of controller.  The enable stage passed with zero work,
so C2 continues directly with the link.

v391 issues DME_LINKSTARTUP (UIC opcode 0x16) exactly the way the proven
NioUfs driver on this SoC family does (its hostUicCommand, "the EDK2 way",
UfsPassThruDxe UfsSendUicCmd):

    ack stale UCCS (IS bit10 @ 0x20) if set
    wait for HCS.UCRDY (bit3 @ 0x30), bounded 100k
    zero ARG1..ARG3 (0x94/0x98/0x9c), write opcode 0x16 into UICCMD (0x90)
    poll IS bit10 (UCCS), bounded 100k
    result = ARG2 (0x98) low byte  (0 = success for LINKSTARTUP)
    ack UCCS

Register offsets 0x90/0x94/0x98/0x9c come from the silicon's own header
(UfsHostBridge.h, listed in NioUfs.cpp:2195-2196) -- NOT the JEDEC 0x60 map.

New pinned row (after the v390 row):

    v391 i=00000000 r=0 d=00000000 q=00 s=0

- i: IS before the sequence (bit10 = stale UCCS was pending)
- r: UCRDY wait (1 = ready seen, 2 = timeout -- sequence not attempted)
- d: UCCS wait iterations (100000+ = command never completed)
- q: DME result low byte (00 = link startup ok)
- s: driver step (7 = link startup stage done)

Judgement table:
- s=7 q=00          => link is up: controller <-> device serial link alive
- s=7 r=2           => UCRDY never set: UIC interface not ready
- s=7 d>=100000     => command never completed: link/device suspect
- s=7 q!=00         => DME reported failure (result codes: 1 = generic fail;
                       PA error codes land in 0x38/DL 0x3c in the ring)
- bus exception     => v389 console lines catch ESR/pc

Idempotent via "g0245d v391" markers.
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
HDR = DEV / "drivers" / "NativeUfs8996" / "Ufs8996Regs.h"
CPP = DEV / "drivers" / "NativeUfs8996" / "NativeUfs8996.cpp"
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
for f in (HDR, CPP, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------ header constants
src = HDR.read_text(encoding="utf-8")
if "g0245d v391" not in src:
    anchor = "constexpr unsigned REG_HCE   = 0x34;  // REG_CONTROLLER_ENABLE (read-only here)\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v391: REG_HCE anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "\n"
        "// UIC command interface (g0245d v391; offsets from the silicon's own\n"
        "// UfsHostBridge.h as listed by NioUfs.cpp -- NOT the JEDEC 0x60 map).\n"
        "constexpr unsigned REG_UICCMD     = 0x90;  // command opcode\n"
        "constexpr unsigned REG_UICCMDARG1 = 0x94;\n"
        "constexpr unsigned REG_UICCMDARG2 = 0x98;\n"
        "constexpr unsigned REG_UICCMDARG3 = 0x9c;\n"
        "constexpr unsigned IS_UCCS        = (1u << 10);  // command completion\n"
        "constexpr unsigned UIC_DME_LINK_STARTUP = 0x16u;\n", 1)
    HDR.write_text(src, encoding="utf-8")
    print("patch_v391: UIC register constants added")
else:
    print("patch_v391: header already patched -- skip")

# ------------------------------------------------------------- driver changes
src = CPP.read_text(encoding="utf-8")
if "g0245d v391" not in src:
    # 1) new probe-state globals after the v390 block
    anchor = "volatile uint32_t ufs8996_en         = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v391: globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v391: C2 link-startup probe state.\n"
        "volatile uint32_t ufs8996_uic_is     = 0;\n"
        "volatile uint32_t ufs8996_uic_ready  = 0;\n"
        "volatile uint32_t ufs8996_uic_spins  = 0;\n"
        "volatile uint32_t ufs8996_uic_result = 0;\n"
        "volatile uint32_t ufs8996_uic_hcs    = 0;\n", 1)

    # 2) link-startup sequence after the v390 HCE block
    anchor = (
        "  ufs8996_step = 6;\n"
        '  g0245d_trace_u("v390 hce", ufs8996_hce_before);\n'
        '  g0245d_trace_u("v390 hcs", ufs8996_hcs_after);\n'
        "  return true;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v391: v390 tail anchor found %d times" % n)
    inject = (
        "  ufs8996_step = 6;\n"
        '  g0245d_trace_u("v390 hce", ufs8996_hce_before);\n'
        '  g0245d_trace_u("v390 hcs", ufs8996_hcs_after);\n'
        "\n"
        "  /* g0245d v391: C2 step 2 -- DME_LINKSTARTUP via the UIC command\n"
        "   * interface, the proven NioUfs/EDK2 sequence.  Bounded everywhere:\n"
        "   * a silent controller must degrade to a status row, not hang. */\n"
        "  ufs8996_uic_is = read32(fBase, Ufs8996::REG_IS);\n"
        "  if (ufs8996_uic_is & Ufs8996::IS_UCCS) {\n"
        "    write32(fBase, Ufs8996::REG_IS, Ufs8996::IS_UCCS); /* ack stale */\n"
        "  }\n"
        "  {\n"
        "    unsigned int v391_i;\n"
        "    ufs8996_uic_ready = 2u;\n"
        "    for (v391_i = 0; v391_i < 100000u; v391_i++) {\n"
        "      if (read32(fBase, Ufs8996::REG_HCS) & Ufs8996::HCS_UCRDY) {\n"
        "        ufs8996_uic_ready = 1u;\n"
        "        break;\n"
        "      }\n"
        "    }\n"
        "    if (ufs8996_uic_ready == 1u) {\n"
        "      write32(fBase, Ufs8996::REG_UICCMDARG1, 0u);\n"
        "      write32(fBase, Ufs8996::REG_UICCMDARG2, 0u);\n"
        "      write32(fBase, Ufs8996::REG_UICCMDARG3, 0u);\n"
        "      write32(fBase, Ufs8996::REG_UICCMD,\n"
        "              Ufs8996::UIC_DME_LINK_STARTUP);\n"
        "      unsigned int v391_w;\n"
        "      for (v391_w = 0; v391_w < 100000u; v391_w++) {\n"
        "        if (read32(fBase, Ufs8996::REG_IS) & Ufs8996::IS_UCCS) {\n"
        "          break;\n"
        "        }\n"
        "      }\n"
        "      ufs8996_uic_spins = v391_w;\n"
        "      ufs8996_uic_result =\n"
        "          read32(fBase, Ufs8996::REG_UICCMDARG2) & 0xffu;\n"
        "      write32(fBase, Ufs8996::REG_IS, Ufs8996::IS_UCCS);\n"
        "    }\n"
        "  }\n"
        "  ufs8996_uic_hcs = read32(fBase, Ufs8996::REG_HCS);\n"
        "  ufs8996_step = 7;\n"
        '  g0245d_trace_u("v391 ls", ufs8996_uic_result);\n'
        "  return true;\n"
    )
    src = src.replace(anchor, inject, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v391: driver link-startup sequence added")
else:
    print("patch_v391: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v391" not in src:
    anchor = (
        "\t\t{ extern void g0245d_probe(const char *);\n"
        "\t\t  g0245d_probe(v390_buf); }\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v391: v390 row tail anchor in bsd_init.c found %d times" % n)
    probe = r'''
	/* g0245d v391: C2 link-startup result, pinned row.
	 * i = IS before (bit10 = stale UCCS), r = UCRDY wait (1 ok / 2 timeout),
	 * d = UCCS wait iterations, q = DME result byte (00 = link up),
	 * s = driver step (7 = link startup stage done). */
	{
		static char v391_buf[] = "v391 i=00000000 r=0 d=00000000 q=00 s=0";
		extern volatile unsigned int ufs8996_uic_is;
		extern volatile unsigned int ufs8996_uic_ready;
		extern volatile unsigned int ufs8996_uic_spins;
		extern volatile unsigned int ufs8996_uic_result;
		extern volatile unsigned int ufs8996_step;
		unsigned int v391_j;
		for (v391_j = 0; v391_j < 8; v391_j++) {
			v391_buf[7 + v391_j] =
			    "0123456789abcdef"[(ufs8996_uic_is >> (28 - 4 * v391_j)) & 0xf];
			v391_buf[22 + v391_j] =
			    "0123456789abcdef"[(ufs8996_uic_spins >> (28 - 4 * v391_j)) & 0xf];
		}
		v391_buf[18] = (ufs8996_uic_ready < 10)
		    ? (char)('0' + ufs8996_uic_ready) : '?';
		v391_buf[33] =
		    "0123456789abcdef"[(ufs8996_uic_result >> 4) & 0xf];
		v391_buf[34] =
		    "0123456789abcdef"[ufs8996_uic_result & 0xf];
		v391_buf[38] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v391_buf); }
	}
'''
    src = src.replace(anchor, anchor + probe, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v391: bsdinit pinned-row v391 probe inserted")
else:
    print("patch_v391: bsd_init.c already patched -- skip")

print("patch_v391: done")
