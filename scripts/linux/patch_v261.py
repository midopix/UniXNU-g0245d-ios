#!/usr/bin/env python3
"""g0245d v261 -- bracket mbinit() so the next photo shows how far it gets.

v260 fixed read_random().  mbinit() has more work after the three redzone
cookies: mbuf_table_init(), a permanent slab-groups table sized from
nmbclusters, and (when mbuf_debug is set) very large audit arrays.  v261 adds
four breadcrumbs plus the two numbers that decide the allocation sizes,
because a sane `nmbclusters` and a crazy one look identical from outside.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v261"


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
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v261: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);""",
        "uipc_mbuf: externs",
    )

    s = sub(
        s,
        """	read_random(&mb_redzone_cookie, sizeof(mb_redzone_cookie));
	read_random(&mb_obscure_extref, sizeof(mb_obscure_extref));
	read_random(&mb_obscure_extfree, sizeof(mb_obscure_extfree));""",
        """	g0245d_trace("v261 mbi rand enter");
	read_random(&mb_redzone_cookie, sizeof(mb_redzone_cookie));
	read_random(&mb_obscure_extref, sizeof(mb_obscure_extref));
	read_random(&mb_obscure_extfree, sizeof(mb_obscure_extfree));
	g0245d_trace("v261 mbi rand done");""",
        "uipc_mbuf: read_random bracket",
    )

    s = sub(
        s,
        """	if (nmbclusters == 0) {
		nmbclusters = NMBCLUSTERS;
	}""",
        """	if (nmbclusters == 0) {
		nmbclusters = NMBCLUSTERS;
	}
	g0245d_trace_u("v261 mbi nmbclusters", nmbclusters);""",
        "uipc_mbuf: nmbclusters",
    )

    s = sub(
        s,
        """	/* Setup the mbuf table */
	mbuf_table_init();""",
        """	/* Setup the mbuf table */
	g0245d_trace("v261 mbi table enter");
	mbuf_table_init();
	g0245d_trace("v261 mbi table done");""",
        "uipc_mbuf: mbuf_table_init",
    )

    s = sub(
        s,
        """	slabstbl = zalloc_permanent(maxslabgrp * sizeof(mcl_slabg_t *),
	    ZALIGN(mcl_slabg_t));""",
        """	g0245d_trace_u("v261 mbi maxslabgrp", (unsigned int)maxslabgrp);
	g0245d_trace("v261 mbi slab enter");
	slabstbl = zalloc_permanent(maxslabgrp * sizeof(mcl_slabg_t *),
	    ZALIGN(mcl_slabg_t));
	g0245d_trace("v261 mbi slab done");""",
        "uipc_mbuf: slab table",
    )

    write(MBUF, s)
    print("uipc_mbuf: v261 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v261 patch applied")
