#!/usr/bin/env python3
"""g0245d v286 -- msm8996 is GICv3, not GICv2.  Full rewrite of the
interrupt bring-up to the kebab sysreg scheme.

Root cause of the v283..v285 silence (upstream research):

  * mainline msm8996.dtsi: intc @0x9bc0000 is "qcom,msm8996-gic-v3" --
    GICD 0x9bc0000/0x10000, GICR 0x9c00000/0x100000, stride 0x40000.
    v283..v285 treated 0x9bc2000 as a GICC and did GICv2 MMIO: reads hit
    the GICR region, iar returned 0 (not even spurious 1023), nothing
    could ever be enabled or delivered.
  * kebab (SM8250) 10063-gic-vtimer is a GICv3 sysreg port: Group 1 NS
    via ICC_IGRPEN1_EL1 / IGROUPR0=0xFFFFFFFF / GICD_CTLR
    ARE_NS|ENABLEGRP1A|ENABLEGRP1, dispatch in sleh_irq from
    ICC_IAR1_EL1.  TrustZone owns Group 0, so timer/IPIs arrive as IRQs.
  * mainline quirk: GICR_WAKER writes are restricted on msm8996 (hyp) --
    mainline skips them; firmware leaves redistributors awake.  We skip
    the WAKER block too.
  * Virtual timer PPI 11 = INTID 27 (mainline armv8-timer node order
    13/14/11/10 -> INTID 29/30/27/26; kernel runs on CNTV).
  * v285 also proved the CPU is NOT the problem: daif=0x200 (only
    SError masked), irqn=0, iar=0 (reads-as-zero GICR region).

v286 changes:

  1. BCM2837.h: HAS_GIC_V3 1 + G0245D_GICV3_G1 1 + kebab's GICR/ICC macro
     set (GICR_PE_SIZE 0x40000 for msm8996).  GICv2 defines kept (dead
     branch still parses).
  2. pe_fiq.c HAS_GIC_V3 branch: hardcoded msm8996 windows (no DT node),
     skip WAKER, Group-1 config (IGROUPR0/ priorities/ ISENABLER0 = 27|1,
     BPR1, GICD_CTLR G1 + RWP wait, ICC_IGRPEN1_EL1), stash readbacks.
  3. sleh.c: dispatch via ICC_IAR1_EL1 / ICC_EOIR1_EL1 (sysreg), keeping
     the irq logging.
  4. IOKitBSDInit.cpp: iar poll via sysreg; extra dump after cfg done so
     all numbers land in the photo-visible bottom rows.
  5. IOPlatformExpert.cpp: dump #2 after "v281 cfg done" (cntv/gicd/igrp/
     igrp1/pmr/daif) using the stashed readbacks.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BOARD = os.path.join(WORK, "pexpert/pexpert/arm64/BCM2837.h")
PEFIQ = os.path.join(WORK, "pexpert/arm/pe_fiq.c")
SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")
BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")
PLAT = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")

MARK = "g0245d v286"


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
if "HAS_GIC_V3" not in s:
    s = sub(
        s,
        """/* g0245d v283: MSM8996 interrupt bring-up.  GIC-400 (GICv2, MMIO);
 * TrustZone owns Group 0, so everything we use is Group 1 NS and arrives
 * as IRQs in sleh_irq().  XNU runs on the virtual timer (CNTV, see
 * _enable_virtual_timer), whose PPI is INTID 27 (GIC_PPI 11 in mainline
 * msm8996.dtsi).  Blueprint: kebab 10063-gic-vtimer (SM8250), munch 0017,
 * cupid (trapped phys timer -> stay on virtual). */
#define G0245D_GICV2 1""",
        """/* g0245d v286: msm8996 is GICv3 ("qcom,msm8996-gic-v3"), NOT GIC-400.
 * v283..v285 did GICv2 MMIO at 0x9bc2000 -- that is inside the GICR
 * region on this SoC, so every read returned garbage (iar=0, no spurious)
 * and nothing could be enabled or delivered.  Blueprint = kebab
 * 10063-gic-vtimer (GICv3 sysregs, Group 1 NS; TrustZone owns Group 0) +
 * cupid (stay on CNTV).  Windows from mainline msm8996.dtsi:
 * GICD 0x9bc0000/0x10000, GICR 0x9c00000/0x100000, stride 0x40000.
 * Virtual timer PPI 11 = INTID 27.  GICR_WAKER writes are restricted on
 * this SoC (mainline "qcom,msm8996-gic-v3" quirk) -- skipped. */
#define HAS_GIC_V3 1
#define G0245D_GICV3_G1 1
#define GIC_SPURIOUS_IRQ 1023
#define GICR_PE_SIZE 0x40000
#define GICD_CTLR 0x0
#define GICD_CTLR_ENABLEGRP1 0x1
#define GICD_CTLR_ENABLEGRP1A 0x2
#define GICD_CTLR_ARE_NS 0x10
#define GICD_CTLR_RWP 0x80000000
#define GICR_TYPER 0x08
#define GICR_WAKER 0x14
#define GICR_IGROUPR0 0x10080
#define GICR_ISENABLER0 0x10100
#define GICR_IPRIORITYR0 0x10400
#define GICR_TYPER_AFFINITY_VALUE_SHIFT 32
#define GICR_TYPER_LAST 0x10
#define GICR_WAKER_PROCESSORSLEEP 0x2
#define GICR_WAKER_CHILDRENASLEEP 0x4
#define ICC_CTLR_EOIMODE 0x2
#define ICC_SRE_SRE 0x1

/* v283 GICv2 attempt (dead code now, kept for the record): */
#define G0245D_GICV2 1""",
        "board: GICv3 defines",
    )
    write(BOARD, s)
    print("BCM2837.h: HAS_GIC_V3 + macro set")
else:
    print("BCM2837.h: already patched")

# --- 2. pe_fiq.c ---------------------------------------------------------
s = read(PEFIQ)
if "G0245D_GICV3_G1" not in s:
    # 2a. DT block -> hardcoded msm8996 windows
    s = sub(
        s,
        """	if (!gicd_base) {
		// Find GIC DT node
		error = SecureDTLookupEntry(NULL, "/arm-io/gic", &entry);
		if (error != kSuccess) {
			panic("%s: cannot find GIC node in DT", __func__);
		}""",
        """	if (!gicd_base) {
#if defined(G0245D_GICV3_G1)
		/* g0245d v286: mainline msm8996.dtsi windows; the boot DT
		 * has no /arm-io/gic node, so hardcode (kebab fallback
		 * style). */
		gicd_base = ml_io_map(0x09BC0000, 0x10000);
		gicr_base = ml_io_map(0x09C00000, 0x100000);
		gicr_size = 0x100000;
		kprintf("G0245D GICv3: gicd@09bc0000 gicr@09c00000\\n");
	} else {
#endif
		// Find GIC DT node
		error = SecureDTLookupEntry(NULL, "/arm-io/gic", &entry);
		if (error != kSuccess) {
			panic("%s: cannot find GIC node in DT", __func__);
		}""",
        "pe_fiq: windows",
    )
    s = sub(
        s,
        """		gicr_size = gicr_size_prop;
	}

	// Find the redistributor for this processor""",
        """		gicr_size = gicr_size_prop;
#if defined(G0245D_GICV3_G1)
	}	/* g0245d v286: close the non-G0245D else */
#endif
	}

	// Find the redistributor for this processor""",
        "pe_fiq: close windows",
    )
    # 2b. skip WAKER on msm8996
    s = sub(
        s,
        """	// Mark this PE to be awake
	uint32_t gicr_waker = gicr_read32(GICR_WAKER);""",
        """#if !defined(G0245D_GICV3_G1)
	// Mark this PE to be awake
	uint32_t gicr_waker = gicr_read32(GICR_WAKER);""",
        "pe_fiq: waker open",
    )
    s = sub(
        s,
        """			    __func__, ml_get_cpu_number_local());
			}
		}
	}

	// Configure timers and legacy FIQ to be group 0
	gicr_write32(GICR_IGROUPR0, 0x81FFFFFF);

	// Enable PPI 27
	gicr_write32(GICR_ISENABLER0, (1 << 27));""",
        """			    __func__, ml_get_cpu_number_local());
			}
		}
	}
#endif	/* !G0245D_GICV3_G1: GICR_WAKER restricted on msm8996 */

#if defined(G0245D_GICV3_G1)
	/* g0245d v286: TrustZone owns Group 0; all our interrupts are
	 * Group 1 NS and arrive as IRQs (kebab). */
	gicr_write32(GICR_IGROUPR0, 0xFFFFFFFF);
	for (unsigned int g0245d_i = 0; g0245d_i < 32; g0245d_i += 4) {
		gicr_write32(GICR_IPRIORITYR0 + g0245d_i, 0xA0A0A0A0);
	}
	gicr_write32(GICR_ISENABLER0,
	    (1U << G0245D_VTIMER_INTID) | (1U << G0245D_IPI_SGI));
#else
	// Configure timers and legacy FIQ to be group 0
	gicr_write32(GICR_IGROUPR0, 0x81FFFFFF);

	// Enable PPI 27
	gicr_write32(GICR_ISENABLER0, (1 << 27));
#endif""",
        "pe_fiq: group config",
    )
    # 2c. ICC section
    s = sub(
        s,
        """	// Set priority masks and binary point for group 0
	__builtin_arm_wsr64("ICC_BPR0_EL1", 0);
	__builtin_arm_wsr64("ICC_PMR_EL1", 0xFF);""",
        """	// Set priority masks and binary point
#if defined(G0245D_GICV3_G1)
	__builtin_arm_wsr64("ICC_BPR1_EL1", 0);
#else
	__builtin_arm_wsr64("ICC_BPR0_EL1", 0);
#endif
	__builtin_arm_wsr64("ICC_PMR_EL1", 0xFF);""",
        "pe_fiq: bpr",
    )
    s = sub(
        s,
        """	// Enable the forwarding of the vtimer interrupt
	uint32_t gicd_ctlr = gicd_read32(GICD_CTLR);
	gicd_ctlr |= GICD_CTLR_ENABLEGRP0;
	gicd_write32(GICD_CTLR, gicd_ctlr);
	__builtin_arm_wsr64("ICC_IGRPEN0_EL1", 1);
	__builtin_arm_isb(ISB_SY);
}""",
        """#if defined(G0245D_GICV3_G1)
	/* g0245d v286: enable Group 1 (ARE_NS is fixed on GICv3; set the
	 * bits kebab sets) and stash readbacks for the freeze dump. */
	uint32_t gicd_ctlr = gicd_read32(GICD_CTLR);
	gicd_ctlr |= GICD_CTLR_ARE_NS | GICD_CTLR_ENABLEGRP1A |
	    GICD_CTLR_ENABLEGRP1;
	gicd_write32(GICD_CTLR, gicd_ctlr);
	while (gicd_read32(GICD_CTLR) & GICD_CTLR_RWP) {
		;
	}
	__builtin_arm_wsr64("ICC_IGRPEN1_EL1", 1);
	__builtin_arm_isb(ISB_SY);
	{
		extern void g0245d_trace_u(const char *, unsigned int);
		g0245d_rb_gicd_ctlr = gicd_read32(GICD_CTLR);
		g0245d_rb_gicd_igrp0 = gicr_read32(GICR_IGROUPR0);
		g0245d_rb_gicc_ctlr =
		    (unsigned int)__builtin_arm_rsr64("ICC_CTLR_EL1");
		g0245d_trace_u("v286 gicd rb", g0245d_rb_gicd_ctlr);
	}
#else
	// Enable the forwarding of the vtimer interrupt
	uint32_t gicd_ctlr = gicd_read32(GICD_CTLR);
	gicd_ctlr |= GICD_CTLR_ENABLEGRP0;
	gicd_write32(GICD_CTLR, gicd_ctlr);
	__builtin_arm_wsr64("ICC_IGRPEN0_EL1", 1);
	__builtin_arm_isb(ISB_SY);
#endif
}""",
        "pe_fiq: grp1 enable",
    )
    write(PEFIQ, s)
    print("pe_fiq.c: GICv3 G1 bring-up")
else:
    print("pe_fiq.c: already patched")

# --- 3. sleh.c -----------------------------------------------------------
s = read(SLEH)
if "ICC_IAR1_EL1" not in s:
    s = sub(
        s,
        """		/* g0245d v283: GIC-400 (GICv2) IRQ dispatch.  Timer and IPIs
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
		intid = iar & 0x3FFu;""",
        """		/* g0245d v286: msm8996 IS GICv3 -- sysreg dispatch (kebab).
		 * Timer and IPIs are Group 1 NS and arrive here as IRQs
		 * (TrustZone owns Group 0).  Virtual timer PPI = INTID 27. */
		uint64_t iar;
		unsigned int intid;
		unsigned int dbgtype = DBG_INTR_TYPE_OTHER;

		iar = __builtin_arm_rsr64("ICC_IAR1_EL1");
		intid = (unsigned int)(iar & 0xFFFFFFULL);""",
        "sleh: sysreg iar",
    )
    s = sub(
        s,
        """		} else if (intid < 16) {
			gicc[0x10 / 4] = iar;	/* EOI before handling */
			__builtin_arm_isb(0xF);	/* ISB SY */
			cpu_signal_handler();""",
        """		} else if (intid < 16) {
			__builtin_arm_wsr64("ICC_EOIR1_EL1", iar);
			__builtin_arm_isb(0xF);	/* ISB SY */
			cpu_signal_handler();""",
        "sleh: eoi ipi",
    )
    s = sub(
        s,
        """			    intid);
			}
			gicc[0x10 / 4] = iar;	/* EOI */
		}""",
        """			    intid);
			}
			__builtin_arm_wsr64("ICC_EOIR1_EL1", iar);
		}""",
        "sleh: eoi other",
    )
    write(SLEH, s)
    print("sleh.c: sysreg dispatch")
else:
    print("sleh.c: already patched")

# --- 4. IOKitBSDInit.cpp -------------------------------------------------
s = read(BSDINIT)
if "v286 iar" not in s:
    s = sub(
        s,
        """	{
		volatile unsigned int *g0245d_vgicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		unsigned int g0245d_iar = g0245d_vgicc[0x0C / 4];
		g0245d_vgicc[0x10 / 4] = g0245d_iar;	/* EOI right back */
		g0245d_trace_u("v285 iar", g0245d_iar & 0x3FFu);
	}""",
        """	{
		/* g0245d v286: sysreg poll -- 27 = vtimer pending (delivery
		 * OK, CPU mask issue); 1023 = nothing pending. */
		uint64_t g0245d_iar = __builtin_arm_rsr64("ICC_IAR1_EL1");
		unsigned int g0245d_intid =
		    (unsigned int)(g0245d_iar & 0xFFFFFFULL);
		if (g0245d_intid < 1020) {
			__builtin_arm_wsr64("ICC_EOIR1_EL1", g0245d_iar);
		}
		g0245d_trace_u("v286 iar", g0245d_intid);
	}""",
        "fbr: sysreg poll",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: sysreg iar poll")
else:
    print("IOKitBSDInit.cpp: already patched")

# --- 5. IOPlatformExpert.cpp: dump #2 after cfg done ---------------------
s = read(PLAT)
if "v286 cntv" not in s:
    s = sub(
        s,
        """extern "C" void g0245d_trace_u(const char *label, unsigned int value);""",
        """extern "C" void g0245d_trace_u(const char *label, unsigned int value);
extern "C" unsigned int g0245d_rb_gicd_ctlr;
extern "C" unsigned int g0245d_rb_gicd_igrp0;""",
        "plat: externs",
    )
    s = sub(
        s,
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 cfg done"); }""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 cfg done"); }
	/* g0245d v286: dump #2 -- last rows of the ring, always visible
	 * in a photo (boot freezes right after this in IOFindBSDRoot). */
	g0245d_trace_u("v286 cntv",
	    (unsigned int)__builtin_arm_rsr64("CNTV_CTL_EL0"));
	g0245d_trace_u("v286 gicd", g0245d_rb_gicd_ctlr);
	g0245d_trace_u("v286 igrp", g0245d_rb_gicd_igrp0);
	g0245d_trace_u("v286 igrp1",
	    (unsigned int)__builtin_arm_rsr64("ICC_IGRPEN1_EL1"));
	g0245d_trace_u("v286 pmr",
	    (unsigned int)__builtin_arm_rsr64("ICC_PMR_EL1"));
	g0245d_trace_u("v286 daif", __builtin_arm_rsr("DAIF"));""",
        "plat: dump2",
    )
    write(PLAT, s)
    print("IOPlatformExpert.cpp: dump #2")
else:
    print("IOPlatformExpert.cpp: already patched")

print("v286 done")
