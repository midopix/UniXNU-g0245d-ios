#!/usr/bin/env python3
"""g0245d v262 -- print how much memory VM thinks we have, and guard maxslabgrp.

v261's photo is the first one where mbinit() clearly moves:

    8203 bsd calling mbinit
    8204 v261 mbi rand enter
    8205 v260 read_random fallback     <- the v260 fallback fired
    8206 v261 mbi rand done
    8207 v261 mbi nmbclusters 128
    8208 v261 mbi table enter
    8209 v261 mbi table done
    hb 8212/8157

Two things stand out.  First, read_random() no longer kills the boot.  Second,
nmbclusters is 128 -- three orders of magnitude below the usual 16384, and it
echoes the pgz_slots 9 seen back in v243 (both derive from VM's idea of
physical memory).  With 128 clusters,

    maxslabgrp = (P2ROUNDUP(128,16) << 11) >> 20 = 0

so the slab-groups table is allocated with zero entries, and the first mbuf
allocation that indexes slabstbl[] will walk off it.

v262 prints sane_size and max_mem in MB next to maxslabgrp, and forces
maxslabgrp to at least 1 so a zero-length table cannot be indexed.  It does not
try to fix the memory size yet: first we need to see the numbers.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v262"


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
        """/* g0245d v261: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);""",
        """/* g0245d v261/v262: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);
/* g0245d v262: VM's idea of physical memory. */
extern uint64_t sane_size;
extern uint64_t max_mem;""",
        "uipc_mbuf: memory externs",
    )

    s = sub(
        s,
        """	g0245d_trace_u("v261 mbi nmbclusters", nmbclusters);""",
        """	g0245d_trace_u("v261 mbi nmbclusters", nmbclusters);
	g0245d_trace_u("v262 sane_size MB", (unsigned int)(sane_size >> 20));
	g0245d_trace_u("v262 max_mem MB", (unsigned int)(max_mem >> 20));""",
        "uipc_mbuf: memory sizes",
    )

    s = sub(
        s,
        """	g0245d_trace_u("v261 mbi maxslabgrp", (unsigned int)maxslabgrp);
	g0245d_trace("v261 mbi slab enter");""",
        """	g0245d_trace_u("v261 mbi maxslabgrp", (unsigned int)maxslabgrp);
	if (maxslabgrp == 0) {
		/* nmbclusters is tiny, so the whole slab-groups table rounds to
		 * zero megabytes.  Never hand a zero-length table to mbuf code.
		 */
		g0245d_trace("v262 slabgrp zero -> 1");
		maxslabgrp = 1;
	}
	g0245d_trace("v261 mbi slab enter");""",
        "uipc_mbuf: maxslabgrp guard",
    )

    write(MBUF, s)
    print("uipc_mbuf: v262 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v262 patch applied")
