#!/usr/bin/env python3
"""v232 fix-up: the two extern declarations landed next to PE_create_console
(line 529), but PE_init_iokit() uses g0245d_trace() at line 261.  Move them to
the file-scope declaration block at the top instead.
"""

import os
import sys

PE_INIT = os.environ.get(
    "XNU_WORK",
    os.path.expanduser("~/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66"
    "/g0245d/tree/.cache/xnu-work"),
) + "/pexpert/arm/pe_init.c"

BLOCK = (
    "\n/* g0245d v232: text checkpoints and the framebuffer console, both\n"
    " * exported from osfmk/arm/arm_init.c.  C89, so declare at file scope.\n"
    " */\n"
    "extern void g0245d_trace(const char *label);\n"
    "extern void g0245d_con_putc(char c);\n"
)

src = open(PE_INIT, encoding="utf-8", errors="surrogateescape").read()

if BLOCK not in src:
    print("already moved")
    sys.exit(0)

if src.count(BLOCK) != 1:
    sys.exit("block not unique: %d" % src.count(BLOCK))
src = src.replace(BLOCK, "")

anchor = (
    "/* extern references */\n"
    "extern void     pe_identify_machine(boot_args *bootArgs);\n"
)
if src.count(anchor) != 1:
    sys.exit("anchor not unique: %d" % src.count(anchor))

new = (
    "/* extern references */\n"
    "extern void     pe_identify_machine(boot_args *bootArgs);\n"
    "\n"
    "/* g0245d v232: the framebuffer console and its text checkpoint helper,\n"
    " * both exported from osfmk/arm/arm_init.c.  PE_init_iokit() uses them, so\n"
    " * they have to be declared before it, not next to PE_create_console().\n"
    " */\n"
    "extern void     g0245d_trace(const char *label);\n"
    "extern void     g0245d_con_putc(char c);\n"
)
src = src.replace(anchor, new)

open(PE_INIT, "w", encoding="utf-8", errors="surrogateescape").write(src)
print("declarations moved to the top of pe_init.c")
