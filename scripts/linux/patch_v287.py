#!/usr/bin/env python3
"""g0245d v287 -- does the deadline machinery arm, and do re-arms deliver?

v286 boot picture decoded (HUGE progress):

  * "v285 irqn 1" -- ONE interrupt DELIVERED.  The GICv3 sysreg path
     works end to end: ICC_IAR1_EL1 read, Group 1 NS, sleh_irq dispatch,
     ICC_EOIR1_EL1.  v286 iar 1023 (nothing pending at dump time).
  * "v286 cntv 5" = ENABLE | ISTATUS: the virtual timer is enabled AND
     asserting (CVAL in the past) at dump time.
  * "v286 gicd 18" = 0x12 = ARE_NS | EnableGrp1 (EnableGrp1A bit reads
     back clear -- fine).  "v286 igrp1 1" -- Group 1 enabled.
     "v286 pmr 248" = 0xF8 (lower bits RAZ, priorities pass).
     "v286 igrp 0" -- IGROUPR0 read-back zero, but kebab warned real
     hardware can read back zero while delivery works (and delivery
     provably worked once).
  * Boot still freezes in the 3 s IOBSD wait -- so the remaining break is
     between "wait with timeout" and "deadline armed on CNTV", or between
     "deadline fired" and "waiter woken".

v287 probes exactly those two hops:

  1. rtclock.c setPop(): log the first 4 arming calls with their
     decrementer values ("v287 setpop <delay>").  If the 3 s wait arms a
     deadline we will see setpop ~freq*3 (19.2 MHz * 3 = 0x22EC000 or
     so).  If setPop never runs, the wait machinery never arms.
  2. sleh.c: one-shot "v287 rtci" after rtclock_intr(TRUE) returns --
     proves the full handler ran without dying.
  3. IOPlatformExpert.cpp dump #2 additions: irqn again, CNTV_CVAL -
     CNTVCT (armed deadline delta, low 32 bits), then re-arm CVAL to
     +1 s and trace "v287 rearmed" -- if delivery works for re-arms, the
     next photo shows irqn growing and the wait machinery is the only
     suspect left.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

RTC = os.path.join(WORK, "osfmk/arm/rtclock.c")
SLEH = os.path.join(WORK, "osfmk/arm64/sleh.c")
PLAT = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")

MARK = "g0245d v287"


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


# --- 1. rtclock.c: log setPop arming -------------------------------------
s = read(RTC)
if "v287 setpop" not in s:
    s = sub(
        s,
        """	delay_time = deadline_to_decrementer(time, current_time);
	cdp->rtcPop = delay_time + current_time;

	ml_set_decrementer((uint32_t) delay_time);

	return delay_time;
}""",
        """	delay_time = deadline_to_decrementer(time, current_time);
	cdp->rtcPop = delay_time + current_time;

	{
		/* g0245d v287: log the first arming calls.  A timed wait
		 * arms ~3 s => delay_time ~= 3 * CNTFRQ (0x22EC000 at
		 * 19.2 MHz).  If setPop never runs, the wait machinery
		 * never arms a deadline. */
		static int g0245d_setpop_logged;
		if (g0245d_setpop_logged < 4) {
			g0245d_setpop_logged++;
			extern void g0245d_trace_u(const char *, unsigned int);
			g0245d_trace_u("v287 setpop", (unsigned int)delay_time);
		}
	}

	ml_set_decrementer((uint32_t) delay_time);

	return delay_time;
}""",
        "rtclock: setpop logging",
    )
    write(RTC, s)
    print("rtclock.c: setPop logging added")
else:
    print("rtclock.c: already patched")

# --- 2. sleh.c: one-shot marker after rtclock_intr -----------------------
s = read(SLEH)
if "v287 rtci" not in s:
    s = sub(
        s,
        """		if (intid == G0245D_VTIMER_INTID) {
			cdp->cpu_decrementer = -1;	/* Large */
			rtclock_intr(TRUE);
		} else if (intid < 16) {""",
        """		if (intid == G0245D_VTIMER_INTID) {
			cdp->cpu_decrementer = -1;	/* Large */
			rtclock_intr(TRUE);
			{
				/* g0245d v287: handler completed. */
				static int g0245d_rtci_shown;
				if (!g0245d_rtci_shown) {
					g0245d_rtci_shown = 1;
					extern void g0245d_trace(const char *);
					g0245d_trace("v287 rtci");
				}
			}
		} else if (intid < 16) {""",
        "sleh: rtci marker",
    )
    write(SLEH, s)
    print("sleh.c: rtci marker added")
else:
    print("sleh.c: already patched")

# --- 3. IOPlatformExpert.cpp: dump #2 additions --------------------------
s = read(PLAT)
if "v287 rearmed" not in s:
    s = sub(
        s,
        """extern "C" unsigned int g0245d_rb_gicd_ctlr;
extern "C" unsigned int g0245d_rb_gicd_igrp0;""",
        """extern "C" unsigned int g0245d_rb_gicd_ctlr;
extern "C" unsigned int g0245d_rb_gicd_igrp0;
extern "C" unsigned int g0245d_irq_count;""",
        "plat: irqn extern",
    )
    s = sub(
        s,
        """	g0245d_trace_u("v286 daif", __builtin_arm_rsr("DAIF"));""",
        """	g0245d_trace_u("v286 daif", __builtin_arm_rsr("DAIF"));
	/* g0245d v287: did more interrupts fire since prewait?  What is
	 * the armed deadline?  Then re-arm +1 s ourselves -- if delivery
	 * works for re-arms, irqn grows and the wait machinery is the
	 * only suspect left. */
	g0245d_trace_u("v287 irqn", g0245d_irq_count);
	{
		uint64_t g0245d_cval = __builtin_arm_rsr64("CNTV_CVAL_EL0");
		uint64_t g0245d_now = __builtin_arm_rsr64("CNTVCT_EL0");
		g0245d_trace_u("v287 cvdl",
		    (unsigned int)(g0245d_cval - g0245d_now));
		__builtin_arm_wsr64("CNTV_CVAL_EL0",
		    g0245d_now + g0245d_rb_cntfrq);
		g0245d_trace("v287 rearmed");
	}""",
        "plat: dump2 additions",
    )
    write(PLAT, s)
    print("IOPlatformExpert.cpp: dump2 additions")
else:
    print("IOPlatformExpert.cpp: already patched")

print("v287 done")
