#!/usr/bin/env python3
"""g0245d v392: C2 step 2b -- decode the DME_LINKSTARTUP failure.

v391 verdict (photo 2026-11-27 09:10):
    v391 i=00000000 r=1 d=00000000 q=01 s=7

- i=0: no stale UCCS before the command
- r=1: HCS.UCRDY was already set
- d=0: UIC command completed on the first poll
- q=1: DME_LINKSTARTUP returned the generic failure code
- s=7: the sequence ran to completion (no bus exception, no hang)

q=01 is deliberately non-specific.  The controller exposes the precise
failing UniPro layer in five read-only error-code registers defined by the
stock msm-3.18 header (refs/ufs-linux-3.18/scsi/ufshci.h):

    0x38 PA, 0x3c DL, 0x40 NL, 0x44 TL, 0x48 DME

v392 changes exactly one suspect point: after the v391 LINKSTARTUP sequence,
read those five registers and pin them on a new console row.  No UIC command,
no reset, no DME attribute write, no HCE/clock change.  If all five are zero,
the failure is not a UniPro layer error and the next step is to try the
device descriptor query directly.

New pinned row:

    v392 p=00000000 d=00000000 n=00000000 t=00000000 e=00000000 s=7

- p = PA error register (0x38), d = DL (0x3c), n = NL (0x40)
- t = TL (0x44), e = DME (0x48), s = driver step

Idempotent via "g0245d v392" markers.
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
if "g0245d v392" not in src:
    anchor = "constexpr unsigned UIC_DME_LINK_STARTUP = 0x16u;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v392: UIC_DME_LINK_STARTUP anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "\n"
        "// UIC layer error-code registers (g0245d v392; read-only decode of\n"
        "// the v391 q=01 result; offsets from msm-3.18 scsi/ufshci.h).\n"
        "constexpr unsigned REG_UIC_ERR_PA  = 0x38;\n"
        "constexpr unsigned REG_UIC_ERR_DL  = 0x3c;\n"
        "constexpr unsigned REG_UIC_ERR_NL  = 0x40;\n"
        "constexpr unsigned REG_UIC_ERR_TL  = 0x44;\n"
        "constexpr unsigned REG_UIC_ERR_DME = 0x48;\n", 1)
    HDR.write_text(src, encoding="utf-8")
    print("patch_v392: UIC error-register constants added")
else:
    print("patch_v392: header already patched -- skip")

# ------------------------------------------------------------- driver changes
src = CPP.read_text(encoding="utf-8")
if "g0245d v392" not in src:
    anchor = "volatile uint32_t ufs8996_uic_hcs    = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v392: globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v392: UIC layer error-code snapshot.\n"
        "volatile uint32_t ufs8996_err_pa  = 0;\n"
        "volatile uint32_t ufs8996_err_dl  = 0;\n"
        "volatile uint32_t ufs8996_err_nl  = 0;\n"
        "volatile uint32_t ufs8996_err_tl  = 0;\n"
        "volatile uint32_t ufs8996_err_dme = 0;\n", 1)

    anchor = (
        "  ufs8996_uic_hcs = read32(fBase, Ufs8996::REG_HCS);\n"
        "  ufs8996_step = 7;\n"
        '  g0245d_trace_u("v391 ls", ufs8996_uic_result);\n'
        "  return true;\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v392: v391 tail anchor found %d times" % n)
    inject = (
        "  ufs8996_uic_hcs = read32(fBase, Ufs8996::REG_HCS);\n"
        "\n"
        "  /* g0245d v392: q=01 is only a generic DME failure.  Decode which\n"
        "   * UniPro layer reported it, without issuing another UIC command. */\n"
        "  ufs8996_err_pa  = read32(fBase, Ufs8996::REG_UIC_ERR_PA);\n"
        "  ufs8996_err_dl  = read32(fBase, Ufs8996::REG_UIC_ERR_DL);\n"
        "  ufs8996_err_nl  = read32(fBase, Ufs8996::REG_UIC_ERR_NL);\n"
        "  ufs8996_err_tl  = read32(fBase, Ufs8996::REG_UIC_ERR_TL);\n"
        "  ufs8996_err_dme = read32(fBase, Ufs8996::REG_UIC_ERR_DME);\n"
        "\n"
        "  ufs8996_step = 7;\n"
        '  g0245d_trace_u("v391 ls", ufs8996_uic_result);\n'
        "  return true;\n"
    )
    src = src.replace(anchor, inject, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v392: driver error-register snapshot added")
else:
    print("patch_v392: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v392" not in src:
    anchor = (
        "\t\t{ extern void g0245d_probe(const char *);\n"
        "\t\t  g0245d_probe(v391_buf); }\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v392: v391 row tail anchor in bsd_init.c found %d times" % n)
    probe = r'''
	/* g0245d v392: decode of the v391 q=01 result.  p/d/n/t/e are the
	 * read-only UIC error-code registers at 0x38/3c/40/44/48. */
	{
		static char v392_buf[] =
		    "v392 p=00000000 d=00000000 n=00000000 t=00000000 e=00000000 s=7";
		extern volatile unsigned int ufs8996_err_pa;
		extern volatile unsigned int ufs8996_err_dl;
		extern volatile unsigned int ufs8996_err_nl;
		extern volatile unsigned int ufs8996_err_tl;
		extern volatile unsigned int ufs8996_err_dme;
		extern volatile unsigned int ufs8996_step;
		static const unsigned char v392_off[5] = { 7, 18, 29, 40, 51 };
		volatile unsigned int *v392_ptr[5] = {
			&ufs8996_err_pa, &ufs8996_err_dl, &ufs8996_err_nl,
			&ufs8996_err_tl, &ufs8996_err_dme
		};
		unsigned int v392_i;
		unsigned int v392_j;
		for (v392_i = 0; v392_i < 5; v392_i++) {
			unsigned int v392_v = *v392_ptr[v392_i];
			for (v392_j = 0; v392_j < 8; v392_j++) {
				v392_buf[v392_off[v392_i] + v392_j] =
				    "0123456789abcdef"[(v392_v >> (28 - 4 * v392_j)) & 0xf];
			}
		}
		v392_buf[62] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v392_buf); }
	}
'''
    src = src.replace(anchor, anchor + probe, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v392: bsdinit pinned-row v392 probe inserted")
else:
    print("patch_v392: bsd_init.c already patched -- skip")

print("patch_v392: done")
