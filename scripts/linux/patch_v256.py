#!/usr/bin/env python3
"""g0245d v256 -- open up hashinit(), the actual stop.

v255's photo is fully legible:

    8109 v255 nch enter
    8110 v255 desiredvnodes 10000
    8111 v255 desiredNodes 11000
    8112 v255 smr enter
    8113 v255 smr done
    8114 v255 tails done
    8115 v255 crc enter
    (two faint rows)
    hb 8117/8074

desiredvnodes is 10000 -- entirely sane, so the "absurd bucket count" theory
is dead.  hb says the newest trace is 8117, and counting the ladder that is
"v255 hash enter": crc done is 8116, hash enter is 8117, hash done never came.
So the machine is inside hashinit():

    hashsize = 1UL << (fls(elements) - 1);          /* 22000 -> 16384 */
    hashtbl = kalloc_type(struct generic_hash_head, hashsize, Z_WAITOK | Z_ZERO);

16384 * 8 bytes = 128 KB, zero-filled, Z_WAITOK.  Either kalloc_type waits for
memory it cannot get (Z_WAITOK sleeps, and the pageout thread does not exist
yet), or the typed-allocation metadata for this element count is not ready.

v256 prints elements, hashsize and the result pointer around the call, so one
photo distinguishes those, and it also brackets the call in nchinit().
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

SUBR = os.path.join(WORK, "bsd/kern/kern_subr.c")
CACHE = os.path.join(WORK, "bsd/vfs/vfs_cache.c")

MARK = "g0245d v256"


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


# ------------------------------------------------------------- kern_subr.c
s = read(SUBR)
if MARK not in s:
    s = sub(
        s,
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v256: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);
extern void g0245d_tracev(const char *label, unsigned long long value);""",
        "kern_subr: externs",
    )
    s = sub(
        s,
        """	hashsize = 1UL << (fls(elements) - 1);
	hashtbl = kalloc_type(struct generic_hash_head, hashsize, Z_WAITOK | Z_ZERO);""",
        """	g0245d_trace_u("v256 hi elements", (unsigned int)elements);
	hashsize = 1UL << (fls(elements) - 1);
	g0245d_trace_u("v256 hi size", (unsigned int)hashsize);
	g0245d_trace("v256 hi alloc enter");
	hashtbl = kalloc_type(struct generic_hash_head, hashsize, Z_WAITOK | Z_ZERO);
	g0245d_tracev("v256 hi alloc ret", (unsigned long long)(uintptr_t)hashtbl);""",
        "kern_subr: hashinit ladder",
    )
    write(SUBR, s)
    print("kern_subr: v256 changes applied")
else:
    print("kern_subr: already patched")

# -------------------------------------------------------------- vfs_cache.c
s = read(CACHE)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v255 hash enter");
	nchashtbl = hashinit(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), M_CACHE, &nchash);
	g0245d_trace("v255 hash done");""",
        """	g0245d_trace("v255 hash enter");
	nchashtbl = hashinit(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), M_CACHE, &nchash);
	g0245d_tracev("v256 nch hashtbl", (unsigned long long)(uintptr_t)nchashtbl);
	g0245d_trace_u("v256 nch hash mask", (unsigned int)nchash);
	g0245d_trace("v255 hash done");""",
        "vfs_cache: hash result",
    )
    s = sub(
        s,
        """extern void g0245d_probe(const char *label);""",
        """extern void g0245d_probe(const char *label);
extern void g0245d_tracev(const char *label, unsigned long long value);""",
        "vfs_cache: extern tracev",
    )
    write(CACHE, s)
    print("vfs_cache: v256 changes applied")
else:
    print("vfs_cache: already patched")

print("v256 patch applied")
