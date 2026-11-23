#!/usr/bin/env python3
"""g0245d v305 -- pin down the freeze between dm kalloc and DEVFS_LOCK.

Evidence (v304 photo 17:08:21):
  probes reached `v304 dm kalloc ok` (8566), heartbeat
  `hb 8566/8523 v304 dm kalloc ok`, but NO `dm lock ok`.  => frozen in the
  short span after the devfsmount kalloc and before/at DEVFS_LOCK()
  (devfs_vfsops.c:193-207).  That span is a few assignments + DEVFS_LOCK()
  = lck_mtx_lock(&devfs_mutex).  devfs_mutex is LCK_MTX_DECLARE'd with no
  explicit lck_mtx_init, but devfs_sinit() uses DEVFS_LOCK() successfully
  before devfs_mount, so the lock may be statically valid -- need a probe
  immediately before and after DEVFS_LOCK() to disambiguate.

v305 (label-only diagnostic probes, no behavior change):
  devfs_vfsops.c devfs_mount(): pin the assignments + the lock.
    `v305 dm assign`   (right before DEVFS_LOCK, after the assignments)
    `v305 pre lock`    (immediately before lck_mtx_lock)
    `v305 post lock`   (immediately after lock returns)
  Retained v304 probes (dm kalloc ok / dm lock ok / dm dup call) remain as
  cross-check markers.

Idempotent.  Run on the tree that already has v304 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v305.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

VFSOP = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "g0245d v305"


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


TRACE = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'


s = read(VFSOP)
if MARK in s:
    print("devfs_vfsops.c: already v305")
else:
    # pin right before DEVFS_LOCK (after all the assignments incl. mnt_flag)
    s = sub(
        s,
        """	mp->mnt_flag |= MNT_LOCAL;

	DEVFS_LOCK();
	{ extern void g0245d_trace(const char *); g0245d_trace("v304 dm lock ok"); }""",
        """	mp->mnt_flag |= MNT_LOCAL;
	""" + TRACE % "v305 dm assign" + """

	""" + TRACE % "v305 pre lock" + """
	DEVFS_LOCK();
	""" + TRACE % "v305 post lock" + """
	{ extern void g0245d_trace(const char *); g0245d_trace("v304 dm lock ok"); }""",
        "v305: pin DEVFS_LOCK",
    )
    write(VFSOP, s)
    print("devfs_vfsops.c: v305 DEVFS_LOCK probes installed")

print("v305 patch complete")
