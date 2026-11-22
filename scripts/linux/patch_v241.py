#!/usr/bin/env python3
"""g0245d v241 -- skip generatePlatformUUID, and trace every startup routine.

v240's photo walks the whole ConfigureIOKit ladder and then stops:

    176 v240 cfg enter
    177 v240 cfg rootnub ok
    178 v240 nvram enter
    179 v240 options frompath
    180 v240 options found        <- the runtime ADT does have /options
    181 v240 nvram new
    182 v240 nvram init enter
    183 v240 nvram init done
    184 v240 nvram attach done
    185 v240 nvram start done
    186 v240 nvram done
    187 v240 serial none
    188 v240 uuid enter
    189 (half-drawn, the photo's lighting kills it)

So createNVRAM() did real work -- an IODTNVRAM was built, initialised,
attached and started -- and serial-number is absent as predicted.  The stop is
inside generatePlatformUUID(), whose only interesting statement is
IORegistryEntry::fromPath("/chosen", gIODTPlane).  (Its disassembly shows a
direct bl, a 0xf0 frame and the "uuid chosen enter" trace immediately before
the call, so a missing follow-up means the call itself.)

Two ways to be wrong here: the uuid code really hangs, or the console died and
nothing after it can be seen.  Skipping the call separates them -- the next
trace ("v241 uuid skipped") either appears or it does not.

Because a pass through ConfigureIOKit would put us into the startup-routine
ladder (kernel_startup_initialize_upto(STARTUP_SUB_EARLY_BOOT), spllo() and
initialize_screen(), which may take the framebuffer away from us), v241 also
traces the function pointer of every startup routine and brackets spllo() and
initialize_screen().  Those addresses resolve offline with llvm-nm.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

PE = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")
START = os.path.join(WORK, "osfmk/kern/startup.c")

MARK = "g0245d v241"


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


# -------------------------------------------------------- IOPlatformExpert.cpp
s = read(PE)
if MARK not in s:
    s = sub(
        s,
        """/* g0245d v240: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern "C" void g0245d_trace(const char *label);""",
        """/* g0245d v240: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern "C" void g0245d_trace(const char *label);
extern "C" void g0245d_probe(const char *label);""",
        "IOPlatformExpert: extern g0245d_probe",
    )

    s = sub(
        s,
        """	g0245d_trace("v240 uuid enter");
	generatePlatformUUID();
	g0245d_trace("v240 uuid done");""",
        """	g0245d_trace("v240 uuid enter");
	/* g0245d v241: generatePlatformUUID() is SKIPPED.  v240 stops inside it,
	 * at or inside IORegistryEntry::fromPath("/chosen") -- the single
	 * interesting statement in the function.  Skipping it answers one
	 * question with one photo: does the trace after it appear at all?  If
	 * it does, the uuid code is the stop and can be bisected; if it does
	 * not, the console (not the uuid code) is what died.
	 */
	g0245d_probe("v241 nouuid");
	g0245d_trace("v241 uuid skipped");
	g0245d_trace("v240 uuid done");""",
        "IOPlatformExpert: skip generatePlatformUUID",
    )

    write(PE, s)
    print("IOPlatformExpert: v241 changes applied")
else:
    print("IOPlatformExpert: already patched")

# ---------------------------------------------------------------- startup.c
s = read(START)
if MARK not in s:
    # 1. every startup routine, by function pointer.
    s = sub(
        s,
        """		startup_phase = cur->subsystem - 1;
		kernel_startup_log(cur->subsystem);
		cur->func(cur->arg);""",
        """		startup_phase = cur->subsystem - 1;
		kernel_startup_log(cur->subsystem);
		/* g0245d v241: name the routine before running it.  kernel_bootstrap_log
		 * only names the subsystem, and a subsystem can hold dozens of routines.
		 * The value is the function pointer, resolved offline with llvm-nm.
		 */
		g0245d_tracev("v241 startup fn", (unsigned long long)cur->func);
		cur->func(cur->arg);""",
        "startup: per-routine trace",
    )

    # 2. the interrupt enable and the screen grab, which can both end the run.
    s = sub(
        s,
        """	assert(ml_get_interrupts_enabled() == FALSE);""",
        """	assert(ml_get_interrupts_enabled() == FALSE);
	g0245d_trace("v241 irq assert ok");""",
        "startup: irq assert",
    )
    s = sub(
        s,
        """	(void) spllo();         /* Allow interruptions */""",
        """	g0245d_trace("v241 spllo enter");
	(void) spllo();         /* Allow interruptions */
	g0245d_trace("v241 spllo done");""",
        "startup: spllo",
    )
    s = sub(
        s,
        """	initialize_screen(NULL, kPEAcquireScreen);""",
        """	g0245d_trace("v241 screen init enter");
	initialize_screen(NULL, kPEAcquireScreen);
	g0245d_trace("v241 screen init done");""",
        "startup: initialize_screen",
    )

    write(START, s)
    print("startup: v241 changes applied")
else:
    print("startup: already patched")

print("v241 patch applied")
