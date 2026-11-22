#!/usr/bin/env python3
"""g0245d v272 -- systemic fix: back zalloc_permanent with a static pool.

v271's fixed row reads

    hb 8240/8184 v271 mcl chk

with trace_seq = 8240 while the last labelled trace is 8238 ("mcl chk").
trace_u() does not update g0245d_last_label, so 8239 = "v271 mcl npages 8"
and 8240 = "v271 mcl pg 0".  The stall is inside the m_clalloc() page loop
on i=0: slab_get() finds slabstbl[0] == NULL and calls

    zalloc_permanent_type(mcl_slabg_t)
    zalloc_permanent(sizeof(mcl_slab_t) * NSLABSPMB)      # 256 * 48 = 12 KB

That is the FOURTH wall of the same kind: zalloc_permanent() expands its
zone through zone_expand_locked(Z_WAITOK) -> vm_page_grab() ->
VM_PAGE_WAIT(), which sleeps forever on this bring-up (56 MB VM view, no
pageout daemon).  Previous walls: mleak tables (v267), mcl_paddr (v268),
freelist_populate's KMA_LOMEM (v270).

There are 30+ more zalloc_permanent() call sites on the boot path ahead
(tcp_cache, radix rn_zeros, sysctl, audit, execargs_cache, ...).  Bypassing
them one at a time is whack-a-mole, so v272 fixes the mechanism itself:

  * a 8 MB page-aligned static BSS pool backs every permanent allocation
    of <= 2 MB through a CAS-atomic bump allocator (safe for the runtime
    multithreaded callers such as sysctl_register_oid / dlil ifa alloc),
  * _zalloc_permanent() (the <= PAGE_SIZE zone path) and
    zalloc_permanent_tag() (<= 2 MB) both route into the pool,
  * larger sizes still take the old kernel_memory_allocate path,
  * usage is traced at pool start and at every 1 MB watermark.

Also fixes the diagnosis blind spot that caused this round's ambiguity:
g0245d_trace_u() and g0245d_trace_lit() now update g0245d_last_label, so
the fixed heartbeat row always shows the newest trace.

Risk: +8 MB of kernel BSS (demand-zero pages already part of the kernel
image mapping; the real DRAM is 4 GB, only the VM *view* is 56 MB).
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ZALLOC = os.path.join(WORK, "osfmk/kern/zalloc.c")
ARMINIT = os.path.join(WORK, "osfmk/arm/arm_init.c")

MARK = "g0245d v272"


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


# ---------------------------------------------------------------- zalloc.c
s = read(ZALLOC)
if MARK not in s:
    s = sub(
        s,
        """static void *
_zalloc_permanent(zone_t zone, vm_size_t size, vm_offset_t mask)
{
	struct zone_page_metadata *page_meta;""",
        """/*
 * g0245d v272: the permanent zone expands through zone_expand_locked
 * (Z_WAITOK) -> vm_page_grab() -> VM_PAGE_WAIT(), which sleeps forever on
 * this bring-up (56 MB VM view, no pageout daemon).  Back every permanent
 * allocation of <= 2 MB with a CAS-atomic bump allocator over static BSS
 * instead.  BSS pages are demand-zero and never reused (permanent memory
 * is never freed), so every returned block is zero-filled as required.
 */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);

#define G0245D_PERM_POOL_SIZE   (8u << 20)      /* 8 MB of static backing */
#define G0245D_PERM_MAX         (2u << 20)      /* route <= 2 MB to pool */

static char g0245d_perm_pool[G0245D_PERM_POOL_SIZE] __attribute__((aligned(4096)));
static vm_size_t g0245d_perm_used;
static vm_size_t g0245d_perm_wm;

static void *
g0245d_perm_alloc(vm_size_t size, vm_offset_t mask)
{
	for (;;) {
		vm_size_t    used = g0245d_perm_used;
		vm_offset_t  base = (vm_offset_t)(uintptr_t)g0245d_perm_pool + used;
		vm_offset_t  addr = (base + mask) & ~(vm_offset_t)mask;
		vm_offset_t  end = addr + size;
		vm_size_t    next = end - (vm_offset_t)(uintptr_t)g0245d_perm_pool;

		if (end > (vm_offset_t)(uintptr_t)g0245d_perm_pool +
		    G0245D_PERM_POOL_SIZE) {
			g0245d_trace("v272 perm pool EXHAUSTED");
			panic("g0245d v272: permanent pool exhausted");
		}

		if (__sync_bool_compare_and_swap(&g0245d_perm_used, used, next)) {
			if (used == 0) {
				g0245d_trace("v272 perm pool on");
			}
			if (next - g0245d_perm_wm >= (1u << 20)) {
				g0245d_perm_wm = next & ~((1u << 20) - 1);
				g0245d_trace_u("v272 perm used", (unsigned int)next);
			}
			return (void *)(uintptr_t)addr;
		}
	}
}

static void *
_zalloc_permanent(zone_t zone, vm_size_t size, vm_offset_t mask)
{
	/* g0245d v272: static pool instead of the sleeping zone path. */
	(void)zone;
	return g0245d_perm_alloc(size, mask);
	struct zone_page_metadata *page_meta;""",
        "zalloc: pool + _zalloc_permanent head",
    )

    s = sub(
        s,
        """void *
zalloc_permanent_tag(vm_size_t size, vm_offset_t mask, vm_tag_t tag)
{
	if (size <= PAGE_SIZE) {""",
        """void *
zalloc_permanent_tag(vm_size_t size, vm_offset_t mask, vm_tag_t tag)
{
	/* g0245d v272: route every allocation up to 2 MB into the static
	 * pool; only larger (rare) sizes keep the kernel_memory_allocate
	 * path.
	 */
	if (size <= G0245D_PERM_MAX) {
		return g0245d_perm_alloc(size, mask);
	}
	if (size <= PAGE_SIZE) {""",
        "zalloc: zalloc_permanent_tag route",
    )

    s = sub(
        s,
        """zalloc_percpu_permanent(vm_size_t size, vm_offset_t mask)
{
	zone_t zone = &zone_array[ZONE_ID_PERCPU_PERMANENT];
	return (void *)__zpcpu_mangle(_zalloc_permanent(zone, size, mask));
}""",
        """zalloc_percpu_permanent(vm_size_t size, vm_offset_t mask)
{
	/* g0245d v272: static pool as well. */
	(void)mask;
	return (void *)__zpcpu_mangle(g0245d_perm_alloc(size, mask));
}""",
        "zalloc: percpu permanent route",
    )

    write(ZALLOC, s)
    print("zalloc.c: v272 changes applied")
else:
    print("zalloc.c: already patched")

# --------------------------------------------------------------- arm_init.c
s = read(ARMINIT)
if MARK not in s:
    # trace_u: update last label so the fixed row shows the newest trace.
    s = sub(
        s,
        """void
g0245d_trace_u(const char *label, unsigned int value)
{
	g0245d_con_printf("%u %s %u\\n", ++g0245d_trace_seq, label, value);
	g0245d_con_sync();
	g0245d_hb();
}""",
        """void
g0245d_trace_u(const char *label, unsigned int value)
{
	g0245d_con_printf("%u %s %u\\n", ++g0245d_trace_seq, label, value);
	g0245d_con_sync();
	/* g0245d v272: keep the fixed row honest -- without this the row
	 * keeps showing an older label and misleads the photo reading.
	 */
	g0245d_last_label = label;
	g0245d_hb();
}""",
        "arm_init: trace_u label",
    )

    # trace_lit: same, but through a persistent buffer (its buf is local).
    s = sub(
        s,
        """	buf[i] = '\\0';
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, buf);
	g0245d_con_sync();
	g0245d_hb();
}""",
        """	buf[i] = '\\0';
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, buf);
	g0245d_con_sync();
	/* g0245d v272: publish the stage name to the fixed row too. */
	static char g0245d_lit_label[49];
	for (unsigned int j = 0; j <= i && j < 48; j++) {
		g0245d_lit_label[j] = buf[j];
	}
	g0245d_last_label = g0245d_lit_label;
	g0245d_hb();
}""",
        "arm_init: trace_lit label",
    )

    write(ARMINIT, s)
    print("arm_init.c: v272 changes applied")
else:
    print("arm_init.c: already patched")

print("v272 patch applied")
