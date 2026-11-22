#!/usr/bin/env python3
"""g0245d v273 -- perm pool: grab pages early from the VM, drop the BSS pool.

v272's boot regressed: the ring rendered garbage below its line-0 trace
("8282 v257 hi alloc failed" crisp, traces 8283-8311 = colored mush) and the
boot stalled inside a hashinit kalloc_type(Z_NOWAIT).  Root cause hypothesis
(backed by HANDOFF addresses): the kernel image physically overlaps the
framebuffer region.  FB phys base = 0x83401000, ~24.9 MB; the kernel image
(~34.5 MB of mapped segments) sits just below it.  v272 appended an 8 MB
__bss array, which pushed the image tail into the FB's physical pages: once
pool usage crossed the boundary, every console glyph write after trace 8282
was overwritten by bump-pool traffic -- and worse, the pool may have stomped
other loader data, ending in the stall at seq 8311.

v273 keeps the systemic routing (all zalloc_permanent <= 2 MB go to the
bump allocator) but sources the pool from the VM instead of BSS:

  * g0245d_perm_pool_grab() runs right after vm_mem_bootstrap() in
    kernel_bootstrap: at that point every page of the 56 MB view is free,
    so an 8 MB kernel_memory_allocate(KMA_NOPAGEWAIT) cannot sleep and
    will not steal pages needed later,
  * the pool pointer replaces the BSS array, so the kernel image shrinks
    back to its v271 size and no longer touches the FB,
  * if the grab fails (KMA_NOPAGEWAIT returns instead of sleeping), the
    perm allocator falls back to the original zone path -- which history
    shows works fine until mbinit -- and a trace says so.

Also: g0245d_perm_alloc returns NULL when the pool is absent; callers
check and fall through to the zone path.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ZALLOC = os.path.join(WORK, "osfmk/kern/zalloc.c")
STARTUP = os.path.join(WORK, "osfmk/kern/startup.c")

MARK = "g0245d v273"


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
    # 1. BSS array -> dynamic pointer + grab routine.
    s = sub(
        s,
        """static char g0245d_perm_pool[G0245D_PERM_POOL_SIZE] __attribute__((aligned(4096)));
static vm_size_t g0245d_perm_used;
static vm_size_t g0245d_perm_wm;""",
        """static char    *g0245d_perm_pool;      /* v273: VM-grabbed, not BSS */
static vm_size_t g0245d_perm_pool_size;
static vm_size_t g0245d_perm_used;
static vm_size_t g0245d_perm_wm;

/* g0245d v273: called right after vm_mem_bootstrap(), when every page of
 * the 56 MB view is still free.  KMA_NOPAGEWAIT makes the allocation fail
 * (KERN_RESOURCE_SHORTAGE) instead of sleeping in VM_PAGE_WAIT, so this
 * can never hang.  The kernel image keeps its v271 size -- v272's 8 MB
 * BSS array overlapped the framebuffer's physical pages (FB base
 * 0x83401000 sits just past the image tail) and garbled the console.
 */
void
g0245d_perm_pool_grab(void)
{
	vm_offset_t addr = 0;
	kern_return_t kr;

	if (g0245d_perm_pool != NULL) {
		return;
	}
	kr = kernel_memory_allocate(kernel_map, &addr,
	    G0245D_PERM_POOL_SIZE, 0,
	    KMA_KOBJECT | KMA_ZERO | KMA_NOPAGEWAIT,
	    VM_KERN_MEMORY_OSFMK);
	if (kr != KERN_SUCCESS) {
		g0245d_trace_u("v273 perm pool grab FAIL", (unsigned int)kr);
		return;
	}
	g0245d_perm_pool = (char *)(uintptr_t)addr;
	g0245d_perm_pool_size = G0245D_PERM_POOL_SIZE;
	g0245d_trace("v273 perm pool grabbed");
}""",
        "zalloc: dynamic pool + grab",
    )

    # 2. bump allocator over the dynamic pool.
    s = sub(
        s,
        """	for (;;) {
		vm_size_t    used = g0245d_perm_used;
		vm_offset_t  base = (vm_offset_t)(uintptr_t)g0245d_perm_pool + used;
		vm_offset_t  addr = (base + mask) & ~(vm_offset_t)mask;
		vm_offset_t  end = addr + size;
		vm_size_t    next = end - (vm_offset_t)(uintptr_t)g0245d_perm_pool;

		if (end > (vm_offset_t)(uintptr_t)g0245d_perm_pool +
		    G0245D_PERM_POOL_SIZE) {""",
        """	if (g0245d_perm_pool == NULL) {
		return NULL;
	}
	for (;;) {
		vm_size_t    used = g0245d_perm_used;
		vm_offset_t  base = (vm_offset_t)(uintptr_t)g0245d_perm_pool + used;
		vm_offset_t  addr = (base + mask) & ~(vm_offset_t)mask;
		vm_offset_t  end = addr + size;
		vm_size_t    next = end - (vm_offset_t)(uintptr_t)g0245d_perm_pool;

		if (end > (vm_offset_t)(uintptr_t)g0245d_perm_pool +
		    g0245d_perm_pool_size) {""",
        "zalloc: bump over dynamic pool",
    )

    # 3. _zalloc_permanent: fall back to the original zone path when the
    #    pool is absent (early boot before vm_mem_bootstrap, or grab fail).
    s = sub(
        s,
        """	/* g0245d v272: static pool instead of the sleeping zone path. */
	(void)zone;
	return g0245d_perm_alloc(size, mask);
	struct zone_page_metadata *page_meta;""",
        """	/* g0245d v273: pool when grabbed, original zone path otherwise
	 * (the zone still has room before mbinit, per every earlier boot).
	 */
	if (g0245d_perm_pool != NULL) {
		return g0245d_perm_alloc(size, mask);
	}
	struct zone_page_metadata *page_meta;""",
        "zalloc: _zalloc_permanent conditional",
    )

    # 4. zalloc_permanent_tag: pool only when present.
    s = sub(
        s,
        """	if (size <= G0245D_PERM_MAX) {
		return g0245d_perm_alloc(size, mask);
	}
	if (size <= PAGE_SIZE) {""",
        """	if (size <= G0245D_PERM_MAX && g0245d_perm_pool != NULL) {
		void *p = g0245d_perm_alloc(size, mask);
		if (p != NULL) {
			return p;
		}
	}
	if (size <= PAGE_SIZE) {""",
        "zalloc: tag route conditional",
    )

    # 5. percpu: same fallback.
    s = sub(
        s,
        """zalloc_percpu_permanent(vm_size_t size, vm_offset_t mask)
{
	/* g0245d v272: static pool as well. */
	(void)mask;
	return (void *)__zpcpu_mangle(g0245d_perm_alloc(size, mask));
}""",
        """zalloc_percpu_permanent(vm_size_t size, vm_offset_t mask)
{
	/* g0245d v273: pool when grabbed, zone otherwise. */
	if (g0245d_perm_pool != NULL) {
		(void)mask;
		return (void *)__zpcpu_mangle(g0245d_perm_alloc(size, mask));
	}
	zone_t zone = &zone_array[ZONE_ID_PERCPU_PERMANENT];
	return (void *)__zpcpu_mangle(_zalloc_permanent(zone, size, mask));
}""",
        "zalloc: percpu conditional",
    )

    # 6. exhaustion: panic text updated.
    s = sub(
        s,
        """			g0245d_trace("v272 perm pool EXHAUSTED");
			panic("g0245d v272: permanent pool exhausted");""",
        """			g0245d_trace("v273 perm pool EXHAUSTED");
			panic("g0245d v273: permanent pool exhausted");""",
        "zalloc: exhaustion text",
    )

    write(ZALLOC, s)
    print("zalloc.c: v273 changes applied")
else:
    print("zalloc.c: already patched")

# --------------------------------------------------------------- startup.c
s = read(STARTUP)
if MARK not in s:
    s = sub(
        s,
        """	kernel_bootstrap_log("vm_mem_bootstrap");
	vm_mem_bootstrap();""",
        """	kernel_bootstrap_log("vm_mem_bootstrap");
	vm_mem_bootstrap();

	/* g0245d v273: every page of the VM view is free right here; wire
	 * the permanent pool before anything can exhaust the zone.  Safe:
	 * KMA_NOPAGEWAIT fails instead of sleeping.
	 */
	{
		extern void g0245d_perm_pool_grab(void);
		kernel_bootstrap_log("v273 perm pool grab");
		g0245d_perm_pool_grab();
	}""",
        "startup: grab hook",
    )
    write(STARTUP, s)
    print("startup.c: v273 changes applied")
else:
    print("startup.c: already patched")

print("v273 patch applied")
