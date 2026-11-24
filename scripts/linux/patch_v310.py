#!/usr/bin/env python3
"""g0245d v310 -- bisect the tail of devfs_mount after dev_dup_plane returned.

v309 verdict (photo 09:06): the wall is broken.
    8570 v309 salt 2048622583     <- salt != 0, the assert was NOT the cause
    8571 v308 hash ok             <- bypassing VM_KERNEL_ADDRHASH unblocked it
    8572 v308 typenum ok
    8573 v308 flag ok
    8574 v305 dm assign
    8575 v305 pre lock            <- DEVFS_LOCK acquired fine
    8576 v305 post lock
    8577 v304 dm lock ok
    8578 v304 dm dup call
hb307 8579/8536 v304 dm dup ret   <- dev_dup_plane returned

So the SHA-256 inside vm_kernel_addrhash() was the real wall (most likely the
SHA256 instructions trap while FP/SIMD is still disabled this early), and the
mount now freezes between DEVFS_UNLOCK() and `v304 dm statfs ok`.

v310 probes the remaining statements and, for the first time, prints the actual
dev_dup_plane() return value (`v310 err <n>`), which decides between the
error-free branch and the kfree/return branch.

Idempotent.  Run on the tree that already has v309 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v310.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "v310 unlock ok"


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
TU = '{ extern void g0245d_trace_u(const char *, unsigned int); g0245d_trace_u("%s", (unsigned int)(%s)); }'

s = read(F)
if MARK in s:
    print("devfs_vfsops.c: already v310")
else:
    s = sub(
        s,
        "\tDEVFS_UNLOCK();\n\n\tif (error) {",
        "\tDEVFS_UNLOCK();\n\t" + (T % "v310 unlock ok") + "\n\n\tif (error) {",
        "v310: after DEVFS_UNLOCK",
    )
    s = sub(
        s,
        "\t} else {\n\t\tDEVFS_INCR_MOUNTS();\n\t}\n",
        "\t} else {\n\t\tDEVFS_INCR_MOUNTS();\n\t}\n\t" + (TU % ("v310 err", "error")) + "\n",
        "v310: after incr mounts",
    )
    s = sub(
        s,
        "\tbzero(mp->mnt_vfsstat.f_mntfromname, MAXPATHLEN);\n",
        "\tbzero(mp->mnt_vfsstat.f_mntfromname, MAXPATHLEN);\n\t" + (T % "v310 bzero ok") + "\n",
        "v310: after bzero",
    )
    s = sub(
        s,
        "\t(void)devfs_statfs(mp, &mp->mnt_vfsstat, ctx);\n",
        "\t" + (T % "v310 statfs call") + "\n\t(void)devfs_statfs(mp, &mp->mnt_vfsstat, ctx);\n",
        "v310: before devfs_statfs",
    )
    write(F, s)
    print("devfs_vfsops.c: v310 tail probes installed")

print("v310 patch complete")
