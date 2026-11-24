#!/usr/bin/env python3
"""g0245d v314 -- pin the last three statements of mdevstrategy.

v313 verdict (photo 09:25), ring read out:
    8667 v312 devid 0
    8668 v312 count 4096
    8669 v312 blkoff 0
    8671 v312 bufmap ok
    8672 v312 mdflags 1      <- mdInited only, mdPhys CLEAR
    8673 v312 copy call
    8674 v313 read virt      <- virtual path
    8675 v313 virt copy done <- bcopy() SUCCEEDED
hb307 8676/8633 v313 unmap call

So the copy is fine (fvaddr happened to be readable as a virtual address), and
the freeze is after `v313 unmap call`:

    buf_unmap(bp);            -> buf_unmap_range_internal(): !B_CLUSTER => return 0
    buf_setresid(bp, 0);      -> inline store
    buf_biodone(bp);          -> iodone chain: wakes waiters, buffer bookkeeping

Since the buffer is not a cluster (buf_map took the b_datap branch), buf_unmap
cannot block; the suspect is buf_biodone(), whose wakeup path needs the thread /
wait-queue machinery that mockfs brings up very early.

v314 brackets all three so the next photo names the exact one.

Idempotent.  Run on the tree that already has v313 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v314.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/dev/memdev.c")
MARK = "v314 unmap ok"


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
    print("memdev.c: already v314")
else:
    s = sub(
        s,
        "\tbuf_unmap(bp);\n\n\tbuf_setresid(bp, 0);",
        "\tbuf_unmap(bp);\n\t" + (T % "v314 unmap ok") + "\n\n\tbuf_setresid(bp, 0);",
        "v314: after buf_unmap",
    )
    s = sub(
        s,
        "\tbuf_biodone(bp);                                                                        /* Say we've finished */",
        "\t" + (T % "v314 resid ok") + "\n"
        "\t" + (T % "v314 biodone call") + "\n"
        "\tbuf_biodone(bp);                                                                        /* Say we've finished */\n"
        "\t" + (T % "v314 biodone ok"),
        "v314: around buf_biodone",
    )
    write(F, s)
    print("memdev.c: v314 tail probes installed")

print("v314 patch complete")
