#!/usr/bin/env python3
"""g0245d v389: print SP1 synchronous-exception diagnostics on the console
right before the panic.

The banner line ("Synchronous exception taken while SP1 selected at pc 0x...")
gets truncated by the screen edge, and the v369/v380 ring probes are never
redrawn once the exception fires (the ring snapshot is only drawn by the
periodic console refresh, which stops at the exception).  Panic output DOES
survive on screen (v381 proved this with "lret=2 @kern_exec.c:1336"), so put
the decisive values on the console as short lines instead.

Only touch: osfmk/arm64/sleh.c (sleh_synchronous_sp1).
Uses the global `int printf` from osfmk/kern/misc_protos.h (no local decl --
conflicting types) and get_saved_state_pc/lr accessors (arm_saved_state_t is
a union with no direct .pc/.lr members).
Idempotent, and repairs the first (broken) variant of the block.
"""
import os
import sys

XNU_WORK = os.environ["XNU_WORK"]
SLEH = os.path.join(XNU_WORK, "osfmk", "arm64", "sleh.c")

src = open(SLEH, encoding="utf-8").read()

GOOD = (
    "\t/* g0245d v389: the SP1 banner line is cut off by the screen edge and\n"
    "\t * the ring probes above are never redrawn once the exception fires,\n"
    "\t * so put the decisive values on the console directly; panic output\n"
    "\t * survives on screen (v381 proved it). */\n"
    '\tprintf("v389 ec=%02x esr=%08x\\n",\n'
    "\t       (unsigned)((esr >> 26) & 0x3fu), esr);\n"
    '\tprintf("v389 far=%016llx\\n", (unsigned long long)(uintptr_t)far);\n'
    '\tprintf("v389 pc=%016llx\\n", (unsigned long long)get_saved_state_pc(state));\n'
    '\tprintf("v389 lr=%016llx\\n", (unsigned long long)get_saved_state_lr(state));\n'
    "\n"
    "\tswitch (class) {\n"
)

if "v389 pc=%016llx\\n\", (unsigned long long)get_saved_state_pc" in src:
    print("patch_v389: sleh.c already patched (good variant), nothing to do")
    sys.exit(0)

# repair the first (broken) variant: local printf decl + direct .pc/.lr
BROKEN_ANCHOR = (
    "\t/* g0245d v389: the SP1 banner line is cut off by the screen edge and\n"
    "\t * the ring probes above are never redrawn once the exception fires,\n"
    "\t * so put the decisive values on the console directly; panic output\n"
    "\t * survives on screen (v381 proved it). */\n"
    "\t{ extern void printf(const char *, ...);\n"
    '\t  printf("v389 ec=%02x esr=%08x\\n",\n'
    "\t         (unsigned)((esr >> 26) & 0x3fu), esr);\n"
    '\t  printf("v389 far=%016llx\\n", (unsigned long long)(uintptr_t)far);\n'
    '\t  printf("v389 pc=%016llx\\n", (unsigned long long)state->pc);\n'
    '\t  printf("v389 lr=%016llx\\n", (unsigned long long)state->lr); }\n'
    "\n"
    "\tswitch (class) {\n"
)
if src.count(BROKEN_ANCHOR) == 1:
    src = src.replace(BROKEN_ANCHOR, GOOD, 1)
    open(SLEH, "w", encoding="utf-8").write(src)
    print("patch_v389: sleh.c broken v389 block repaired")
    sys.exit(0)

anchor = (
    '\t    g0245d_tracev("v380 sp1 ec", (unsigned long long)((esr >> 26) & 0x3fu));\n'
    "\t  } }\n"
    "\n"
    "\tswitch (class) {\n"
)
if src.count(anchor) != 1:
    sys.exit("patch_v389: sleh.c anchor found %d times" % src.count(anchor))

src = src.replace(anchor, GOOD, 1)
open(SLEH, "w", encoding="utf-8").write(src)
print("patch_v389: sleh.c SP1 console diagnostics inserted")
