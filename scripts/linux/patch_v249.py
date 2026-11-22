#!/usr/bin/env python3
"""g0245d v249 -- skip kperf_init_early(), which waits for every CPU.

v248's photo is precise:

    8082 v245 PE lockdown done
    8083 v248 vm restrictions enter
    8084 v248 vm restrictions done
    8085 v248 kperf enter
    (nothing more)
    status: >PE_lockdown_iokit

So vm_set_restrictions() passed and the stop is inside kperf_init_early().
Its source is five lines:

    assert(ml_get_interrupts_enabled() == FALSE);
    ml_wait_max_cpus();                       /* waits until every possible CPU is accounted for */
    if (PE_parse_boot_arg_str("kperf", ...)) kperf_kernel_configure(...);

On this bring-up only the boot CPU exists while machine_info.max_cpus still
claims more, so ml_wait_max_cpus() never returns -- a classic deadlock with
no output, exactly the panel signature.

Note that kperf_init() is a different call: it runs from ktrace_startup(),
which is STARTUP(KTRACE, RANK_FIRST) and already completed among the 3917
startup routines.  It only calls kptimer_init() and was fine.  So skip just
this early hook, keep it verbatim under #if 0, and let bsd_init() run so the
47 stage breadcrumbs from v248 finally become visible.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

START = os.path.join(WORK, "osfmk/kern/startup.c")

MARK = "g0245d v249"


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


s = read(START)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v248 kperf enter");
	kperf_init_early();
	g0245d_trace("v248 kperf done");""",
        """	g0245d_trace("v248 kperf enter");
	/* g0245d v249: kperf_init_early() begins with ml_wait_max_cpus(),
	 * which waits until every advertised CPU is accounted for.  This
	 * bring-up only has the boot CPU while machine_info.max_cpus claims
	 * more, so it never returns.  kperf_init() is a separate call from
	 * ktrace_startup() (STARTUP(KTRACE)) and already completed fine.
	 * Skip only this early hook for bring-up.
	 */
	g0245d_trace("v249 kperf early skipped");
#if 0   /* g0245d v249: original kperf_init_early(); */
	kperf_init_early();
#endif
	g0245d_trace("v248 kperf done");""",
        "startup: skip kperf_init_early",
    )
    write(START, s)
    print("startup: v249 changes applied")
else:
    print("startup: already patched")

print("v249 patch applied")
