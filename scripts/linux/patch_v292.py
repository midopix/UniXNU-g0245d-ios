#!/usr/bin/env python3
"""g0245d v292 -- replace the sleeping kernel_memory_allocate() in IOFindBSDRoot
with the already-grabbed v273 permanent pool (never sleeps, virgin pages zero).

Evidence (v291 photo, 2026-11-23 10:37): seq 8476/8478/8479 show
`v291 cfg exit` / `v291 wait done` / `v291 didram enter`, but NEITHER
`v289 memdisk` (success) NOR `v289 memdisk FAIL` (failure) appears.  Both
branches are probed, so the 8 KB kernel_memory_allocate() call itself never
returns -- the same "allocation sleeps internally" wall as v270/v279/v257.
KMA_NOPAGEWAIT did not save it.

v292 changes ONLY the allocator in that one block:
  - kernel_memory_allocate(kernel_map, ..., 0x2000, KMA_*|NOPAGEWAIT, ...)
    -> g0245d_perm_pool_alloc(0x2000)
  - g0245d_perm_pool_alloc is a facade over the v273 bump allocator
    (osfmk/kern/zalloc.c, added by patch_v279.py): 8 MB pool grabbed once at
    early boot, 16-byte aligned, virgin pages already zero, NEVER sleeps.
  - identical probe ladder preserved: v289 memdisk / v289 rd md0 / FAIL.
  - one new probe `v292 perm pool` printed right after the bump, so the next
    photo proves we took this path.

Idempotent.  Run AFTER patch_v291.py (anchors assume v291 source state):
    XNU_WORK=<xnu-work> python3 patch_v292.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")
MARK = "g0245d v292"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what, count=1):
    n = src.count(old)
    if n != count:
        sys.exit("%s: anchor found %d times (expected %d)" % (what, n, count))
    return src.replace(old, new)


s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """		{
			kern_return_t g0245d_kr;
			vm_offset_t g0245d_va = 0;
			g0245d_kr = kernel_memory_allocate(kernel_map,
			    &g0245d_va, 0x2000, 0,
			    (kma_flags_t)(KMA_KOBJECT | KMA_ZERO |
			    KMA_NOPAGEWAIT),
			    (vm_tag_t)VM_KERN_MEMORY_OSFMK);
			if (g0245d_kr == KERN_SUCCESS) {""",
        """		{
			/* g0245d v292: the 8 KB kernel_memory_allocate() above never
			 * returned in v291 (KMA_NOPAGEWAIT did not help).  Take the
			 * block from the v273 permanent pool instead: 8 MB grabbed
			 * once at early boot, virgin pages zero, no sleeping path. */
			extern void *g0245d_perm_pool_alloc(unsigned long size);
			vm_offset_t g0245d_va = 0;
			g0245d_va = (vm_offset_t)(uintptr_t)
			    g0245d_perm_pool_alloc(0x2000);
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v292 perm pool"); }
			if (g0245d_va != 0) {""",
        "v292: allocator swap",
    )
    s = sub(
        s,
        """				  g0245d_trace_u("v289 memdisk FAIL",
				      (unsigned int)g0245d_kr); }""",
        """				  g0245d_trace_u("v289 memdisk FAIL",
				      0xFFFFFFFFu); }""",
        "v292: FAIL probe value",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: v292 permanent-pool allocator installed")
else:
    print("IOKitBSDInit.cpp: already v292")

print("v292 done (allocator only; probe ladder unchanged)")
