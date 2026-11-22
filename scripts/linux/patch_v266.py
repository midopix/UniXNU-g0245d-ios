#!/usr/bin/env python3
"""g0245d v266 -- trace the rest of mbinit() after the slab table.

v265's heartbeat label finally tells us where the boot is:

    hb 8220/8164 v261 mbi slab done

so mbinit() passes read_random, mbuf_table_init and the slab-groups table, and
stops somewhere in the remaining work:

    PE_parse_boot_argn("mbuf_debug", ...); mbuf_debug |= mcache_getflags();
    if (mbuf_debug & MCF_DEBUG) { ...big audit arrays... }
    mleak_activate();
    ncpu = ml_wait_max_cpus();
    mcl_pages = (nmbclusters << MCLSHIFT) / PAGE_SIZE;
    mcl_paddr = zalloc_permanent(mcl_pages * sizeof(ppnum_t), ...);
    mcl_paddr_base = IOMapperIOVMAlloc(mcl_pages);      <- needs an IOMapper
    embutl = mbutl + (nmbclusters * MCLBYTES);
    freelist_populate(m_class(MC_BIGCL), initmcl, M_WAIT);   <- real 2 MB

With nmbclusters floored at 1024, mcl_pages is 512 pages = 2 MB.

The sharpest suspect is IOMapperIOVMAlloc(): it asks IOKit for an I/O virtual
range, and this bring-up has no IOMapper instance.  Second is the M_WAIT
freelist_populate(), which allocates the first real cluster pages.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v266"


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
        """	mleak_activate();""",
        """	g0245d_trace("v266 mbi debug parsed");
	mleak_activate();
	g0245d_trace("v266 mbi mleak done");""",
        "uipc_mbuf: mleak",
    )

    s = sub(
        s,
        """	/* Calculate the number of pages assigned to the cluster pool */
	mcl_pages = (nmbclusters << MCLSHIFT) / PAGE_SIZE;
	mcl_paddr = zalloc_permanent(mcl_pages * sizeof(ppnum_t),
	    ZALIGN(ppnum_t));

	/* Register with the I/O Bus mapper */
	mcl_paddr_base = IOMapperIOVMAlloc(mcl_pages);""",
        """	/* Calculate the number of pages assigned to the cluster pool */
	mcl_pages = (nmbclusters << MCLSHIFT) / PAGE_SIZE;
	g0245d_trace_u("v266 mbi mcl_pages", (unsigned int)mcl_pages);
	g0245d_trace("v266 mbi paddr enter");
	mcl_paddr = zalloc_permanent(mcl_pages * sizeof(ppnum_t),
	    ZALIGN(ppnum_t));
	g0245d_trace("v266 mbi paddr done");

	/* Register with the I/O Bus mapper */
	g0245d_trace("v266 mbi iommu enter");
	mcl_paddr_base = IOMapperIOVMAlloc(mcl_pages);
	g0245d_trace("v266 mbi iommu done");""",
        "uipc_mbuf: paddr + iommu",
    )

    s = sub(
        s,
        """	VERIFY(m_total(MC_BIGCL) == 0 && m_minlimit(MC_BIGCL) != 0);
	freelist_populate(m_class(MC_BIGCL), initmcl, M_WAIT);
	VERIFY(m_total(MC_BIGCL) >= m_minlimit(MC_BIGCL));""",
        """	VERIFY(m_total(MC_BIGCL) == 0 && m_minlimit(MC_BIGCL) != 0);
	g0245d_trace_u("v266 mbi initmcl", (unsigned int)initmcl);
	g0245d_trace("v266 mbi populate enter");
	freelist_populate(m_class(MC_BIGCL), initmcl, M_WAIT);
	g0245d_trace("v266 mbi populate done");
	VERIFY(m_total(MC_BIGCL) >= m_minlimit(MC_BIGCL));""",
        "uipc_mbuf: freelist_populate",
    )

    write(MBUF, s)
    print("uipc_mbuf: v266 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v266 patch applied")
