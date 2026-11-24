#!/usr/bin/env python3
"""g0245d v312 -- bisect mdevstrategy (the memory-disk read path).

v311 verdict (photo 09:15): devfs_mount is DONE -- the trace ran from 8583 all
the way to 8657, i.e. +74 lines, through statfs and past it.  The new freeze is
`v295 mdev strat` in bsd/dev/memdev.c:266, the first line of mdevstrategy().

mdevstrategy() is the raw-memory block device read path used by mockfs.  After
the probe it does:
    devid = minor(buf_device(bp));
    if (!(mdev[devid].mdFlags & mdInited)) { ENXIO; biodone; return; }
    buf_setresid(bp, buf_count(bp));
    blkoff = buf_blkno(bp) * mdev[devid].mdSecsize;
    ... bounds trims ...
    if (buf_map(bp, &vaddr)) panic("ramstrategy: buf_map failed");
    fvaddr = (mdev[devid].mdBase << 12) + blkoff;
    if B_READ: bcopy() or the bcopy_phys() loop (pmap_find_phys -> panic)

Both panics are silent on this path, so v312 prints the inputs (devid, count,
blkoff) and brackets buf_map + the copy, which pins the failing step even if it
dies inside a panic.

Idempotent.  Run on the tree that already has v311 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v312.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/dev/memdev.c")
MARK = "v312 devid"


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


TU = '{ extern void g0245d_trace_u(const char *, unsigned int); g0245d_trace_u("%s", (unsigned int)(%s)); }'
T = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'

s = read(F)
if MARK in s:
    print("memdev.c: already v312")
else:
    s = sub(
        s,
        "\tdevid = minor(buf_device(bp));",
        "\tdevid = minor(buf_device(bp));\n\t" + (TU % ("v312 devid", "devid")),
        "v312: devid",
    )
    s = sub(
        s,
        "\tif (buf_map(bp, (caddr_t *)&vaddr)) {",
        "\t" + (TU % ("v312 count", "buf_count(bp)"))
        + "\n\t" + (TU % ("v312 blkoff", "blkoff"))
        + "\n\t" + (T % "v312 bufmap call")
        + "\n\tif (buf_map(bp, (caddr_t *)&vaddr)) {",
        "v312: before buf_map",
    )
    s = sub(
        s,
        "\tfvaddr = (mdev[devid].mdBase << 12) + blkoff;",
        "\t" + (T % "v312 bufmap ok")
        + "\n\t" + (TU % ("v312 mdflags", "mdev[devid].mdFlags"))
        + "\n\tfvaddr = (mdev[devid].mdBase << 12) + blkoff;",
        "v312: after buf_map",
    )
    s = sub(
        s,
        "\tif (buf_flags(bp) & B_READ) {",
        "\t" + (T % "v312 copy call")
        + "\n\tif (buf_flags(bp) & B_READ) {",
        "v312: before copy",
    )
    write(F, s)
    print("memdev.c: v312 mdevstrategy probes installed")

print("v312 patch complete")
