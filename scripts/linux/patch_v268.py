#!/usr/bin/env python3
"""g0245d v268 -- static fallback for the mbuf cluster paddr table.

v267's fixed heartbeat row reads

    hb 8226/8170 v266 mbi paddr enter

so mleak_activate() is now fully bypassed (v267 mleak buckets 512 /
mleak disabled both printed) and the new stop is the very next permanent
allocation:

    mcl_paddr = zalloc_permanent(mcl_pages * sizeof(ppnum_t), ZALIGN(ppnum_t));

with mcl_pages == 512 (nmbclusters floored at 1024 clusters, 2 KB clusters,
4 KB pages).  _zalloc_permanent() loops on zone_expand_locked(Z_WAITOK)
once the permanent zone has no partial page with room, and expansion ends
in vm_page_grab() -> VM_PAGE_WAIT() -- a forever sleep before vm_pageout
exists.  Same wall the mleak tables hit; zalloc_permanent() has no
no-wait variant at all, so there is no graceful failure to request.

Downstream usage is safe with a static zeroed table:

  - writes only happen under `if (mcl_paddr_base != 0)`, and
    IOMapperIOVMAlloc() returns 0 when IOMapper::gSystem is NULL (this
    bring-up has no mapper), so no writes will occur;
  - reads return 0, which is harmless (physical page 0 is never claimed
    while the mapper is absent).

v268 replaces the allocation with a 2048-entry static array (8 KB BSS,
covers nmbclusters up to 4096) and keeps the v266 traces intact so the
boot proceeds to the next instrumented stop: freelist_populate().
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v268"


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
        """	g0245d_trace("v266 mbi paddr enter");
	mcl_paddr = zalloc_permanent(mcl_pages * sizeof(ppnum_t),
	    ZALIGN(ppnum_t));
	g0245d_trace("v266 mbi paddr done");""",
        """	g0245d_trace("v266 mbi paddr enter");
	/* g0245d v268: zalloc_permanent() sleeps forever once the permanent
	 * zone is exhausted (zone_expand_locked -> vm_page_grab ->
	 * VM_PAGE_WAIT, no pageout yet).  Use a static zeroed table instead:
	 * writes are guarded by mcl_paddr_base != 0 and IOMapperIOVMAlloc()
	 * returns 0 without a mapper, reads yield 0 which is harmless.
	 */
	static ppnum_t g0245d_mcl_paddr_buf[2048];
	if (mcl_pages <= 2048) {
		g0245d_trace("v268 mbi paddr static");
		mcl_paddr = g0245d_mcl_paddr_buf;
	} else {
		g0245d_trace("v268 mbi paddr skip");
		mcl_paddr = NULL;
	}
	g0245d_trace("v266 mbi paddr done");""",
        "uipc_mbuf: static mcl_paddr",
    )
    write(MBUF, s)
    print("uipc_mbuf: v268 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v268 patch applied")
