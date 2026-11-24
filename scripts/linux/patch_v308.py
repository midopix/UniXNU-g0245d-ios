#!/usr/bin/env python3
"""g0245d v308 -- bisect the last 5 statements before DEVFS_LOCK in devfs_mount.

v307 verdict (photo 08:56): heartbeat showed `hb307 8567/8524 v304 dm kalloc ok`.
The new kernel IS running; the freeze is real and sits between
  devfs_vfsops.c:196  g0245d_trace("v304 dm kalloc ok")
and
  devfs_vfsops.c:206  g0245d_trace("v305 dm assign")
i.e. inside these five statements:
  devfs_mp_p->mount = mp;
  mp->mnt_data = (qaddr_t)devfs_mp_p;
  mp->mnt_vfsstat.f_fsid.val[0] = VM_KERNEL_ADDRHASH(devfs_mp_p);
  mp->mnt_vfsstat.f_fsid.val[1] = vfs_typenum(mp);   <-- function call
  mp->mnt_flag |= MNT_LOCAL;

v308 inserts one label after each, so a single boot pinpoints the statement.
Idempotent.  Run on the tree that already has v307 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v308.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "v308 mount set"
TR = "{ extern void g0245d_trace(const char *); g0245d_trace(\"%s\"); }"


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


s = read(F)
if MARK in s:
    print("devfs_vfsops.c: already v308")
else:
    s = sub(
        s,
        "\tdevfs_mp_p->mount = mp;\n",
        "\tdevfs_mp_p->mount = mp;\n\t" + (TR % "v308 mount set") + "\n",
        "v308: after mount field",
    )
    s = sub(
        s,
        "\t__IGNORE_WCASTALIGN(mp->mnt_data = (qaddr_t)devfs_mp_p);\n",
        "\t__IGNORE_WCASTALIGN(mp->mnt_data = (qaddr_t)devfs_mp_p);\n\t" + (TR % "v308 mnt_data ok") + "\n",
        "v308: after mnt_data",
    )
    s = sub(
        s,
        "\tmp->mnt_vfsstat.f_fsid.val[0] = (int32_t)VM_KERNEL_ADDRHASH(devfs_mp_p);\n",
        "\tmp->mnt_vfsstat.f_fsid.val[0] = (int32_t)VM_KERNEL_ADDRHASH(devfs_mp_p);\n\t" + (TR % "v308 hash ok") + "\n",
        "v308: after addr hash",
    )
    s = sub(
        s,
        "\tmp->mnt_vfsstat.f_fsid.val[1] = vfs_typenum(mp);\n",
        "\tmp->mnt_vfsstat.f_fsid.val[1] = vfs_typenum(mp);\n\t" + (TR % "v308 typenum ok") + "\n",
        "v308: after vfs_typenum",
    )
    s = sub(
        s,
        "\tmp->mnt_flag |= MNT_LOCAL;\n",
        "\tmp->mnt_flag |= MNT_LOCAL;\n\t" + (TR % "v308 flag ok") + "\n",
        "v308: after MNT_LOCAL",
    )
    write(F, s)
    print("devfs_vfsops.c: v308 5-step bisect probes installed")

print("v308 patch complete")
