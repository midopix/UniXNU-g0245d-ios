#!/usr/bin/env python3
"""g0245d v274 -- kill the diagnosis blind spots around the new stall.

v273 boot picture: trace seq stopped at 8313 (v272: 8311 -- exactly +2, the
two new pool traces), hb row label still "v256 hi alloc enter", and the
gap between seq and hb_count is 59 = the number of tracev() calls, which
are the only trace kind that neither updates the fixed-row label nor
bumps the heartbeat.  Two facts follow:

  * the last *labelled* trace of the boot is a hashinit's "hi alloc enter";
    the ~31 traces after it are all tracev()s,
  * a tracev burst can only come from prng_random's "every 1024 calls"
    early_random checkpoint, so roughly 30-31 K zone-element allocations
    ran after that hashinit before everything went quiet.

That means the hashinit wall itself is gone; the kernel died somewhere
inside a subsystem init that allocates tens of thousands of zone elements
(each one randomised via early_random) -- and because tracev is mute we
cannot see where.

v274 is a pure observability release, five changes:

  1. arm_init.c: g0245d_tracev() now updates the fixed-row label and bumps
     the heartbeat like every other trace -- no more mute windows.
  2. prng_random.c: the every-1024-calls checkpoint switches from tracev
     to trace_u, so a burst shows up in the label with its call count.
  3. kern_subr.c: hashinit logs the caller's return address (low 32 bits);
     the unstripped mach.development.bcm2837 resolves it offline.
  4. zalloc.c: all three VM_PAGE_WAIT() sites get a distinct label
     (zwait kma / zwait zba / zwait elem) -- if the stall is a Z_WAITOK
     sleep, the label will say which path.
  5. vm_resident.c: the vm_page_grab free-count==0 spin-then-wait loop
     traces "v274 grab wait" before sleeping.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM_INIT = os.path.join(WORK, "osfmk/arm/arm_init.c")
PRNG = os.path.join(WORK, "osfmk/prng/prng_random.c")
KERN_SUBR = os.path.join(WORK, "bsd/kern/kern_subr.c")
ZALLOC = os.path.join(WORK, "osfmk/kern/zalloc.c")
VM_RES = os.path.join(WORK, "osfmk/vm/vm_resident.c")

MARK = "g0245d v274"


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


# --------------------------------------------------------------- arm_init.c
s = read(ARM_INIT)
if MARK not in s:
    s = sub(
        s,
        """void
g0245d_tracev(const char *label, unsigned long long value)
{
	g0245d_con_printf("%u %s %p\\n", ++g0245d_trace_seq, label,
	    (void *)(uintptr_t)value);
	g0245d_con_sync();
}""",
        """void
g0245d_tracev(const char *label, unsigned long long value)
{
	/* g0245d v274: tracev used to be mute -- no label update, no
	 * heartbeat -- which hid the final ~31 traces of the v272/v273
	 * boots behind a stale "hi alloc enter" label.  Make it honest.
	 */
	g0245d_last_label = label;
	g0245d_con_printf("%u %s %p\\n", ++g0245d_trace_seq, label,
	    (void *)(uintptr_t)value);
	g0245d_con_sync();
	g0245d_hb();
}""",
        "arm_init: tracev goes loud",
    )
    write(ARM_INIT, s)
    print("arm_init.c: tracev fixed")
else:
    print("arm_init.c: already patched")

# ----------------------------------------------------------- prng_random.c
s = read(PRNG)
if MARK not in s:
    s = sub(
        s,
        """extern void g0245d_trace(const char *label);
extern void g0245d_tracev(const char *label, unsigned long long value);""",
        """extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);
extern void g0245d_tracev(const char *label, unsigned long long value);""",
        "prng: trace_u extern",
    )
    s = sub(
        s,
        """	if (g0245d_er_calls > 1 && (g0245d_er_calls & 0x3FF) == 0) {
		g0245d_tracev("v230 early_random calls", g0245d_er_calls);
	}""",
        """	if (g0245d_er_calls > 1 && (g0245d_er_calls & 0x3FF) == 0) {
		/* g0245d v274: labelled trace, so a burst of early_random
		 * calls shows in the fixed row with its live counter
		 * instead of hiding behind a stale label.
		 */
		g0245d_trace_u("v274 er calls", g0245d_er_calls);
	}""",
        "prng: periodic trace goes labelled",
    )
    write(PRNG, s)
    print("prng_random.c: periodic checkpoint labelled")
else:
    print("prng_random.c: already patched")

# -------------------------------------------------------------- kern_subr.c
s = read(KERN_SUBR)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v256 hi alloc enter");""",
        """	g0245d_trace("v256 hi alloc enter");
	/* g0245d v274: log the caller's return address; the unstripped
	 * build kernel resolves it to a subsystem name offline.
	 */
	g0245d_trace_u("v274 hi caller",
	    (unsigned int)(uintptr_t)__builtin_return_address(0));""",
        "kern_subr: hashinit caller RA",
    )
    write(KERN_SUBR, s)
    print("kern_subr.c: hashinit caller traced")
else:
    print("kern_subr.c: already patched")

# ----------------------------------------------------------------- zalloc.c
s = read(ZALLOC)
if MARK not in s:
    # Site 1: kernel_memory_allocate KMA path (outside the lock).
    s = sub(
        s,
        """			 * We can't pass KMA_NOPAGEWAIT under a global lock as it leads
			 * to bad system deadlocks, so if the allocation failed,
			 * we need to do the VM_PAGE_WAIT() outside of the lock.
			 */
			VM_PAGE_WAIT();""",
        """			 * We can't pass KMA_NOPAGEWAIT under a global lock as it leads
			 * to bad system deadlocks, so if the allocation failed,
			 * we need to do the VM_PAGE_WAIT() outside of the lock.
			 */
			g0245d_trace("v274 zwait kma");
			VM_PAGE_WAIT();""",
        "zalloc: zwait kma",
    )
    # Site 2: zba_populate path.
    s = sub(
        s,
        """		assert(kr == KERN_RESOURCE_SHORTAGE);
		zba_unlock();
		VM_PAGE_WAIT();
		zba_lock();""",
        """		assert(kr == KERN_RESOURCE_SHORTAGE);
		zba_unlock();
		g0245d_trace("v274 zwait zba");
		VM_PAGE_WAIT();
		zba_lock();""",
        "zalloc: zwait zba",
    )
    # Site 3: zone element wait path.
    s = sub(
        s,
        """				waited++;
				VM_PAGE_WAIT();
				continue;""",
        """				waited++;
				g0245d_trace("v274 zwait elem");
				VM_PAGE_WAIT();
				continue;""",
        "zalloc: zwait elem",
    )
    write(ZALLOC, s)
    print("zalloc.c: three wait sites labelled")
else:
    print("zalloc.c: already patched")

# ------------------------------------------------------------ vm_resident.c
s = read(VM_RES)
if MARK not in s:
    s = sub(
        s,
        """		while (vm_page_free_count == 0) {
			vm_free_page_unlock();""",
        """		while (vm_page_free_count == 0) {
			/* g0245d v274: make the free-count wait visible. */
			extern void g0245d_trace(const char *label);
			g0245d_trace("v274 grab wait");
			vm_free_page_unlock();""",
        "vm_resident: grab wait trace",
    )
    write(VM_RES, s)
    print("vm_resident.c: grab wait traced")
else:
    print("vm_resident.c: already patched")

print("v274 patch applied")
