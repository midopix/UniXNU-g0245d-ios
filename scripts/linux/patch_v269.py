#!/usr/bin/env python3
"""g0245d v269 -- cap nmbclusters, shrink the mbuf cluster pool to fit.

v268's ring reads

    hb 8222 v267 mleak buckets 512
    hb 8223 v267 mleak disabled
    hb 8224 v266 mbi mleak done
    hb 8225 v266 mbi mcl_pages 16384      <- surprise
    hb 8226 v266 mbi paddr enter
    hb 8227 v268 mbi paddr skip           <- 16384 > 2048, mcl_paddr = NULL
    hb 8228 v266 mbi paddr done
    hb 8229 v266 mbi iommu enter
    hb 8230 v266 mbi iommu done           <- no mapper, returned 0 quickly
    fixed row: hb 8232/8175 v266 mbi populate enter

So v268 behaved exactly as designed, IOMapperIOVMAlloc() is harmless, and
the stop moved into freelist_populate(MC_BIGCL, initmcl, M_WAIT).

The surprise: mcl_pages == 16384.  With sane_size raised to 512 MB, the
nmbclusters formula yields 32768 clusters = 64 MB of wired pool inside a
56 MB view.  The v264 floor only raises the value, it never lowers it, so
the pool is 12x the memory the VM believes it has.  freelist_populate()
ends in kmem_mb_alloc() -> kmem_alloc(mbmap, KMA_KOBJECT | KMA_LOMEM,
M_WAIT) and sleeps forever: the LOMEM pages do not exist.

v269 caps nmbclusters at 1024 (2 MB pool).  Everything downstream scales
with it: mcl_pages becomes 512 (back inside the v268 static table, so
mcl_paddr is a real zeroed array again instead of NULL), m_minlimit and
initmcl shrink proportionally, and the VERIFY(m_total >= m_minlimit)
after populate still holds.  2 MB of clusters is plenty to reach
userland.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v269"


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
        """	if (nmbclusters < 1024) {
		g0245d_trace_u("v264 nmbclusters floor from", nmbclusters);
		nmbclusters = 1024;
	}
	g0245d_trace_u("v261 mbi nmbclusters", nmbclusters);""",
        """	if (nmbclusters < 1024) {
		g0245d_trace_u("v264 nmbclusters floor from", nmbclusters);
		nmbclusters = 1024;
	}
	/* g0245d v269: with sane_size at 512 MB the formula asks for 32768
	 * clusters = 64 MB of wired pool inside a 56 MB view.  The pool and
	 * its populate (kmem_alloc KMA_LOMEM, M_WAIT) sleep forever.  Cap
	 * at 1024 clusters = 2 MB; mcl_pages returns to 512, back inside
	 * the v268 static paddr table, and every minlimit/initmcl scales
	 * down with it.
	 */
	if (nmbclusters > 1024) {
		g0245d_trace_u("v269 nmbclusters cap from", nmbclusters);
		nmbclusters = 1024;
	}
	g0245d_trace_u("v261 mbi nmbclusters", nmbclusters);""",
        "uipc_mbuf: cap nmbclusters",
    )
    write(MBUF, s)
    print("uipc_mbuf: v269 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v269 patch applied")
