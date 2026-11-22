#!/usr/bin/env python3
"""g0245d v279 -- fbt probetab from the permanent pool, plus a generic
page-wait marker.

v278 boot picture decoded:

  * pseu 7001..12001 = indices 7-12 entered (helper/lockstat/lockprof/sdt/
    systrace/fbt).  Heartbeat "hb 8414/8372 v278 fbt enter": the two
    garbled rows 8412/8413 are "v278 fbt cdev" and "v278 fbt bl" (seq math
    agrees), so cdevsw_add and fbt_blacklist_init both passed, and
    fbt_attach's enter probe was the LAST trace ever printed.
  * "v278 fbt zalloc" never appeared, and enter..zalloc bracket exactly one
    statement: kmem_zalloc(probetab, KM_SLEEP).  The stall is INSIDE that
    allocation -- no further diagnosis needed, fix it directly.
  * No existing probe fired on the way in (label never left "fbt enter"),
    so the sleep sits in an unprobed wait path (very likely VM_PAGE_WAIT
    from kernel_memory_allocate, same wall family as mbinit).

v279 changes:

  1. zalloc.c: public facade g0245d_perm_pool_alloc() over the v273 bump
     allocator (static g0245d_perm_alloc stays private).
  2. fbt.c: probetab comes from the permanent pool (virgin grabbed pages,
     zero-filled -- kmem_zalloc semantics, never sleeps).  NULL -> clean
     DDI_FAILURE instead of a silent NULL deref.
  3. vm_resident.c vm_page_wait(): one-shot "v279 vm wait free <count>"
     probe so ANY future page-wait sleep is visible on the heartbeat line
     with the free-page count (tells us instantly whether the machine is
     genuinely out of pages or stuck on a lock).
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ZALLOC = os.path.join(WORK, "osfmk/kern/zalloc.c")
FBT = os.path.join(WORK, "bsd/dev/dtrace/fbt.c")
VMRES = os.path.join(WORK, "osfmk/vm/vm_resident.c")

MARK = "g0245d v279"


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


# --- 1. zalloc.c: public pool facade -------------------------------------
s = read(ZALLOC)
if "g0245d_perm_pool_alloc" not in s:
    s = sub(
        s,
        """static void *
_zalloc_permanent(zone_t zone, vm_size_t size, vm_offset_t mask)""",
        """/* g0245d v279: public facade over the bump allocator for one-off early
 * allocations that must never sleep (fbt's probetab slept forever in
 * kmem_zalloc/KM_SLEEP).  Blocks come from virgin grabbed pages, so they
 * are zero-filled like kmem_zalloc. */
void *
g0245d_perm_pool_alloc(unsigned long size)
{
	return g0245d_perm_alloc((vm_size_t)size, 15);
}

static void *
_zalloc_permanent(zone_t zone, vm_size_t size, vm_offset_t mask)""",
        "zalloc: pool facade",
    )
    write(ZALLOC, s)
    print("zalloc.c: g0245d_perm_pool_alloc added")
else:
    print("zalloc.c: already patched")

# --- 2. fbt.c: probetab from the pool ------------------------------------
s = read(FBT)
if MARK not in s:
    s = sub(
        s,
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt enter"); }
	fbt_probetab =
	    kmem_zalloc(fbt_probetab_size * sizeof(fbt_probe_t *), KM_SLEEP);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt zalloc"); }""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt enter"); }
	/* g0245d v279: kmem_zalloc(KM_SLEEP) sleeps forever on this bring-up
	 * (v278 proved the stall is exactly this allocation).  Take the
	 * probe table from the v273 permanent pool instead: bump allocator
	 * over virgin grabbed pages -- zero-filled, never sleeps. */
	{
		extern void *g0245d_perm_pool_alloc(unsigned long size);
		fbt_probetab = (fbt_probe_t **)g0245d_perm_pool_alloc(
		    (unsigned long)fbt_probetab_size *
		    sizeof(fbt_probe_t *));
	}
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v279 fbt pool"); }
	if (fbt_probetab == NULL) {
		g0245d_trace("v279 fbt pool FAIL");
		return DDI_FAILURE;
	}""",
        "fbt: pool-backed probetab",
    )
    write(FBT, s)
    print("fbt.c: probetab now pool-backed")
else:
    print("fbt.c: already patched")

# --- 3. vm_resident.c: one-shot vm_page_wait marker ----------------------
s = read(VMRES)
if "v279 vm wait" not in s:
    s = sub(
        s,
        """vm_page_wait(
	int     interruptible )
{
	/*
	 *	We can't use vm_page_free_reserved to make this""",
        """vm_page_wait(
	int     interruptible )
{
	{	/* g0245d v279: one-shot marker for ANY page-wait sleep. */
		static int g0245d_vmwait_shown;
		if (!g0245d_vmwait_shown) {
			g0245d_vmwait_shown = 1;
			extern void g0245d_trace_u(const char *, unsigned int);
			g0245d_trace_u("v279 vm wait free",
			    (unsigned int)vm_page_free_count);
		}
	}

	/*
	 *	We can't use vm_page_free_reserved to make this""",
        "vm_resident: vm_page_wait marker",
    )
    write(VMRES, s)
    print("vm_resident.c: vm_page_wait one-shot marker added")
else:
    print("vm_resident.c: already patched")

print("v279 done")
