#!/usr/bin/env python3
"""g0245d v283 -- MSM8996 interrupt bring-up: GIC-400 (GICv2) + vtimer IRQ.

v282 boot picture decoded (decisive):

  * "v282 fbr prewait" printed, then the uuid sequence and "v281 cfg done"
     (8435).  THIRTY-ONE MINUTES later the console is still frozen there:
     waitForMatchingService(IOBSD, 3 s) returned neither by match nor by
     its own deadline.  Conclusion: ALL thread sleep/wake paths hang --
     deadline waits included.  Same wall family as every KM_SLEEP hang
     (mbinit, fbt): the kernel has NO working interrupt-driven wake path.

Upstream survey (github, other UniXNU device ports):

  * yecw/UniXNU-kebab patches/xnu/10063-kebab-gic-vtimer.patch: SM8250.
    TrustZone owns GIC Group 0, so timer/IPIs arrive as Group 1 IRQs.
    pe_init_fiq() inits the GIC, sleh_irq() dispatches by INTID read from
    ICC_IAR1_EL1: vtimer -> rtclock_intr, <16 -> cpu_signal_handler,
    else -> cdp->interrupt_handler.  This is what makes timed waits work.
  * MikelikeXiaoyezi/UniXNU-munch 0017: virtual-timer INTID from DT.
  * obaosp/UniXNU-cupid: Gunyah traps CNTP; kernel stays on CNTV.
  * Our tree: pe_init_fiq()'s non-GIC branch is EMPTY (pe_fiq.c #else),
    and sleh_irq() calls cdp->interrupt_handler directly -- nothing has
    ever been initialized, no IRQ ever delivered.

g0245d facts:

  * machine_routines.c _enable_virtual_timer() enables CNTV and masks
    CNTP => the deadline interrupt is the virtual timer PPI.  On
    MSM8996 (GIC-400, GICv2) mainline DT wires the virtual timer to
    GIC_PPI 11 = INTID 27 (kebab/sweet use 27 as well).
  * GIC-400 windows (mainline msm8996.dtsi): GICD @0x09BC0000 (0x1000),
    GICC @0x09BC2000 (0x2000).  GICv2 is MMIO: GICC_IAR/EOIR, not the
    GICv3 sysregs kebab uses.

v283 changes:

  1. BCM2837.h: G0245D_GICV2 + GIC window / INTID defines.
  2. pe_fiq.c: new #elif G0245D_GICV2 pe_init_fiq() -- map GICD/GICC,
     all groups to Group 1 (TrustZone owns Group 0), enable INTID 27
     (vtimer) + SGI 1 (IPI), enable GICD + GICC.
  3. sleh.c sleh_irq(): G0245D_IRQ_DISPATCH branch -- read GICC_IAR,
     ack, dispatch: INTID 27 -> rtclock_intr(TRUE); <16 -> EOI then
     cpu_signal_handler(); else -> cdp->interrupt_handler if present,
     then EOI.  Spurious (>=1020) returns without EOI.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BOARD = os.path.join(WORK, "pexpert/pexpert/arm64/BCM2837.h")
PEFIQ = os.path.join(WORK, "pexpert/arm/pe_fiq.c")
SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")

MARK = "g0245d v283"


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


# --- 1. BCM2837.h --------------------------------------------------------
s = read(BOARD)
if "G0245D_GICV2" not in s:
    s = sub(
        s,
        """#define BCM2837_BRINGUP
#define ARM_ARCH_TIMER""",
        """#define BCM2837_BRINGUP
#define ARM_ARCH_TIMER

/* g0245d v283: MSM8996 interrupt bring-up.  GIC-400 (GICv2, MMIO);
 * TrustZone owns Group 0, so everything we use is Group 1 NS and arrives
 * as IRQs in sleh_irq().  XNU runs on the virtual timer (CNTV, see
 * _enable_virtual_timer), whose PPI is INTID 27 (GIC_PPI 11 in mainline
 * msm8996.dtsi).  Blueprint: kebab 10063-gic-vtimer (SM8250), munch 0017,
 * cupid (trapped phys timer -> stay on virtual). */
#define G0245D_GICV2 1
#define G0245D_GICD_BASE 0x09BC0000
#define G0245D_GICD_SIZE 0x1000
#define G0245D_GICC_BASE 0x09BC2000
#define G0245D_GICC_SIZE 0x2000
#define G0245D_VTIMER_INTID 27
#define G0245D_IPI_SGI 1""",
        "board: GICv2 defines",
    )
    write(BOARD, s)
    print("BCM2837.h: G0245D_GICV2 defines added")
else:
    print("BCM2837.h: already patched")

# --- 2. pe_fiq.c ---------------------------------------------------------
s = read(PEFIQ)
if "G0245D_GICV2" not in s:
    s = sub(
        s,
        """#else
void
pe_init_fiq()
{
}
#endif""",
        """#elif defined(G0245D_GICV2)
/* g0245d v283: GIC-400 (GICv2, MMIO).  Per-PE state lives in the GICC
 * view (banked); shared state in GICD.  TrustZone owns Group 0 on this
 * platform, so all our interrupts are Group 1 NS and surface as IRQs
 * handled by sleh_irq(). */
static vm_offset_t g0245d_gicd_base;
static vm_offset_t g0245d_gicc_base;

void
pe_init_fiq()
{
	if (!g0245d_gicd_base) {
		g0245d_gicd_base = ml_io_map(G0245D_GICD_BASE, G0245D_GICD_SIZE);
		g0245d_gicc_base = ml_io_map(G0245D_GICC_BASE, G0245D_GICC_SIZE);
		kprintf("G0245D GICv2: gicd@%08x gicc@%08x\\n",
		    (unsigned int)G0245D_GICD_BASE,
		    (unsigned int)G0245D_GICC_BASE);
	}

	/* GICC: this PE's view */
	{
		volatile unsigned int *gicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		gicc[0x04 / 4] = 0xFF;  /* PMR: pass all priorities */
		gicc[0x1C / 4] = 0;     /* BPR1 */
		gicc[0x00 / 4] = 0x3;   /* CTLR: enable + signal Group 1 as IRQ */
	}

	/* GICD: shared */
	{
		volatile unsigned int *gicd =
		    (volatile unsigned int *)g0245d_gicd_base;
		int i;
		/* IGROUPR0..7: SGI+PPI+SPI all Group 1 (TZ owns Group 0) */
		for (i = 0; i < 8; i++) {
			gicd[0x080 / 4 + i] = 0xFFFFFFFFu;
		}
		gicd[0x400 / 4] = 0xA0A0A0A0u;       /* IPRIORITYR0: SGI 1 */
		gicd[0x400 / 4 + 6] = 0xA0A0A0A0u;   /* IPRIORITYR6: INTID 27 */
		gicd[0x100 / 4] = (1u << G0245D_VTIMER_INTID) |
		    (1u << G0245D_IPI_SGI);          /* ISENABLER0 */
		gicd[0x000 / 4] |= 0x3u;             /* CTLR: enable grp0+grp1 */
	}
}
#else
void
pe_init_fiq()
{
}
#endif""",
        "pe_fiq: GICv2 branch",
    )
    write(PEFIQ, s)
    print("pe_fiq.c: GICv2 pe_init_fiq added")
else:
    print("pe_fiq.c: already patched")

# --- 3. sleh.c -----------------------------------------------------------
s = read(SLEH)
if "G0245D_IRQ_DISPATCH" not in s:
    s = sub(
        s,
        """#include <arm/rtclock.h>""",
        """#include <arm/rtclock.h>
#include <arm/machine_cpu.h>	/* g0245d v283: cpu_signal_handler */""",
        "sleh: machine_cpu include",
    )
    s = sub(
        s,
        """sleh_irq(arm_saved_state_t *state)
{
	cpu_data_t * cdp __unused             = getCpuDatap();""",
        """#define G0245D_IRQ_DISPATCH 1	/* g0245d v283 */

sleh_irq(arm_saved_state_t *state)
{
	cpu_data_t * cdp __unused             = getCpuDatap();""",
        "sleh: dispatch marker",
    )
    s = sub(
        s,
        """#endif


	sleh_interrupt_handler_prologue(state, DBG_INTR_TYPE_OTHER);
	boot_progress_irq(get_saved_state_pc(state), get_saved_state_cpsr(state), get_saved_state_sp(state));

#if USE_APPLEARMSMP
	PE_handle_ext_interrupt();
#else
	/* Run the registered interrupt handler. */
	cdp->interrupt_handler(cdp->interrupt_target,
	    cdp->interrupt_refCon,
	    cdp->interrupt_nub,
	    cdp->interrupt_source);
#endif""",
        """#endif

#if defined(G0245D_IRQ_DISPATCH)
	{
		/* g0245d v283: GIC-400 (GICv2) IRQ dispatch.  Timer and IPIs
		 * are Group 1 NS and arrive here as IRQs (TrustZone owns
		 * Group 0 -- same as kebab).  Virtual timer PPI = INTID 27. */
		extern vm_offset_t g0245d_gicc_base;
		volatile unsigned int *gicc;
		unsigned int iar, intid;
		unsigned int dbgtype = DBG_INTR_TYPE_OTHER;

		if (g0245d_gicc_base == 0) {
			return;	/* GIC not initialized yet */
		}
		gicc = (volatile unsigned int *)g0245d_gicc_base;
		iar = gicc[0x0C / 4];		/* IAR */
		intid = iar & 0x3FFu;
		if (intid >= 1020) {
			return;			/* spurious: no EOI */
		}
		if (intid == G0245D_VTIMER_INTID) {
			dbgtype = DBG_INTR_TYPE_TIMER;
		} else if (intid < 16) {
			dbgtype = DBG_INTR_TYPE_IPI;
		}
		sleh_interrupt_handler_prologue(state, dbgtype);
		if (intid == G0245D_VTIMER_INTID) {
			cdp->cpu_decrementer = -1;	/* Large */
			rtclock_intr(TRUE);
		} else if (intid < 16) {
			gicc[0x10 / 4] = iar;	/* EOI before handling */
			__builtin_arm_isb(0xF);	/* ISB SY */
			cpu_signal_handler();
		} else {
			if (cdp->interrupt_handler) {
				cdp->interrupt_handler(cdp->interrupt_target,
				    cdp->interrupt_refCon,
				    cdp->interrupt_nub,
				    intid);
			}
			gicc[0x10 / 4] = iar;	/* EOI */
		}
		entropy_collect();
		sleh_interrupt_handler_epilogue();
		return;
	}
#endif

	sleh_interrupt_handler_prologue(state, DBG_INTR_TYPE_OTHER);
	boot_progress_irq(get_saved_state_pc(state), get_saved_state_cpsr(state), get_saved_state_sp(state));

#if USE_APPLEARMSMP
	PE_handle_ext_interrupt();
#else
	/* Run the registered interrupt handler. */
	cdp->interrupt_handler(cdp->interrupt_target,
	    cdp->interrupt_refCon,
	    cdp->interrupt_nub,
	    cdp->interrupt_source);
#endif""",
        "sleh: GICv2 dispatch branch",
    )
    write(SLEH, s)
    print("sleh.c: GICv2 dispatch branch added")
else:
    print("sleh.c: already patched")

print("v283 done")
