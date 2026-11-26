#!/usr/bin/env python3
"""One-off repair for patch_v387's IOService.cpp placement bug."""
import sys
from pathlib import Path

F = Path("/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work/iokit/Kernel/IOService.cpp")
src = F.read_text(encoding="utf-8")

BAD = '''bool
/* g0245d v387: IOKit matching stop-location counters (C linkage so
 * bsd/kern/bsd_init.c can read them for the pinned boot row). */
extern "C" {
volatile unsigned int g0245d_io_d = 0; /* startDict candidate fetch */
volatile unsigned int g0245d_io_c = 0; /* startCandidate entered */
volatile unsigned int g0245d_io_a = 0; /* attach ok in startCandidate */
volatile unsigned int g0245d_io_s = 0; /* reached service->start */
}

IOService::startCandidate( IOService * service )
'''
GOOD = '''bool
IOService::startCandidate( IOService * service )
'''
if src.count(BAD) == 1:
    src = src.replace(BAD, GOOD, 1)
    print("repair: startCandidate header restored")
elif "g0245d v387" not in src:
    sys.exit("repair: v387 markers absent -- nothing to do")
elif src.count(GOOD) == 1:
    print("repair: header already restored -- skip")
else:
    sys.exit("repair: unexpected IOService.cpp state")

GLOBALS = '''/* g0245d v387: IOKit matching stop-location counters (C linkage so
 * bsd/kern/bsd_init.c can read them for the pinned boot row). */
extern "C" {
volatile unsigned int g0245d_io_d = 0; /* startDict candidate fetch */
volatile unsigned int g0245d_io_c = 0; /* startCandidate entered */
volatile unsigned int g0245d_io_a = 0; /* attach ok in startCandidate */
volatile unsigned int g0245d_io_s = 0; /* reached service->start */
}

/*
 * Alloc and probe matching classes,
 * called on the provider instance
 */

void
IOService::probeCandidates( OSOrderedSet * matches )
'''
ANCHOR = '''/*
 * Alloc and probe matching classes,
 * called on the provider instance
 */

void
IOService::probeCandidates( OSOrderedSet * matches )
'''
n = src.count(ANCHOR)
if n != 1:
    sys.exit("repair: probeCandidates anchor found %d times" % n)
src = src.replace(ANCHOR, GLOBALS, 1)
F.write_text(src, encoding="utf-8")
print("repair: globals moved above probeCandidates -- done")
