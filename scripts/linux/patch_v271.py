#!/usr/bin/env python3
"""g0245d v271 -- trace m_clalloc() between the successful allocation and
freelist_populate done.

v270's fixed row reads

    hb 8236/8188 v270 mba ok

with the ring showing

    8233 v266 mbi populate enter
    8234 v270 mba size 32768
    8235 v270 mba contig 0
    8236 v270 mba ok

So dropping KMA_LOMEM worked -- the very first cluster-page allocation
(32 KB, initmcl 8) succeeded through the normal vm_page_grab path.  But
no further trace printed: the boot stalls somewhere inside m_clalloc()
between the allocation and its return (net_update_uptime, the mclaudit
MCR_SLEEP allocations, or the slab-building page loop -- none of which
has a trace yet).

v271 brackets every step of that window:

    v271 mcl nup      before net_update_uptime()
    v271 mcl chk      after it (page checks next)
    v271 mcl npages   after numpages = size/PAGE_SIZE
    v271 mcl audit    mclaudit != NULL, before MCR_SLEEP allocs
    v271 mcl pg <i>   each page of the slab-building loop
    v271 mcl auditdone / loopdone / ret

Pure diagnosis -- no behavior change.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v271"


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
        """	 * If we did ask for "n" 16KB physically contiguous chunks
	 * and didn't get them, then please try again without this
	 * restriction.
	 */
	net_update_uptime();""",
        """	 * If we did ask for "n" 16KB physically contiguous chunks
	 * and didn't get them, then please try again without this
	 * restriction.
	 */
	g0245d_trace("v271 mcl nup");
	net_update_uptime();
	g0245d_trace("v271 mcl chk");""",
        "m_clalloc: net_update_uptime",
    )

    s = sub(
        s,
        """	VERIFY(IS_P2ALIGNED(page, PAGE_SIZE));
	numpages = size / PAGE_SIZE;""",
        """	VERIFY(IS_P2ALIGNED(page, PAGE_SIZE));
	numpages = size / PAGE_SIZE;
	g0245d_trace_u("v271 mcl npages", (unsigned int)numpages);""",
        "m_clalloc: npages",
    )

    s = sub(
        s,
        """	if (mclaudit != NULL) {
		int needed;
""",
        """	if (mclaudit != NULL) {
		int needed;

		g0245d_trace("v271 mcl audit");
""",
        "m_clalloc: audit enter",
    )

    s = sub(
        s,
        """		VERIFY(mca_list != NULL && i == needed);
	}

	lck_mtx_lock(mbuf_mlock);""",
        """		VERIFY(mca_list != NULL && i == needed);
		g0245d_trace("v271 mcl auditdone");
	}

	lck_mtx_lock(mbuf_mlock);""",
        "m_clalloc: audit done",
    )

    s = sub(
        s,
        """	for (i = 0; i < numpages; i++, page += PAGE_SIZE) {
		ppnum_t offset =""",
        """	for (i = 0; i < numpages; i++, page += PAGE_SIZE) {
		g0245d_trace_u("v271 mcl pg", (unsigned int)i);
		ppnum_t offset =""",
        "m_clalloc: page loop",
    )

    s = sub(
        s,
        """	VERIFY(mca_list == NULL && con_list == NULL);""",
        """	VERIFY(mca_list == NULL && con_list == NULL);
	g0245d_trace("v271 mcl loopdone");""",
        "m_clalloc: loop done",
    )

    s = sub(
        s,
        """	return count;
out:""",
        """	g0245d_trace("v271 mcl ret");
	return count;
out:""",
        "m_clalloc: return",
    )

    write(MBUF, s)
    print("uipc_mbuf: v271 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v271 patch applied")
