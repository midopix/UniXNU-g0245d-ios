#!/usr/bin/env python3
"""g0245d v255 -- open up nchinit(), the real stop.

The three photos are one frame, and the pinned row reads "hb 8108" (not 8188
as I first misread).  That makes the ring and the heartbeat agree to within
two traces, so the machine really is parked around 8107/8108:

    8103 v250 vntblinit done
    8104 v250 vfs event enter
    8105 v252 klist enter
    8106 v252 klist done
    8107 v250 vfs event done      (faint row)
    8108 v250 nchinit enter       (hb = 8108)

vfb_event_init is therefore fine and the stop is inside nchinit().  Its body:

    desiredNegNodes = desiredvnodes / 10;
    desiredNodes = desiredvnodes + desiredNegNodes;
    if (nc_smr_enabled) { zone_enable_smr(namecache_zone, ...); ... }
    TAILQ_INIT(&nchead); TAILQ_INIT(&neghead);
    init_crc32();                       /* 256*8 iterations, pure arithmetic */
    nchashtbl = hashinit(MAX(CONFIG_NC_HASH, 2 * desiredNodes), M_CACHE, &nchash);
    init_string_table();
    for (i < NUM_STRCACHE_LOCKS) lck_mtx_init(...);

init_crc32() cannot hang.  hashinit() allocates and then initialises a bucket
array whose size is 2*desiredNodes, and desiredvnodes scales with physical
memory -- if the value this bring-up derives is absurd, hashinit either runs
for a very long time or cannot allocate.  So v255 traces each statement and
prints desiredvnodes / desiredNodes themselves.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

CACHE = os.path.join(WORK, "bsd/vfs/vfs_cache.c")

MARK = "g0245d v255"


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


s = read(CACHE)
if MARK not in s:
    s = sub(
        s,
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v255: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);
extern void g0245d_probe(const char *label);""",
        "vfs_cache: externs",
    )

    s = sub(
        s,
        """nchinit(void)
{
	desiredNegNodes = (desiredvnodes / 10);
	desiredNodes = desiredvnodes + desiredNegNodes;

	if (nc_smr_enabled) {
		zone_enable_smr(namecache_zone, VFS_SMR(), &namecache_smr_free);
		zone_enable_smr(stringcache_zone, VFS_SMR(), &string_smr_free);
	}
	TAILQ_INIT(&nchead);
	TAILQ_INIT(&neghead);

	init_crc32();

	nchashtbl = hashinit(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), M_CACHE, &nchash);""",
        """nchinit(void)
{
	g0245d_trace("v255 nch enter");
	desiredNegNodes = (desiredvnodes / 10);
	desiredNodes = desiredvnodes + desiredNegNodes;
	g0245d_trace_u("v255 desiredvnodes", (unsigned int)desiredvnodes);
	g0245d_trace_u("v255 desiredNodes", (unsigned int)desiredNodes);

	if (nc_smr_enabled) {
		g0245d_trace("v255 smr enter");
		zone_enable_smr(namecache_zone, VFS_SMR(), &namecache_smr_free);
		zone_enable_smr(stringcache_zone, VFS_SMR(), &string_smr_free);
		g0245d_trace("v255 smr done");
	}
	TAILQ_INIT(&nchead);
	TAILQ_INIT(&neghead);
	g0245d_trace("v255 tails done");

	g0245d_trace("v255 crc enter");
	init_crc32();
	g0245d_trace("v255 crc done");

	g0245d_trace("v255 hash enter");
	nchashtbl = hashinit(MAX(CONFIG_NC_HASH, (2 * desiredNodes)), M_CACHE, &nchash);
	g0245d_trace("v255 hash done");""",
        "vfs_cache: nchinit ladder",
    )

    s = sub(
        s,
        """	init_string_table();

	for (int i = 0; i < NUM_STRCACHE_LOCKS; i++) {
		lck_mtx_init(&strcache_mtx_locks[i], &strcache_lck_grp, &strcache_lck_attr);
	}
}""",
        """	g0245d_trace("v255 strtab enter");
	init_string_table();
	g0245d_trace("v255 strtab done");

	g0245d_trace("v255 locks enter");
	for (int i = 0; i < NUM_STRCACHE_LOCKS; i++) {
		lck_mtx_init(&strcache_mtx_locks[i], &strcache_lck_grp, &strcache_lck_attr);
	}
	g0245d_probe("v255 nch done");
	g0245d_trace("v255 nch done");
}""",
        "vfs_cache: nchinit tail",
    )

    write(CACHE, s)
    print("vfs_cache: v255 changes applied")
else:
    print("vfs_cache: already patched")

print("v255 patch applied")
