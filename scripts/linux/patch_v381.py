#!/usr/bin/env python3
"""g0245d v381 -- surface load_machfile()'s return value for the real launchd.

v380 photo (2026-11-26 14:13) ring 9258-9270:

    9258 v357 s9 0xfffffff007adf1f8
    9259 v356 post ...            9261 v371 ttep 0x97146000
    9262 v371 asid 0x1            9263 v356 pre 0xffffffff35e197b00
    9264-9267 v357 s1/s2/s3/s9    9268 v356 post 0xffffffff35e197b00
    9269 v378 pm1 _exec.c:1332
    9270 v378 pm2
    hb307 9256/9212 v356 pre ... > v363 post

decode: the v378 panic split wrote `v378 pm1` = chars 24.. of the message, and
"_exec.c:1332" is exactly chars 24.. of

    "g0245d v338 lret=N @kern_exec.c:1332"      (panic() appends " @%s:%d")

so the panic came from our own v338 probe at bsd/kern/kern_exec.c:1332:

    lret = load_machfile(...);
    g0245d_trace_u("v333 lret", lret);
    if (lret != LOAD_SUCCESS) panic("g0245d v338 lret=%d", lret);

Meaning: exec of the real launchd got past path resolution, past cs_blob
(v379's amfi guard held), and died inside load_machfile().  `pm0` -- the line
that carries the numeric value -- was lost to a console scroll/redraw in this
photo, so N is still unknown.

ONE嫌疑点: make the value legible.  The message becomes "v381 lret=%d", i.e.
30 chars, so v378's first 24-char segment is "v381 lret=N @kern_exec.c" and the
number is at offset 10 of pm0.  A v381 lret trace_u is added as a second copy.

lv values (bsd/kern/mach_loader.h): 1 BADARCH, 2 BADMACHO, 3 SHLIB,
4 FAILURE, 5 NOSPACE, 6 PROTECT, 7 RESOURCE, 8 ENOENT (dyld not found),
9 IOERROR, 10 DECRYPTFAIL, 11 BADMACHO_UPX.

CUMULATIVE + IDEMPOTENT over v380.  Only bsd/kern/kern_exec.c is touched.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "bsd/kern/kern_exec.c")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v381 lret=" in src:
    print("patch_v381: already applied -- skip")
    sys.exit(0)

old = ('\tif (lret != LOAD_SUCCESS) {\n'
       '\t\tpanic("g0245d v338 lret=%d", (int)lret);\n'
       '\t}\n')
new = ('\tif (lret != LOAD_SUCCESS) {\n'
       '\t\t/* g0245d v381: keep the value inside the first v378 segment\n'
       '\t\t * (24 chars), so pm0 reads "v381 lret=N @kern_exec.c". */\n'
       '\t\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
       '\t\t  g0245d_trace_u("v381 lret", (unsigned int)lret); }\n'
       '\t\tpanic("v381 lret=%d", (int)lret);\n'
       '\t}\n')
n = src.count(old)
if n != 1:
    sys.exit("patch_v381: anchor count=%d (want 1)" % n)
src = src.replace(old, new, 1)
open(PATH, "w", encoding="utf-8").write(src)
print("patch_v381: load_machfile failure now panics with the value first")
