#!/usr/bin/env python3
"""g0245d v285 -- move GIC diagnostics to the freeze point + poll IAR.

v284 boot picture decoded (via seq arithmetic):

  * sha1 enter moved 8431 -> 8437, cfg done 8435 -> 8441: shift is EXACTLY
    +6 = v283's kprintf (1) + the four pe_init_fiq readback probes (4) +
    the DAIF probe (1).
  * Therefore: all four readback probes printed, and NOT A SINGLE
    "v284 irq" line exists -- the self-armed 250 ms CNTV timer never
    delivered.  Any delivered interrupt would have added its own seq
    entries (up to 8).
  * The actual VALUES (GICD/GICC readback, DAIF) scrolled off the top of
    the screen -- invisible in the photo.

v285 makes every number visible at the freeze point and adds one decisive
probe: read GICC_IAR directly (thread context, CPU mask irrelevant):

  * iar == 27  -> the GIC HAS the virtual timer pending; delivery works,
                  the problem is the CPU mask (DAIF) / unmasking.
  * iar ==1023 -> nothing pending at the GIC: the interrupt was never
                  asserted (TZ group routing / clock / ISENABLER blocked).

Changes:

  1. pe_fiq.c: stash readbacks + CNTFRQ into non-static globals.
  2. sleh.c: global irq counter g0245d_irq_count (uncapped).
  3. IOKitBSDInit.cpp prewait: print frq / cntv(CTL readback: bit0 enable,
     bit1 imask, bit2 ISTATUS) / gicd / igrp / gicc / irqn / daif / iar
     (one IAR read + immediate EOI).
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

PEFIQ = os.path.join(WORK, "pexpert/arm/pe_fiq.c")
SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")
BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")

MARK = "g0245d v285"


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


# --- 1. pe_fiq.c: globals for the readbacks ------------------------------
s = read(PEFIQ)
if "g0245d_rb_gicd_ctlr" not in s:
    s = sub(
        s,
        """	{
		extern void g0245d_trace_u(const char *, unsigned int);
		volatile unsigned int *gicd =
		    (volatile unsigned int *)g0245d_gicd_base;
		volatile unsigned int *gicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		g0245d_trace_u("v284 gicd ctlr", gicd[0x000 / 4]);
		g0245d_trace_u("v284 gicd igrp0", gicd[0x080 / 4]);
		g0245d_trace_u("v284 gicc ctlr", gicc[0x000 / 4]);
	}""",
        """	{
		extern void g0245d_trace_u(const char *, unsigned int);
		volatile unsigned int *gicd =
		    (volatile unsigned int *)g0245d_gicd_base;
		volatile unsigned int *gicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		g0245d_rb_gicd_ctlr = gicd[0x000 / 4];
		g0245d_rb_gicd_igrp0 = gicd[0x080 / 4];
		g0245d_rb_gicc_ctlr = gicc[0x000 / 4];
		g0245d_trace_u("v284 gicd ctlr", g0245d_rb_gicd_ctlr);
		g0245d_trace_u("v284 gicd igrp0", g0245d_rb_gicd_igrp0);
		g0245d_trace_u("v284 gicc ctlr", g0245d_rb_gicc_ctlr);
	}""",
        "pe_fiq: stash readbacks",
    )
    s = sub(
        s,
        """		g0245d_trace_u("v284 cval armed", (unsigned int)frq);""",
        """		g0245d_rb_cntfrq = (unsigned int)frq;
		g0245d_trace_u("v284 cval armed", g0245d_rb_cntfrq);""",
        "pe_fiq: stash cntfrq",
    )
    s = sub(
        s,
        """static vm_offset_t g0245d_gicd_base_unused_marker""",
        """static vm_offset_t g0245d_gicd_base_unused_marker""",
        "pe_fiq: never matches",
    ) if False else s
    s = sub(
        s,
        """/* g0245d v283: GIC-400 (GICv2, MMIO).  Per-PE state lives in the GICC
 * view (banked); shared state in GICD.  TrustZone owns Group 0 on this
 * platform, so all our interrupts are Group 1 NS and surface as IRQs
 * handled by sleh_irq(). */
vm_offset_t g0245d_gicd_base;
vm_offset_t g0245d_gicc_base;""",
        """/* g0245d v283: GIC-400 (GICv2, MMIO).  Per-PE state lives in the GICC
 * view (banked); shared state in GICD.  TrustZone owns Group 0 on this
 * platform, so all our interrupts are Group 1 NS and surface as IRQs
 * handled by sleh_irq(). */
vm_offset_t g0245d_gicd_base;
vm_offset_t g0245d_gicc_base;

/* g0245d v285: stashed diagnostics for the console-visible dump at the
 * freeze point (pe_init_fiq runs before the framebuffer console, so the
 * on-boot prints scroll away before any photo can catch them). */
unsigned int g0245d_rb_gicd_ctlr;
unsigned int g0245d_rb_gicd_igrp0;
unsigned int g0245d_rb_gicc_ctlr;
unsigned int g0245d_rb_cntfrq;""",
        "pe_fiq: globals",
    )
    write(PEFIQ, s)
    print("pe_fiq.c: diagnostics globals added")
else:
    print("pe_fiq.c: already patched")

# --- 2. sleh.c: uncapped irq counter -------------------------------------
s = read(SLEH)
if "g0245d_irq_count" not in s:
    s = sub(
        s,
        """		{
			/* g0245d v284: log the first 8 interrupts (capped so
			 * a storm cannot wash the ring out). */
			static int g0245d_irq_logged;
			if (g0245d_irq_logged < 8) {""",
        """		{
			/* g0245d v284: log the first 8 interrupts (capped so
			 * a storm cannot wash the ring out).  v285: uncapped
			 * global count for the freeze-point dump. */
			static int g0245d_irq_logged;
			extern unsigned int g0245d_irq_count;
			g0245d_irq_count++;
			if (g0245d_irq_logged < 8) {""",
        "sleh: uncapped counter",
    )
    s = sub(
        s,
        """#define G0245D_IRQ_DISPATCH 1	/* g0245d v283 */""",
        """#define G0245D_IRQ_DISPATCH 1	/* g0245d v283 */

unsigned int g0245d_irq_count;	/* g0245d v285: every IAR read */""",
        "sleh: counter global",
    )
    write(SLEH, s)
    print("sleh.c: irq counter added")
else:
    print("sleh.c: already patched")

# --- 3. IOKitBSDInit.cpp: the freeze-point dump ---------------------------
s = read(BSDINIT)
if "v285 iar" not in s:
    s = sub(
        s,
        """extern "C" void g0245d_trace_u(const char *label, unsigned int value);

kern_return_t

IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        """extern "C" void g0245d_trace_u(const char *label, unsigned int value);
extern "C" vm_offset_t g0245d_gicc_base;
extern "C" unsigned int g0245d_irq_count;
extern "C" unsigned int g0245d_rb_gicd_ctlr;
extern "C" unsigned int g0245d_rb_gicd_igrp0;
extern "C" unsigned int g0245d_rb_gicc_ctlr;
extern "C" unsigned int g0245d_rb_cntfrq;

kern_return_t

IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        "fbr: extern decls",
    )
    s = sub(
        s,
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v282 fbr prewait"); }
	g0245d_trace_u("v284 daif", __builtin_arm_rsr("DAIF"));""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v282 fbr prewait"); }
	/* g0245d v285: freeze-point dump -- every number a photo can catch.
	 * cntv: bit0 enable / bit1 imask / bit2 ISTATUS (timer asserted).
	 * daif: bit7(0x80) = IRQ mask.  iar: poll the GIC once -- 27 means
	 * the vtimer IS pending (CPU mask problem); 1023 means the GIC
	 * never asserted it (TZ routing / clock / ISENABLER problem). */
	g0245d_trace_u("v285 frq", g0245d_rb_cntfrq);
	g0245d_trace_u("v285 cntv",
	    (unsigned int)__builtin_arm_rsr64("CNTV_CTL_EL0"));
	g0245d_trace_u("v285 gicd", g0245d_rb_gicd_ctlr);
	g0245d_trace_u("v285 igrp", g0245d_rb_gicd_igrp0);
	g0245d_trace_u("v285 gicc", g0245d_rb_gicc_ctlr);
	g0245d_trace_u("v285 irqn", g0245d_irq_count);
	g0245d_trace_u("v285 daif", __builtin_arm_rsr("DAIF"));
	{
		volatile unsigned int *g0245d_vgicc =
		    (volatile unsigned int *)g0245d_gicc_base;
		unsigned int g0245d_iar = g0245d_vgicc[0x0C / 4];
		g0245d_vgicc[0x10 / 4] = g0245d_iar;	/* EOI right back */
		g0245d_trace_u("v285 iar", g0245d_iar & 0x3FFu);
	}""",
        "fbr: freeze-point dump",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: freeze-point dump added")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v285 done")
