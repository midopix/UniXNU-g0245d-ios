#!/usr/bin/env python3
"""g0245d v304 -- dissect the devfs_mount() freeze.

Evidence (v303 photo 17:02:53):
  mount_common probes mc enter/prep/zalloc ok/vfs call all hit; heartbeat
  `hb 8564/8521 v303 mc vfs call`, no `mc vfs ret`.  => mount_zone Z_WAITOK
  allocation was NOT the wall (it passed); frozen INSIDE VFS_MOUNT, i.e.
  devfs_mount() (devfs_vfsops.c:172).  Suspects: kalloc_type(devfsmount,
  Z_WAITOK|Z_NOFAIL), DEVFS_LOCK, dev_dup_plane() (builds the whole devfs
  device tree with vnode creations + node allocations -- prime suspect),
  devfs_statfs().

v304 (label-only diagnostic probes, no behavior change):
  devfs_vfsops.c devfs_mount(): entry, after kalloc_type, after DEVFS_LOCK,
  before/after dev_dup_plane, after devfs_statfs.
    `v304 dm enter` / `v304 dm kalloc ok` / `v304 dm lock ok` /
    `v304 dm dup call` / `v304 dm dup ret<r>` / `v304 dm statfs ok`.

Idempotent.  Run on the tree that already has v303 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v304.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

VFSOP = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "g0245d v304"


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
TRACEU = ('{ extern void g0245d_trace_u(const char *, unsigned int); '
          'g0245d_trace_u("%s", (unsigned int)(%s)); }')


s = read(VFSOP)
if MARK in s:
    print("devfs_vfsops.c: already v304")
else:
    # entry (after the local declarations)
    s = sub(
        s,
        """	struct devfsmount *devfs_mp_p;  /* devfs specific mount info */
	int error;

	/*-""",
        """	struct devfsmount *devfs_mp_p;  /* devfs specific mount info */
	int error;
	""" + TRACE % "v304 dm enter" + """

	/*-""",
        "v304: devfs_mount entry",
    )
    # after kalloc_type
    s = sub(
        s,
        """	devfs_mp_p = kalloc_type(struct devfsmount,
	    Z_WAITOK | Z_ZERO | Z_NOFAIL);
	devfs_mp_p->mount = mp;""",
        """	devfs_mp_p = kalloc_type(struct devfsmount,
	    Z_WAITOK | Z_ZERO | Z_NOFAIL);
	""" + TRACE % "v304 dm kalloc ok" + """
	devfs_mp_p->mount = mp;""",
        "v304: after kalloc_type",
    )
    # after DEVFS_LOCK / around dev_dup_plane
    s = sub(
        s,
        """	DEVFS_LOCK();
	error = dev_dup_plane(devfs_mp_p);
	DEVFS_UNLOCK();""",
        """	DEVFS_LOCK();
	""" + TRACE % "v304 dm lock ok" + """
	""" + TRACE % "v304 dm dup call" + """
	error = dev_dup_plane(devfs_mp_p);
	""" + TRACEU % ("v304 dm dup ret", "error") + """
	DEVFS_UNLOCK();""",
        "v304: dev_dup_plane probes",
    )
    # after devfs_statfs
    s = sub(
        s,
        """	(void)devfs_statfs(mp, &mp->mnt_vfsstat, ctx);

	return 0;""",
        """	(void)devfs_statfs(mp, &mp->mnt_vfsstat, ctx);
	""" + TRACE % "v304 dm statfs ok" + """

	return 0;""",
        "v304: after devfs_statfs",
    )
    write(VFSOP, s)
    print("devfs_vfsops.c: v304 devfs_mount probes installed")

print("v304 patch complete")
