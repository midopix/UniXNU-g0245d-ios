#!/usr/bin/env python3
"""g0245d v313 -- bisect the copy step inside mdevstrategy's read path.

v312 verdict (photo 09:20), ring read out:
    8664 v295 mdev strat
    8665 v312 devid 0        devid valid
    8666 v312 count 4096     one page
    8667 v312 blkoff 0
    8668 v312 bufmap call
    8669 v312 bufmap ok      buf_map() succeeded
    8670 v312 mdflags <n>    (photo glare, digit unreadable)
    8671 v312 copy call      <- freeze happens here
hb307 8671/8628 v312 copy call

So it dies in the copy: either the virtual bcopy() (mdPhys clear, fvaddr used as
a KERNEL VIRTUAL address even though it is a physical page frame) or the
bcopy_phys() loop (mdPhys set, pmap_find_phys(vaddr) returns 0 -> panic that
cannot print).

v313 makes the branch explicit and prints pp (the pmap_find_phys result) right
before the panic test, so either failure mode becomes readable.

Idempotent.  Run on the tree that already has v312 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v313.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/dev/memdev.c")
MARK = "v313 read"


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
    print("memdev.c: already v313")
else:
    s = sub(
        s,
        "\tif (buf_flags(bp) & B_READ) {                                   /* Is this a read? */\n",
        "\tif (buf_flags(bp) & B_READ) {                                   /* Is this a read? */\n"
        "\t\t{ extern void g0245d_trace(const char *); g0245d_trace((mdev[devid].mdFlags & mdPhys) ? \"v313 read phys\" : \"v313 read virt\"); }\n",
        "v313: read branch label",
    )
    s = sub(
        s,
        "\t\t\t    (void *)vaddr, (size_t)buf_count(bp));      /* This is virtual, just get the data */\n",
        "\t\t\t    (void *)vaddr, (size_t)buf_count(bp));      /* This is virtual, just get the data */\n"
        "\t\t\t" + (T % "v313 virt copy done") + "\n",
        "v313: virtual bcopy done",
    )
    s = sub(
        s,
        "\t\t\t\tpp = pmap_find_phys(kernel_pmap, (addr64_t)((uintptr_t)vaddr)); /* Get the sink physical address */\n",
        "\t\t\t\tpp = pmap_find_phys(kernel_pmap, (addr64_t)((uintptr_t)vaddr)); /* Get the sink physical address */\n"
        "\t\t\t\t" + (TU % ("v313 pp", "pp")) + "\n",
        "v313: pp value",
    )
    s = sub(
        s,
        "\t\t\t\tbcopy_phys(fvaddr, paddr, csize);               /* Copy this on in */\n",
        "\t\t\t\tbcopy_phys(fvaddr, paddr, csize);               /* Copy this on in */\n"
        "\t\t\t\t" + (T % "v313 phys copied") + "\n",
        "v313: phys copy step",
    )
    s = sub(
        s,
        "\tbuf_unmap(bp);\n",
        "\t" + (T % "v313 unmap call") + "\n\tbuf_unmap(bp);\n",
        "v313: before buf_unmap",
    )
    write(F, s)
    print("memdev.c: v313 copy-path probes installed")

print("v313 patch complete")
