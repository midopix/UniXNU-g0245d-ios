#!/usr/bin/env python3
"""g0245d v315 -- bisect mount_common after VFS_MOUNT returned.

v314 verdict (photo 09:31): mdevstrategy finished cleanly --
    8681 v313 unmap call / 8682 v314 unmap ok / 8683 v314 resid ok
    8684 v314 biodone call / 8685 v314 biodone ok
i.e. the memory-disk read path works end to end.  But nothing after it printed:
no `v300 km mc ret`, no `v300 dkm km ret`, no `v300 post devfs`.

So the freeze is inside mount_common() between VFS_MOUNT (which called
devfs_mount, already proven complete) and its return.  That stretch is:

    vnode_lock_spin / vp->v_mountedhere = mp / vnode_unlock
    name_cache_lock / mount_generation++ / name_cache_unlock
    vnode_ref(vp)
    checkdirs(vp, ctx)
    (void)VFS_START(mp, 0, ctx)
    mount_list_add(mp)
    lck_rw_done(&mp->mnt_rwlock)
    VFSATTR_INIT / VFS_GETATTR(...)

v315 brackets the four most suspicious: after v_mountedhere, after
name_cache_unlock, after checkdirs, after VFS_START, and after mount_list_add.

Idempotent.  Run on the tree that already has v314 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v315.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/vfs/vfs_syscalls.c")
MARK = "v315 mountedhere"


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


T = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'

s = read(F)
if MARK in s:
    print("vfs_syscalls.c: already v315")
else:
    s = sub(
        s,
        "\t\tvp->v_mountedhere = mp;\n\t\tvnode_unlock(vp);\n",
        "\t\tvp->v_mountedhere = mp;\n\t\tvnode_unlock(vp);\n\t\t" + (T % "v315 mountedhere") + "\n",
        "v315: after v_mountedhere",
    )
    s = sub(
        s,
        "\t\tname_cache_lock();\n\t\tmount_generation++;\n\t\tname_cache_unlock();\n",
        "\t\tname_cache_lock();\n\t\tmount_generation++;\n\t\tname_cache_unlock();\n\t\t" + (T % "v315 ncgen ok") + "\n",
        "v315: after name_cache",
    )
    s = sub(
        s,
        "\t\terror = checkdirs(vp, ctx);\n",
        "\t\t" + (T % "v315 checkdirs call") + "\n\t\terror = checkdirs(vp, ctx);\n",
        "v315: before checkdirs",
    )
    s = sub(
        s,
        "\t\t(void)VFS_START(mp, 0, ctx);\n",
        "\t\t" + (T % "v315 checkdirs ok") + "\n\t\t(void)VFS_START(mp, 0, ctx);\n\t\t" + (T % "v315 vfsstart ok") + "\n",
        "v315: around VFS_START",
    )
    s = sub(
        s,
        "\t\tif (mount_list_add(mp) != 0) {\n",
        "\t\t" + (T % "v315 mlist call") + "\n\t\tif (mount_list_add(mp) != 0) {\n",
        "v315: before mount_list_add",
    )
    write(F, s)
    print("vfs_syscalls.c: v315 mount_common tail probes installed")

print("v315 patch complete")
