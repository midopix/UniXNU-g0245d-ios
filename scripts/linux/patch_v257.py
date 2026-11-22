#!/usr/bin/env python3
"""g0245d v257 -- stop hashinit from sleeping forever on a 128 KB allocation.

v256's photo: hb 8132 with the ladder 8129 hash enter / 8130 hi elements 22000 /
8131 hi size 16384 / 8132 hi alloc enter -- and no "hi alloc ret".  So the
machine is inside kalloc_type(struct generic_hash_head, 16384, Z_WAITOK|Z_ZERO),
i.e. a 128 KB zero-filled typed allocation that sleeps instead of returning.

Z_WAITOK means "may block until memory is available".  At this point in boot
vm_pageout() has not started (it is the last thing bsd_init does), and every
earlier kalloc in bsd_init was a small object served from an existing zone.
A 128 KB request needs new pages; if none are free the caller waits for a
page-reclaim thread that does not exist yet -- a silent deadlock.

v257 changes three things:

  1. hashinit() asks with Z_NOWAIT and reports a NULL result instead of
     sleeping.  A hash table is not worth a deadlock, and every caller in this
     tree already treats a NULL table as "no table".
  2. nchinit() caps the bucket count for this bring-up (2048 buckets = 16 KB,
     a size class that is already backed), instead of 16384.
  3. nchinit() falls back to a static 256-bucket array initialised with
     smrq_init() if hashinit() still returns NULL, so namei can proceed.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

SUBR = os.path.join(WORK, "bsd/kern/kern_subr.c")
CACHE = os.path.join(WORK, "bsd/vfs/vfs_cache.c")

MARK = "g0245d v257"


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
        """	g0245d_trace("v256 hi alloc enter");
	hashtbl = kalloc_type(struct generic_hash_head, hashsize, Z_WAITOK | Z_ZERO);
	g0245d_tracev("v256 hi alloc ret", (unsigned long long)(uintptr_t)hashtbl);""",
        """	g0245d_trace("v256 hi alloc enter");
	/* g0245d v257: Z_WAITOK sleeps until pages can be reclaimed, but
	 * vm_pageout() has not started yet at bsd_init time -- a 128 KB table
	 * would wait forever.  Ask without sleeping and let the caller decide.
	 */
	hashtbl = kalloc_type(struct generic_hash_head, hashsize,
	    Z_NOWAIT | Z_ZERO);
	g0245d_tracev("v256 hi alloc ret", (unsigned long long)(uintptr_t)hashtbl);
	if (hashtbl == NULL) {
		g0245d_trace("v257 hi alloc failed");
	}""",
        "kern_subr: Z_NOWAIT",
    )
    write(SUBR, s)
    print("kern_subr: v257 changes applied")
else:
    print("kern_subr: already patched")

# -------------------------------------------------------------- vfs_cache.c
s = read(CACHE)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v255 hash enter");
	nchashtbl = hashinit(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), M_CACHE, &nchash);""",
        """	g0245d_trace("v255 hash enter");
	/* g0245d v257: 2*desiredNodes can reach 22000 buckets = 176 KB, which
	 * needs fresh pages and used to deadlock in kalloc_type(Z_WAITOK).
	 * Cap it for bring-up; 2048 buckets is 16 KB, a backed size class.
	 */
	nchashtbl = hashinit(MIN(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), 2048),
	    M_CACHE, &nchash);
	if (nchashtbl == NULL) {
		static struct smrq_list_head g0245d_nch_static[256];
		g0245d_trace("v257 nch fallback");
		for (int i = 0; i < 256; i++) {
			smrq_init(&g0245d_nch_static[i]);
		}
		nchashtbl = g0245d_nch_static;
		nchash = 256 - 1;
	}""",
        "vfs_cache: cap and fallback",
    )
    write(CACHE, s)
    print("vfs_cache: v257 changes applied")
else:
    print("vfs_cache: already patched")

print("v257 patch applied")
