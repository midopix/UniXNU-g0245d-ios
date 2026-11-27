#!/usr/bin/env python3
"""g0245d v393: C2 step 2c -- recover from the DME_LINKSTARTUP q=01 failure.

v392 verdict (photo 2026-11-27 09:21):
    v392 p=00000000 d=00000000 n=00000000 t=00000000 e=00000001

PA/DL/NL/TL error registers are all zero.  UECDME reports only the generic
DME error code (bit0=1; no ERR bit31, no layer-specific cause).  This matches
the known UFS recovery path in Linux 3.18: after any DME_LINKSTARTUP failure,
reset UniPro, re-enable it, and retry LINKSTARTUP up to three times.

v393 changes exactly one suspect point: when v391's q != 0, issue the
NioUfs/EDK2 recovery sequence **DME_RESET (0x14) -> DME_ENABLE (0x12) ->
DME_LINKSTARTUP (0x16)**, each through the same bounded UIC command helper,
and print the three result bytes plus the retried command's completion spins.

New pinned row:

    v393 a=00000000 b=00000000 r=00000000 d=00000000 q=1 s=8

- a = DME_RESET result, b = DME_ENABLE result
- r = retried DME_LINKSTARTUP result (00 = link up)
- d = retried UCCS wait iterations (100000+ = no completion)
- q = retried UCRDY wait (1 = ready, 2 = timeout)
- s = driver step (8 = recovery stage done)

No HCE toggle, no clock/PHY write, no UTP traffic.  Idempotent via
"g0245d v393" markers.
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
if "g0245d v393" not in src:
    anchor = "constexpr unsigned REG_UIC_ERR_DME = 0x48;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v393: v392 header tail anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "\n"
        "// UniPro recovery opcodes (g0245d v393; same UIC command interface).\n"
        "constexpr unsigned UIC_DME_ENABLE  = 0x12u;\n"
        "constexpr unsigned UIC_DME_RESET   = 0x14u;\n", 1)
    HDR.write_text(src, encoding="utf-8")
    print("patch_v393: recovery UIC opcodes added")
else:
    print("patch_v393: header already patched -- skip")

# ------------------------------------------------------------- driver changes
src = CPP.read_text(encoding="utf-8")
if "g0245d v393" not in src:
    # 1) bounded UIC command helper, shared by all three recovery commands
    anchor = "} // namespace\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v393: namespace tail anchor found %d times" % n)
    helper = r'''
// g0245d v393: one bounded UIC command, identical to the proven v391 sequence.
// result 0xfe means "not attempted" because UCRDY never arrived.
struct UicRecoveryResult {
  uint32_t is;
  uint32_t ready;
  uint32_t spins;
  uint32_t result;
};

static UicRecoveryResult uicRecoveryCommand(uintptr_t base, unsigned opcode)
{
  UicRecoveryResult out;
  out.is = 0;
  out.ready = 2u;
  out.spins = 100000u;
  out.result = 0xfeu;

  out.is = *reinterpret_cast<volatile uint32_t *>(
      base + Ufs8996::REG_IS);
  if (out.is & Ufs8996::IS_UCCS) {
    *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_IS) =
        Ufs8996::IS_UCCS;
  }
  for (unsigned int i = 0; i < 100000u; i++) {
    if (*reinterpret_cast<volatile uint32_t *>(
            base + Ufs8996::REG_HCS) & Ufs8996::HCS_UCRDY) {
      out.ready = 1u;
      break;
    }
  }
  if (out.ready != 1u) { return out; }

  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG1) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG2) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMDARG3) = 0u;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_UICCMD) = opcode;
  for (unsigned int w = 0; w < 100000u; w++) {
    if (*reinterpret_cast<volatile uint32_t *>(
            base + Ufs8996::REG_IS) & Ufs8996::IS_UCCS) {
      out.spins = w;
      break;
    }
  }
  out.result = *reinterpret_cast<volatile uint32_t *>(
      base + Ufs8996::REG_UICCMDARG2) & 0xffu;
  *reinterpret_cast<volatile uint32_t *>(base + Ufs8996::REG_IS) =
      Ufs8996::IS_UCCS;
  return out;
}
'''
    src = src.replace(anchor, helper + anchor, 1)

    # 2) recovery globals after v392's snapshot
    anchor = "volatile uint32_t ufs8996_err_dme = 0;\n"
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v393: globals anchor found %d times" % n)
    src = src.replace(anchor, anchor +
        "// g0245d v393: one-shot UniPro recovery after q=01.\n"
        "volatile uint32_t ufs8996_recover_reset  = 0;\n"
        "volatile uint32_t ufs8996_recover_enable = 0;\n"
        "volatile uint32_t ufs8996_recover_result = 0;\n"
        "volatile uint32_t ufs8996_recover_spins  = 0;\n"
        "volatile uint32_t ufs8996_recover_ready  = 0;\n", 1)

    # 3) recovery sequence after the v392 read-only snapshot
    anchor = (
        "  ufs8996_err_pa  = read32(fBase, Ufs8996::REG_UIC_ERR_PA);\n"
        "  ufs8996_err_dl  = read32(fBase, Ufs8996::REG_UIC_ERR_DL);\n"
        "  ufs8996_err_nl  = read32(fBase, Ufs8996::REG_UIC_ERR_NL);\n"
        "  ufs8996_err_tl  = read32(fBase, Ufs8996::REG_UIC_ERR_TL);\n"
        "  ufs8996_err_dme = read32(fBase, Ufs8996::REG_UIC_ERR_DME);\n"
        "\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v393: v392 snapshot anchor found %d times" % n)
    inject = anchor + r'''
  /* g0245d v393: q=01 + only a generic DME error => reset UniPro,
   * enable it again, then retry LINKSTARTUP once.  All three commands use
   * the same bounded helper; no HCE/clock/PHY write. */
  if (ufs8996_uic_result != 0u) {
    UicRecoveryResult v393_r;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_RESET);
    ufs8996_recover_reset = v393_r.result;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_ENABLE);
    ufs8996_recover_enable = v393_r.result;
    v393_r = uicRecoveryCommand(fBase, Ufs8996::UIC_DME_LINK_STARTUP);
    ufs8996_recover_result = v393_r.result;
    ufs8996_recover_spins  = v393_r.spins;
    ufs8996_recover_ready  = v393_r.ready;
    ufs8996_step = 8;
    g0245d_trace_u("v393 retry", ufs8996_recover_result);
  }
'''
    src = src.replace(anchor, inject, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v393: driver recovery sequence added")
else:
    print("patch_v393: driver already patched -- skip")

# ----------------------------------------------------------- bsd_init.c row
src = BSD.read_text(encoding="utf-8")
if "g0245d v393" not in src:
    anchor = (
        "\t\t{ extern void g0245d_probe(const char *);\n"
        "\t\t  g0245d_probe(v392_buf); }\n"
        "\t}\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v393: v392 row tail anchor in bsd_init.c found %d times" % n)
    probe = r'''
	/* g0245d v393: UniPro recovery result after the v391 q=01 failure. */
	{
		static char v393_buf[] =
		    "v393 a=00000000 b=00000000 r=00000000 d=00000000 q=1 s=8";
		extern volatile unsigned int ufs8996_recover_reset;
		extern volatile unsigned int ufs8996_recover_enable;
		extern volatile unsigned int ufs8996_recover_result;
		extern volatile unsigned int ufs8996_recover_spins;
		extern volatile unsigned int ufs8996_recover_ready;
		extern volatile unsigned int ufs8996_step;
		static const unsigned char v393_off[4] = { 7, 18, 29, 40 };
		volatile unsigned int *v393_ptr[4] = {
			&ufs8996_recover_reset, &ufs8996_recover_enable,
			&ufs8996_recover_result, &ufs8996_recover_spins
		};
		unsigned int v393_i;
		unsigned int v393_j;
		for (v393_i = 0; v393_i < 4; v393_i++) {
			unsigned int v393_v = *v393_ptr[v393_i];
			for (v393_j = 0; v393_j < 8; v393_j++) {
				v393_buf[v393_off[v393_i] + v393_j] =
				    "0123456789abcdef"[(v393_v >> (28 - 4 * v393_j)) & 0xf];
			}
		}
		v393_buf[51] = (ufs8996_recover_ready < 10)
		    ? (char)('0' + ufs8996_recover_ready) : '?';
		v393_buf[55] = (ufs8996_step < 10)
		    ? (char)('0' + ufs8996_step) : '?';
		{ extern void g0245d_probe(const char *);
		  g0245d_probe(v393_buf); }
	}
'''
    src = src.replace(anchor, anchor + probe, 1)
    BSD.write_text(src, encoding="utf-8")
    print("patch_v393: bsdinit pinned-row v393 probe inserted")
else:
    print("patch_v393: bsd_init.c already patched -- skip")

print("patch_v393: done")
