#!/usr/bin/env python3
"""g0245d v303 -- dissect the mount_common() freeze (namei wall is broken).

Evidence (v302 photo 16:55:31):
  v302 bypassed lookup_consider_update_cache(); namei's whole chain passed --
  `lhfv trav ret 0`, `namei lk ok/rootdec/exit ok`, `km namei ret 0` -- and the
  trace reached `8560 v300 km mc call` (entering mount_common), heartbeat
  `hb 8560/8517 v300 km mc call`, with no `km mc ret`.  => frozen INSIDE
  mount_common() (vfs_syscalls.c:1011).  Prime suspect is the early
  `zalloc_flags(mount_zone, Z_WAITOK|Z_ZERO)` (line 1195): mount_zone is a
  KALLOC_TYPE_DEFINE kalloc zone that can sleep grabbing pages this early
  (same Z_WAITOK wall class as v291-v298).  Other suspects: prepare_coveredvp
  (1188), VFS_MOUNT -> devfs_mount (1603).

v303 (label-only diagnostic probes, no behavior change):
  vfs_syscalls.c mount_common(): entry, after prepare_coveredvp, after the
  mount_zone zalloc, before/after VFS_MOUNT.
    `v303 mc enter` / `v303 mc prep ok` / `v303 mc zalloc ok` /
    `v303 mc vfs call` / `v303 mc vfs ret<r>`.
  NOTE: no fix this round -- mount_zone has zfree() release paths, so a perm-
  pool allocation would double-free.  Localize first, then choose the fix
  (e.g. static preallocated mount_t, or Z_NOWAIT+retry) based on evidence.

Idempotent.  Run on the tree that already has v302 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v303.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

SYSCALL = os.path.join(WORK, "bsd/vfs/vfs_syscalls.c")
MARK = "g0245d v303"


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


s = read(SYSCALL)
if MARK in s:
    print("vfs_syscalls.c: already v303")
else:
    # 1) entry
    s = sub(
        s,
        """	struct proc *p = vfs_context_proc(ctx);
	int error, flag = 0;
	bool flag_set = false;""",
        """	struct proc *p = vfs_context_proc(ctx);
	int error, flag = 0;
	bool flag_set = false;
	""" + TRACE % "v303 mc enter" + """ """,
        "v303: mount_common entry",
    )
    # 2) after prepare_coveredvp (the error check right after it)
    s = sub(
        s,
        """	error = prepare_coveredvp(vp, ctx, cnp, fstypename, internal_flags);
	if (error != 0) {
		goto out1;
	}

	/*
	 * Allocate and initialize the filesystem (mount_t)
	 */
	mp = zalloc_flags(mount_zone, Z_WAITOK | Z_ZERO);
	mntalloc = 1;""",
        """	error = prepare_coveredvp(vp, ctx, cnp, fstypename, internal_flags);
	""" + TRACEU % ("v303 mc prep", "error") + """
	if (error != 0) {
		goto out1;
	}

	/*
	 * Allocate and initialize the filesystem (mount_t)
	 */
	mp = zalloc_flags(mount_zone, Z_WAITOK | Z_ZERO);
	""" + TRACE % "v303 mc zalloc ok" + """
	mntalloc = 1;""",
        "v303: prep + zalloc probes",
    )
    # 3) around VFS_MOUNT
    s = sub(
        s,
        """	} else {
		error = VFS_MOUNT(mp, device_vnode, fsmountargs, ctx);
	}

	if (flags & MNT_UPDATE) {""",
        """	} else {
		""" + TRACE % "v303 mc vfs call" + """
		error = VFS_MOUNT(mp, device_vnode, fsmountargs, ctx);
		""" + TRACEU % ("v303 mc vfs ret", "error") + """
	}

	if (flags & MNT_UPDATE) {""",
        "v303: VFS_MOUNT probes",
    )
    write(SYSCALL, s)
    print("vfs_syscalls.c: v303 mount_common probes installed")

print("v303 patch complete")
