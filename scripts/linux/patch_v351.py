#!/usr/bin/env python3
"""g0245d v351 -- fix the v331 scratch probe so the tree builds on every host.

The v331 probe printed the pmap of PID1's address space:

    g0245d_tracev("v331 pmap", (unsigned long long)(uintptr_t)map->pmap);

`map` is a `vm_map_t` (= `struct _vm_map *`).  In bsd/kern/kern_exec.c the
struct is only forward declared (osfmk/vm/vm_map.h keeps the definition for
kernel-internal use), so `map->pmap` does not compile:

    bsd/kern/kern_exec.c:8053:64: error: incomplete definition of type
    'struct _vm_map'

The same lesson is recorded in HANDOFF 14.15.4: pmap internals (ttep, hw_asid,
the ptrauth-signed `vm_map.pmap`) may only be touched inside
osfmk/arm/pmap/pmap.c -- comparing a ptrauth-signed pointer is not even legal
from bsd.

The probe is not needed for the v350 judgement (it looks at v349/v350 probes
only), so it is rewritten to print the map pointer itself, which is legal and
still tells us "which map we are in".  Hosts whose base tree already lacks
this line (the machine that built v350) are left untouched -- the patch is
idempotent and simply reports "already applied".
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

KERN_EXEC = os.path.join(WORK, "bsd/kern/kern_exec.c")

OLD = '\t\tg0245d_tracev("v331 pmap", (unsigned long long)(uintptr_t)map->pmap);\n'
NEW = ('\t\t/* g0245d v351: map->pmap is not reachable from bsd (the struct is\n'
       '\t\t * only forward declared here); print the map pointer instead. */\n'
       '\t\tg0245d_tracev("v331 map", (unsigned long long)(uintptr_t)map);\n')

MARK = "g0245d v351"


def main():
    with open(KERN_EXEC, encoding="utf-8") as f:
        s = f.read()

    if MARK in s:
        print("kern_exec.c: already patched")
        return

    n = s.count(OLD)
    if n == 0:
        print("kern_exec.c: the v331 pmap probe is not present on this tree "
              "(nothing to do)")
        return
    if n != 1:
        sys.exit("kern_exec.c: v331 pmap probe found %d times (expected 1)" % n)

    s = s.replace(OLD, NEW)
    with open(KERN_EXEC, "w", encoding="utf-8") as f:
        f.write(s)
    print("kern_exec.c: v331 pmap probe -> v331 map pointer (%s)" % MARK)


if __name__ == "__main__":
    main()
