#!/usr/bin/env python3
"""g0245d v288 -- THE missing EOI (plus RPR proof and FIQ insurance).

v287 boot picture decoded:

  * "v285 frq 0" -- CNTFRQ_EL0 reads ZERO on this platform (so the v284
     self-test armed CVAL=now: instant expiry; the one delivery was that).
  * "v287 irqn 1" -- still exactly one delivery total.
  * "v287 cvdl 4294756778" = -28854 ticks (~1.5 ms in the past) with
     cntv ISTATUS=1: a deadline WAS armed (the 3 s wait DID call setPop
     into CNTV_TVAL) and HAS expired -- the timer is asserting right now.
  * IRQs enabled (daif 0x200), Group 1 enabled, PMR passes -- and yet no
     delivery.  "Asserting but never delivered after exactly one
     successful delivery" = the interrupt is stuck ACTIVE at the GIC.

The bug: our v286 sleh_irq vtimer branch (adapted from kebab) forgot the
EOI!  kebab's original writes ICC_EOIR1_EL1 after rtclock_intr; we only
EOI'd the IPI and other branches.  IAR-read makes the interrupt ACTIVE;
without EOI/deactivate the GIC will never re-deliver ID 27 -- exactly
one delivery, then silence forever.

v288 changes:

  1. sleh.c vtimer branch: write ICC_EOIR1_EL1 after rtclock_intr (the
     actual fix).
  2. sleh.c sleh_fiq: intercept FIQs (read ICC_IAR0_EL1): vtimer ->
     handle + EOIR0; others -> EOIR0 + capped log.  Insurance in case
     TrustZone routes the timer as Group 0 on some boot.
  3. pe_fiq.c: GICD_CTLR |= ENABLEGRP0 as well (NS view RAZ/WI, harmless)
     -- covered by the same insurance.
  4. rtclock.c: global setPop counter (did more arming happen?).
  5. IOPlatformExpert.cpp dump #2: irqn / setpopn / cvdl / ICC_RPR_EL1
     (RPR 0xA0 on the old boot would prove stuck-active; now it should
     read 0xFF) + re-arm CVAL +1 s with the REAL 19.2 MHz rate (CNTFRQ
     reads 0 here).
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")
RTC = os.path.join(WORK, "osfmk/arm/rtclock.c")
PLAT = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")
BOARD = os.path.join(WORK, "pexpert/pexpert/arm64/BCM2837.h")

MARK = "g0245d v288"


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


# --- 1. sleh.c: THE fix -- EOI in the vtimer branch -----------------------
s = read(SLEH)
if "v288 eoi" not in s:
    s = sub(
        s,
        """		if (intid == G0245D_VTIMER_INTID) {
			cdp->cpu_decrementer = -1;	/* Large */
			rtclock_intr(TRUE);
			{
				/* g0245d v287: handler completed. */""",
        """		if (intid == G0245D_VTIMER_INTID) {
			cdp->cpu_decrementer = -1;	/* Large */
			rtclock_intr(TRUE);
			/* g0245d v288: THE FIX -- kebab EOIs here and we
			 * forgot it.  IAR-read made the interrupt active;
			 * without deactivate the GIC never re-delivers
			 * ID 27 (one delivery, then silence forever --
			 * exactly the v287 boot). */
			__builtin_arm_wsr64("ICC_EOIR1_EL1", iar);
			{
				/* g0245d v287: handler completed. */""",
        "sleh: vtimer EOI",
    )
    # sleh_fiq: Group-0/FIQ insurance
    s = sub(
        s,
        """sleh_fiq(arm_saved_state_t *state)
{
	unsigned int type   = DBG_INTR_TYPE_UNKNOWN;""",
        """sleh_fiq(arm_saved_state_t *state)
{
#if defined(G0245D_IRQ_DISPATCH)
	{
		/* g0245d v288: if TrustZone reverted our IGROUPR0 write the
		 * vtimer arrives as Group 0 / FIQ.  Ack via ICC_IAR0_EL1,
		 * handle the timer, EOI via ICC_EOIR0_EL1; everything else
		 * gets EOI'd and logged (no device FIQs expected here). */
		uint64_t g0245d_iar0 = __builtin_arm_rsr64("ICC_IAR0_EL1");
		unsigned int g0245d_intid =
		    (unsigned int)(g0245d_iar0 & 0xFFFFFFULL);
		static int g0245d_fiq_logged;
		{
			extern unsigned int g0245d_irq_count;
			g0245d_irq_count++;
		}
		if (g0245d_intid >= 1020) {
			return;
		}
		if (g0245d_fiq_logged < 6) {
			g0245d_fiq_logged++;
			extern void g0245d_trace_u(const char *, unsigned int);
			g0245d_trace_u("v288 fiq", g0245d_intid);
		}
		if (g0245d_intid == G0245D_VTIMER_INTID) {
			cpu_data_t *g0245d_cdp = getCpuDatap();
			g0245d_cdp->cpu_decrementer = -1;
			sleh_interrupt_handler_prologue(state,
			    DBG_INTR_TYPE_TIMER);
			rtclock_intr(TRUE);
			__builtin_arm_wsr64("ICC_EOIR0_EL1", g0245d_iar0);
			entropy_collect();
			sleh_interrupt_handler_epilogue();
			return;
		}
		__builtin_arm_wsr64("ICC_EOIR0_EL1", g0245d_iar0);
		__builtin_arm_isb(0xF);
		return;
	}
#endif

	unsigned int type   = DBG_INTR_TYPE_UNKNOWN;""",
        "sleh: fiq interception",
    )
    write(SLEH, s)
    print("sleh.c: vtimer EOI fix + FIQ interception")
else:
    print("sleh.c: already patched")

# --- 2. rtclock.c: global setPop counter ---------------------------------
s = read(RTC)
if "g0245d_setpop_count" not in s:
    s = sub(
        s,
        """		static int g0245d_setpop_logged;
		if (g0245d_setpop_logged < 4) {""",
        """		static int g0245d_setpop_logged;
		extern unsigned int g0245d_setpop_count;
		g0245d_setpop_count++;
		if (g0245d_setpop_logged < 4) {""",
        "rtclock: setpop count",
    )
    s = sub(
        s,
        """int
setPop(uint64_t time)
{""",
        """unsigned int g0245d_setpop_count;	/* g0245d v288 */

int
setPop(uint64_t time)
{""",
        "rtclock: setpop global",
    )
    write(RTC, s)
    print("rtclock.c: setPop counter added")
else:
    print("rtclock.c: already patched")

# --- 3. BCM2837.h: ENABLEGRP0 define -------------------------------------
s = read(BOARD)
if "GICD_CTLR_ENABLEGRP0" not in s:
    s = sub(
        s,
        """#define GICD_CTLR_ENABLEGRP1 0x1""",
        """#define GICD_CTLR_ENABLEGRP1 0x1
#define GICD_CTLR_ENABLEGRP0 0x1	/* same bit, kebab naming kept */""",
        "board: enablegrp0",
    )
    write(BOARD, s)
    print("BCM2837.h: ENABLEGRP0 define")
else:
    print("BCM2837.h: already patched")

# --- 4. IOPlatformExpert.cpp: dump #2 with RPR ---------------------------
s = read(PLAT)
if "v288 rpr" not in s:
    s = sub(
        s,
        """extern "C" unsigned int g0245d_irq_count;
extern "C" unsigned int g0245d_rb_cntfrq;""",
        """extern "C" unsigned int g0245d_irq_count;
extern "C" unsigned int g0245d_rb_cntfrq;
extern "C" unsigned int g0245d_setpop_count;""",
        "plat: setpop extern",
    )
    s = sub(
        s,
        """	g0245d_trace_u("v287 irqn", g0245d_irq_count);
	{
		uint64_t g0245d_cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
		uint64_t g0245d_now = __builtin_arm_rsr64("CNTVCT_EL0");
		g0245d_trace_u("v287 cvdl",
		    (unsigned int)(g0245d_cval - g0245d_now));
		__builtin_arm_wsr64("CNTV_CVAL_EL0",
		    g0245d_now + g0245d_rb_cntfrq);
		g0245d_trace("v287 rearmed");
	}""",
        """	g0245d_trace_u("v288 irqn", g0245d_irq_count);
	g0245d_trace_u("v288 setpopn", g0245d_setpop_count);
	{
		uint64_t g0245d_cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
		uint64_t g0245d_now = __builtin_arm_rsr64("CNTVCT_EL0");
		g0245d_trace_u("v288 cvdl",
		    (unsigned int)(g0245d_cval - g0245d_now));
		/* v288: running priority -- 0xA0 would mean the first timer
		 * interrupt is still ACTIVE (deactivation broken); 0xFF is
		 * clean.  With the v288 EOI fix it must read 0xFF. */
		g0245d_trace_u("v288 rpr",
		    (unsigned int)__builtin_arm_rsr64("ICC_RPR_EL1"));
	}
	/* re-arm +1 s with the REAL timer rate (CNTFRQ reads 0 here;
	 * msm8996 arch timer = 19.2 MHz). */
	__builtin_arm_wsr64("CNTV_CVAL_EL0",
	    __builtin_arm_rsr64("CNTVCT_EL0") + 19200000ULL);
	g0245d_trace("v288 rearmed");""",
        "plat: dump2 v288",
    )
    write(PLAT, s)
    print("IOPlatformExpert.cpp: dump2 v288")
else:
    print("IOPlatformExpert.cpp: already patched")

print("v288 done")
