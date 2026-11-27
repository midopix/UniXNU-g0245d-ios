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

Placement matters.  The block must sit at function scope, *after* the v380
bounded-budget probe has been closed.  An earlier revision replaced
"<tail of v380>\n  } }\n\n switch (class) {" wholesale, which swallowed the two
closing braces and nested the switch inside `if (v380_sp1 < 6) {`; clang then
reported "function definition is not allowed here" on every later function in
sleh.c (111 errors).  This version keeps the braces and only appends.

Idempotent: re-running detects the placed block, and if a previous broken
application left it unclosed, repairs the brace in front of it.
"""
import os
import sys

XNU_WORK = os.environ["XNU_WORK"]
SLEH = os.path.join(XNU_WORK, "osfmk", "arm64", "sleh.c")

src = open(SLEH, encoding="utf-8").read()

BODY = (
    "\t/* g0245d v389: the SP1 banner line is cut off by the screen edge and\n"
    "\t * the ring probes above are never redrawn once the exception fires,\n"
    "\t * so put the decisive values on the console directly; panic output\n"
    "\t * survives on screen (v381 proved it). */\n"
    '\tprintf("v389 ec=%02x esr=%08x\\n",\n'
    "\t       (unsigned)((esr >> 26) & 0x3fu), esr);\n"
    '\tprintf("v389 far=%016llx\\n", (unsigned long long)(uintptr_t)far);\n'
    '\tprintf("v389 pc=%016llx\\n", (unsigned long long)get_saved_state_pc(state));\n'
    '\tprintf("v389 lr=%016llx\\n", (unsigned long long)get_saved_state_lr(state));\n'
)

MARK = "v389 ec=%02x esr=%08x"

if MARK in src:
    if "\t  } }\n\t/* g0245d v389:" not in src:
        broken = "\t/* g0245d v389:"
        if src.count(broken) != 1:
            sys.exit("patch_v389: cannot locate the unclosed v389 block (%d)" % src.count(broken))
        src = src.replace(broken, "\t  } }\n" + broken, 1)
        open(SLEH, "w", encoding="utf-8").write(src)
        print("patch_v389: repaired the unclosed v380 block in front of v389")
        sys.exit(0)
    print("patch_v389: sleh.c already patched, nothing to do")
    sys.exit(0)

ANCHOR = "\t  } }\n\n\tswitch (class) {\n"
if src.count(ANCHOR) != 1:
    sys.exit("patch_v389: sleh.c anchor found %d times" % src.count(ANCHOR))

src = src.replace(ANCHOR, "\t  } }\n" + BODY + "\n\tswitch (class) {\n", 1)
open(SLEH, "w", encoding="utf-8").write(src)
print("patch_v389: sleh.c SP1 console diagnostics inserted")
