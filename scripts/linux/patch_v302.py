#!/usr/bin/env python3
"""g0245d v302 -- bypass the name-cache update wall (the v301 freeze).

Evidence (v301 photo 16:49:50):
  `v301 look vnode ret 0` (VNOP_LOOKUP succeeded) -> `v301 lhfv cache`
  (entered lookup_handle_found_vnode, probe placed immediately BEFORE the
  lookup_consider_update_cache() call) -> nothing more; heartbeat froze at
  `hb 8551/8508 v301 lhfv cache`.  => frozen INSIDE
  lookup_consider_update_cache() (vfs_lookup.c:687), whose two suspects are
  vnode_update_identity() and cache_enter_with_gen() (name-cache zalloc,
  the same allocation-wall class as v291-v298).

v302 (behavior change, but correctness-neutral):
  lookup_consider_update_cache() is PURE OPTIMIZATION -- it only writes the
  lookup result into the name cache and updates vnode name/parent metadata.
  mockfs is an in-memory rootfs with no performance need for it.  Bypass both
  call sites (vfs_lookup.c:875 in lookup_handle_found_vnode, vfs_lookup.c:2255
  in the compound-VNOP path) with `v302 cache skip` probes.
  If boot advances past devfs/siginit => the name-cache allocation was the
  wall.  If it still freezes, the retained v301 probes will localize the next
  wall.

Idempotent.  Run on the tree that already has v301 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v302.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

LOOKUP = os.path.join(WORK, "bsd/vfs/vfs_lookup.c")
MARK = "g0245d v302"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what, count=1):
    n = src.count(old)
    if n != count:
        sys.exit("%s: anchor found %d times (expected %d)" % (what, n, count))
    return src.replace(old, new)


SKIP = ('{ extern void g0245d_trace(const char *); '
        'g0245d_trace("%s"); }')

s = read(LOOKUP)
if MARK in s:
    print("vfs_lookup.c: already v302")
else:
    # call site 1: lookup_handle_found_vnode() (the exact v301 freeze)
    s = sub(
        s,
        """	} else {
		{ extern void g0245d_trace(const char *); g0245d_trace("v301 lhfv cache"); }
		lookup_consider_update_cache(ndp->ni_dvp, dp, cnp, nc_generation);
	}""",
        """	} else {
		""" + SKIP % "v302 cache skip" + """
		/* g0245d v302: name-cache update bypassed (pure optimization) */
		/* lookup_consider_update_cache(ndp->ni_dvp, dp, cnp, nc_generation); */
	}""",
        "v302: bypass name-cache call site 1",
    )
    # call site 2: compound VNOP path
    s = sub(
        s,
        """		if ((error != 0) || (ndp->ni_cnd.cn_flags & MAKEENTRY)) {
			lookup_consider_update_cache(dvp, vp, &ndp->ni_cnd, ndp->ni_ncgeneration);
		}""",
        """		if ((error != 0) || (ndp->ni_cnd.cn_flags & MAKEENTRY)) {
			""" + SKIP % "v302 cache skip2" + """
			/* g0245d v302: name-cache update bypassed (pure optimization) */
			/* lookup_consider_update_cache(dvp, vp, &ndp->ni_cnd, ndp->ni_ncgeneration); */
		}""",
        "v302: bypass name-cache call site 2",
    )
    write(LOOKUP, s)
    print("vfs_lookup.c: v302 name-cache bypass installed")

print("v302 patch complete")
