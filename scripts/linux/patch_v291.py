#!/usr/bin/env python3
"""g0245d v291 -- narrow the freeze between configure() and the memory disk.

Evidence (photo 2026-11-23 07:58, v290 flashed 07:57:05):
  seq 8469-8475 are the v288 dump#2 tail, ending at `v288 rearmed`;
  that is the LAST row of the ring, inside IOPlatformExpert::configure().
  NO `v289 memdisk` / `v289 rd md0` / `v281 fbr iobsd tmo` appears, so
  the boot never reached IOFindBSDRoot's memory-disk branch in the photo.
  rpr=255 / irqn=51 / setpopn=179 prove the GICv3 EOI fix still holds,
  so this is a NEW freeze, not the old interrupt regression.

v291 adds relay probes around the configure()->IOFindBSDRoot() handoff so
the NEXT photo can pin the exact gap.  It does NOT change any behavior:
no timing, no allocation, no root logic -- only g0245d_trace calls.

Expected ladder on the next photo (last visible row decides):
  v288 rearmed -> v291 cfg exit        : configure() returned; freeze is
                                         inside waitForMatchingService()
  ...        -> v291 wait done         : 3 s IOBSD wait returned (compare
                                         with v288, where `iobsd tmo` did)
  ...        -> v291 didram enter      : reached the memory-disk branch
  ...        -> v289 memdisk / rd md0  : allocation + mdevadd + rd=md0
  ...        -> load_init_program ...  : mockfs rooted, PID1 about to exec
  ...        -> panic ...42            : userland round-trip proven

If the photo still stops at `v288 rearmed` with NO `v291 cfg exit`, the
freeze is inside configure() AFTER the re-arm write (the WSC nub release),
not in the fbr path.

Run AFTER patch_v289.py (anchors assume the v290 source state):
    XNU_WORK=<xnu-work> python3 patch_v291.py
Idempotent: re-running is a no-op.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

IOPE = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")
BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")
MARK = "g0245d v291"


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


# --- relay 1: configure() just before return (dump#2 tail) ------------------
s = read(IOPE)
if MARK not in s:
    s = sub(
        s,
        """\tg0245d_trace("v288 rearmed");
\tOSSafeReleaseNULL(nub);
\treturn true;
}""",
        """\tg0245d_trace("v288 rearmed");
\t{ extern void g0245d_trace(const char *);
\t  g0245d_trace("v291 cfg exit"); }
\tOSSafeReleaseNULL(nub);
\treturn true;
}""",
        "configure: cfg exit",
    )
    write(IOPE, s)
    print("IOPlatformExpert.cpp: v291 cfg exit added")
else:
    print("IOPlatformExpert.cpp: already patched")

# --- relay 2: IOFindBSDRoot, right after the IOBSD 3 s wait ----------------
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """\t\t{ extern void g0245d_trace(const char *);
\t\t  g0245d_trace("v281 fbr iobsd tmo"); }
\t}
\tmatching->release();""",
        """\t\t{ extern void g0245d_trace(const char *);
\t\t  g0245d_trace("v281 fbr iobsd tmo"); }
\t}
\t{ extern void g0245d_trace(const char *);
\t  g0245d_trace("v291 wait done"); }
\tmatching->release();""",
        "fbr: wait done",
    )
    # --- relay 3: memory-disk branch entry (before kernel_memory_allocate) --
    s = sub(
        s,
        """\tif (!didRam) {
\t\tdidRam = 1;
\t\t/* g0245d v289: build a memory disk holding a minimal arm64""",
        """\tif (!didRam) {
\t\tdidRam = 1;
\t\t{ extern void g0245d_trace(const char *);
\t\t  g0245d_trace("v291 didram enter"); }
\t\t/* g0245d v289: build a memory disk holding a minimal arm64""",
        "fbr: didram enter",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: v291 wait done / didram enter added")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v291 done (probes only; no behavioral change)")
