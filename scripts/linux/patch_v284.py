#!/usr/bin/env python3
"""g0245d v284 -- GIC delivery diagnostics.

v283 boot picture decoded:

  * state.json proves the flash: md5 902cf562... ok at 20:40:26.  The photo
     30 minutes later still freezes at "v281 cfg done" (hb 8436/8394) --
     identical seq to v282.  No "iobsd tmo" despite the 3 s deadline, so
     the GIC patch did NOT result in a delivered timer interrupt.
  * Note: pe_init_fiq's kprintf("G0245D GICv2: ...") adds zero console
     writes (seq parity with v282) because PE_init_cpu runs before the
     framebuffer console is created -- no information there.

Three blind spots, one probe each:

  1. Readback: GICD_CTLR / GICD_IGROUPR0 / GICC_CTLR printed right after
     the v283 writes.  TrustZone silently blocking NS writes shows up as
     zero readback.  (pe_init_fiq, C file, extern g0245d_trace_u.)
  2. Self-test: arm CNTV ~250 ms out (CNTFRQ from CNTFRQ_EL0) and enable
     CNTV_CTL in case _enable_virtual_timer has not run yet.  Any
     delivered interrupt now prints "v284 irq <intid>" from sleh_irq
     (capped at 8 prints to keep the ring readable).
  3. DAIF at the IOFindBSDRoot wait point -- rules out "the kernel never
     unmasks IRQ on this path".
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

PEFIQ = os.path.join(WORK, "pexpert/arm/pe_fiq.c")
SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")
BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")

MARK = "g0245d v284"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what):
    n = src.count(old)
    if n != 1:
        sys.exit("%s: anchor found %d times" % (what, n))
    return src.replace(old, new)


# --- 1. pe_fiq.c: readbacks + self-armed test timer ----------------------
s = read(PEFIQ)
if MARK not in s:
    s = sub(
        s,
        """		gicd[0x100 / 4] = (1u << G0245D_VTIMER_INTID) |
		    (1u << G0245D_IPI_SGI);          /* ISENABLER0 */
		gicd[0x000 / 4] |= 0x3u;             /* CTLR: enable grp0+grp1 */
	}
}""",
        """		gicd[0x100 / 4] = (1u << G0245D_VTIMER_INTID) |
		    (1u << G0245D_IPI_SGI);          /* ISENABLER0 */
		gicd[0x000 / 4] |= 0x3u;             /* CTLR: enable grp0+grp1 */
	}

	/* g0245d v284: read back what we wrote.  TrustZone silently eating
	 * NS writes shows up as zero here. */
	{
		extern void g0245d_trace_u(const char *, unsigned int);
		volatile unsigned int *gicd =
		    (volatile unsigned int *)g0245d_gicd_base;
		volatile unsigned int *gicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		g0245d_trace_u("v284 gicd ctlr", gicd[0x000 / 4]);
		g0245d_trace_u("v284 gicd igrp0", gicd[0x080 / 4]);
		g0245d_trace_u("v284 gicc ctlr", gicc[0x000 / 4]);
	}

	/* g0245d v284: self-test -- arm the virtual timer ~250 ms out and
	 * enable CNTV (in case _enable_virtual_timer has not run yet).
	 * If the GIC delivers, sleh_irq logs "v284 irq <intid>". */
	{
		extern void g0245d_trace_u(const char *, unsigned int);
		uint64_t frq = __builtin_arm_rsr64("CNTFRQ_EL0");
		uint64_t now = __builtin_arm_rsr64("CNTVCT_EL0");
		__builtin_arm_wsr64("CNTV_CVAL_EL0", now + frq / 4);
		__builtin_arm_wsr64("CNTV_CTL_EL0", 1);	/* enable, unmasked */
		g0245d_trace_u("v284 cval armed", (unsigned int)frq);
	}
}""",
        "pe_fiq: readbacks + test timer",
    )
    write(PEFIQ, s)
    print("pe_fiq.c: v284 diagnostics added")
else:
    print("pe_fiq.c: already patched")

# --- 2. sleh.c: log the first few interrupts ------------------------------
s = read(SLEH)
if "v284 irq" not in s:
    s = sub(
        s,
        """		iar = gicc[0x0C / 4];		/* IAR */
		intid = iar & 0x3FFu;
		if (intid >= 1020) {
			return;			/* spurious: no EOI */
		}""",
        """		iar = gicc[0x0C / 4];		/* IAR */
		intid = iar & 0x3FFu;
		{
			/* g0245d v284: log the first 8 interrupts (capped so
			 * a storm cannot wash the ring out). */
			static int g0245d_irq_logged;
			if (g0245d_irq_logged < 8) {
				g0245d_irq_logged++;
				extern void g0245d_trace_u(const char *,
				    unsigned int);
				g0245d_trace_u("v284 irq", intid);
			}
		}
		if (intid >= 1020) {
			return;			/* spurious: no EOI */
		}""",
        "sleh: irq logging",
    )
    write(SLEH, s)
    print("sleh.c: irq logging added")
else:
    print("sleh.c: already patched")

# --- 3. IOKitBSDInit.cpp: DAIF at the wait point --------------------------
s = read(BSDINIT)
if "v284 daif" not in s:
    s = sub(
        s,
        """IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        """extern "C" void g0245d_trace_u(const char *label, unsigned int value);

IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        "fbr: trace_u decl",
    )
    s = sub(
        s,
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v282 fbr prewait"); }""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v282 fbr prewait"); }
	g0245d_trace_u("v284 daif", __builtin_arm_rsr("DAIF"));""",
        "fbr: DAIF probe",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: DAIF probe added")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v284 done")
