#!/usr/bin/env python3
"""g0245d v270 -- drop KMA_LOMEM from mbuf page allocations.

v269's ring reads

    hb 8226 v266 mbi mcl_pages 512        <- cap worked
    hb 8227 v266 mbi paddr enter
    hb 8228 v268 mbi paddr static         <- back inside the static table
    hb 8229 v266 mbi paddr done
    hb 8230 v266 mbi iommu enter
    hb 8231 v266 mbi iommu done
    fixed row: hb 8233/8177 v266 mbi populate enter

so the 2 MB pool is correctly sized, yet freelist_populate() still sleeps
-- even though m_minlimit(MC_BIGCL) = nclusters>>6 makes the very first
m_clalloc() ask for only a few dozen KB.

The reason is in kernel_memory_allocate() (vm_resident.c):

    if (flags & KMA_LOMEM) {
            mem = vm_page_grablo();          // dedicated low-page pool
    } else {
            mem = vm_page_grab();
    }
    ...
    if ((flags & KMA_LOMEM) && (vm_lopage_needed == TRUE)) {
            kr = KERN_RESOURCE_SHORTAGE; goto out;   // graceful
    }
    ...
    VM_PAGE_WAIT();                          // forever

vm_page_grablo() draws from the lopage pool, which this bring-up never
fills; with vm_lopage_needed == FALSE the KERN_RESOURCE_SHORTAGE exit is
skipped and every KMA_LOMEM request falls into VM_PAGE_WAIT() with no
pageout daemon to wake it.  kmem_mb_alloc() is the only mbuf-path user of
KMA_LOMEM, and its requests are tiny after the v269 cap, so plain
KMA_KOBJECT (normal vm_page_grab) is both safe and sufficient here.

v270 removes KMA_LOMEM from both kmem_mb_alloc() calls and adds traces
around them (mba size/contig/ok/err) so any further stall in the cluster
path is visible on the fixed row.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v270"


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


s = read(MBUF)
if MARK not in s:
    s = sub(
        s,
        """	if (!physContig) {
		kr = kmem_alloc(mbmap, &addr, size,
		    KMA_KOBJECT | KMA_LOMEM, VM_KERN_MEMORY_MBUF);
	} else {
		kr = kmem_alloc_contig(mbmap, &addr, size, PAGE_MASK, 0xfffff,
		    0, KMA_KOBJECT | KMA_LOMEM, VM_KERN_MEMORY_MBUF);
	}

	if (kr != KERN_SUCCESS) {
		addr = 0;
	}""",
        """	/* g0245d v270: KMA_LOMEM draws from the lopage pool via
	 * vm_page_grablo(); this bring-up never fills that pool and
	 * vm_lopage_needed == FALSE skips the graceful RESOURCE_SHORTAGE
	 * exit, so every request sleeps forever in VM_PAGE_WAIT().  Use
	 * plain KMA_KOBJECT (normal vm_page_grab path) instead.
	 */
	g0245d_trace_u("v270 mba size", (unsigned int)size);
	g0245d_trace_u("v270 mba contig", (unsigned int)physContig);
	if (!physContig) {
		kr = kmem_alloc(mbmap, &addr, size,
		    KMA_KOBJECT, VM_KERN_MEMORY_MBUF);
	} else {
		kr = kmem_alloc_contig(mbmap, &addr, size, PAGE_MASK, 0xfffff,
		    0, KMA_KOBJECT, VM_KERN_MEMORY_MBUF);
	}

	if (kr != KERN_SUCCESS) {
		g0245d_trace_u("v270 mba err", (unsigned int)kr);
		addr = 0;
	} else {
		g0245d_trace("v270 mba ok");
	}""",
        "uipc_mbuf: drop KMA_LOMEM",
    )
    write(MBUF, s)
    print("uipc_mbuf: v270 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v270 patch applied")
