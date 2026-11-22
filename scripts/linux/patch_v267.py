#!/usr/bin/env python3
"""g0245d v267 -- disable mbuf leak logging, the next permanent allocation wall.

v266's pinned row reads

    hb 8221/8165 v266 mbi debug parsed

and that trace sits immediately before mleak_activate(), whose body is:

    if (mclfindleak == 0) return;
    mleak_allocations = zalloc_permanent(mleak_alloc_buckets * sizeof(struct mallocation), ...);
    mleak_traces      = zalloc_permanent(mleak_trace_buckets  * sizeof(struct mtrace), ...);
    mleak_stat        = zalloc_permanent(MLEAK_STAT_SIZE(MLEAK_NUM_TRACES), ...);

Those buckets are sized for a full-sized machine; on this bring-up VM believes
it has 56 MB, so the first zalloc_permanent either fails or never returns.
Mbuf leak logging is a debug facility -- useless for getting to userland.

mclfindleak is a plain global, and mleak_activate() returns immediately when it
is zero, so v267 clears it right before the call and leaves the code untouched.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v267"


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
        """	g0245d_trace("v266 mbi debug parsed");
	mleak_activate();
	g0245d_trace("v266 mbi mleak done");""",
        """	g0245d_trace("v266 mbi debug parsed");
	/* g0245d v267: mleak_activate() allocates several permanent tables
	 * sized by mleak_alloc_buckets / mleak_trace_buckets.  With VM
	 * believing it has 56 MB those allocations fail or hang, and leak
	 * logging is not needed to reach userland.  mleak_activate() returns
	 * immediately when mclfindleak == 0.
	 */
	g0245d_trace_u("v267 mleak buckets",
	    (unsigned int)mleak_alloc_buckets);
	mclfindleak = 0;
	g0245d_trace("v267 mleak disabled");
	mleak_activate();
	g0245d_trace("v266 mbi mleak done");""",
        "uipc_mbuf: disable mleak",
    )
    write(MBUF, s)
    print("uipc_mbuf: v267 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v267 patch applied")
