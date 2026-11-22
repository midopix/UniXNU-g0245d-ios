#!/usr/bin/env python3
"""g0245d v258 -- declare max_cpus known at lockdown, so ml_wait_max_cpus() returns.

v257's photo shows the chain surviving everything that used to stop it:

    8161 v256 hi alloc ret 0x0
    8162 v257 hi alloc failed        <- static fallback carried namei
    8163/8165 v250 fs done
    8164 v250 fs routefs
    8166 v250 vfs done               <- vfsinit finished
    8167..8172 apfs/graphics/iogpu probes all done
    8173 bsd calling proc_uuid_policy_init()
    8174..8177 hi elements 64 / size 64 / alloc ret 0xfffffff2720f9000

proc_uuid_policy_init() is three statements and its hashinit succeeded, so the
stop is after it.  In bsd_init.c the next thing is

    #if SOCKETS
            mcache_init();                  /* no bsd_init_kprintf! */
            bsd_init_kprintf("calling mbinit\\n");
            mbinit();

and mcache_init() begins with ncpu = ml_wait_max_cpus().  That function is:

    assert(lockdown_done);
    lck_mtx_lock(&max_cpus_lock);
    while (max_cpus_initialized != MAX_CPUS_SET) {
            max_cpus_initialized = MAX_CPUS_WAIT;
            lck_mtx_sleep(..., THREAD_UNINT);
    }

It sleeps until something calls ml_set_max_cpus().  On a real platform the SMP
bring-up does that after the last CPU comes online; this bring-up has only the
boot CPU and no bring-up path at all, so nobody ever calls it -- the same root
cause as kperf_init_early() in v249, which was only skipped, not fixed.

v258 fixes it once: machine_lockdown() already sets lockdown_done, so right
there we declare the CPU count known.  Every later ml_wait_max_cpus() returns
immediately.  mcache_init() is also bracketed so the next photo shows whether
it completes.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MR = os.path.join(WORK, "osfmk/arm64/machine_routines.c")
BSD = os.path.join(WORK, "bsd/kern/bsd_init.c")

MARK = "g0245d v258"


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


# ------------------------------------------------------ machine_routines.c
s = read(MR)
if MARK not in s:
    s = sub(
        s,
        """/* g0245d v246: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);""",
        """/* g0245d v246/v258: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);""",
        "machine_routines: extern trace_u",
    )
    s = sub(
        s,
        """	lockdown_done = 1;
	g0245d_trace("v246 ml done");""",
        """	lockdown_done = 1;
	g0245d_trace("v246 ml done");
	/* g0245d v258: nothing on this bring-up ever calls ml_set_max_cpus(),
	 * because there is no SMP bring-up path -- only the boot CPU exists.
	 * ml_wait_max_cpus() therefore slept forever (mcache_init() hit it).
	 * Lockdown is the point where the platform's CPU count is final on a
	 * real machine, so declare it known here.
	 */
	ml_set_max_cpus(machine_info.max_cpus);
	g0245d_trace_u("v258 maxcpus", machine_info.max_cpus);""",
        "machine_routines: set max cpus",
    )
    write(MR, s)
    print("machine_routines: v258 changes applied")
else:
    print("machine_routines: already patched")

# ------------------------------------------------------------- bsd_init.c
s = read(BSD)
if MARK not in s:
    s = sub(
        s,
        """	/* Initialize per-CPU cache allocator */
	mcache_init();""",
        """	/* Initialize per-CPU cache allocator */
	g0245d_trace("v258 mcache enter");
	mcache_init();
	g0245d_trace("v258 mcache done");""",
        "bsd_init: mcache bracket",
    )
    write(BSD, s)
    print("bsd_init: v258 changes applied")
else:
    print("bsd_init: already patched")

print("v258 patch applied")
