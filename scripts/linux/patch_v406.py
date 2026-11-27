#!/usr/bin/env python3
"""g0245d v406: give the v405b diagnostics their own pinned line.

v405 photo (home rebuild, identical to the company run): row A prints
"27 v405 o=0 t=36 r=f6 d=40 a=0000 ss=000102 pm=11 s=9 i=05" but the
v405b init row NEVER reaches the panel.  Root cause: g0245d_probe()
(v233) pins EVERY call to the same screen row (con_rows - 3), so the
v405b probe call is overwritten by the row-A probe call three lines
later -- on every machine, every cycle.

v406 adds g0245d_probe2() pinning one row higher (con_rows - 4) and
switches the v405b print to it.  No driver changes; only boot is flashed.
"""
import os
import sys
from pathlib import Path

W = Path(os.environ["XNU_WORK"])
ARM = W / "osfmk" / "arm" / "arm_init.c"
BSD = W / "bsd" / "kern" / "bsd_init.c"
for f in (ARM, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------ arm_init.c
src = ARM.read_text(encoding="utf-8")
if "g0245d_probe2" in src:
    print("patch_v406: arm_init probe2 already present -- skip")
else:
    anchor = (
        "\n/* g0245d v236: the trace sequence, so the pinned row can say at which\n"
    )
    n = src.count(anchor)
    if n != 1:
        sys.exit("patch_v406: v236 comment anchor found %d times" % n)
    probe2 = (
        "/* g0245d v406: second pinned line, one row above the v233 probe row.\n"
        " * The v405b init diagnostics (set/fl/n/pmb/idn) printed through\n"
        " * g0245d_probe were overwritten by the row-A probe three lines later\n"
        " * -- both calls pin to con_rows - 3.  This variant pins one row\n"
        " * higher so both rows survive the 3 s refresh cycle.\n"
        " */\n"
        "void\n"
        "g0245d_probe2(const char *label)\n"
        "{\n"
        "\tunsigned int   row;\n"
        "\tunsigned int   col;\n"
        "\tunsigned int   i;\n"
        "\n"
        "\tstatic const char volatile v406_tag[] = \"v406 probe2 pinned row\";\n"
        "\tif (v406_tag[0] == 0) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\tif (!g0245d_con_ready || g0245d_con_rows < 5 || label == 0) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\trow = g0245d_con_row;\n"
        "\tcol = g0245d_con_col;\n"
        "\tg0245d_con_row = g0245d_con_rows - 4;\n"
        "\tg0245d_con_col = 0;\n"
        "\tg0245d_con_fill_row(g0245d_con_row);\n"
        "\tg0245d_con_putu((unsigned long)++g0245d_probe_seq, 10, 0);\n"
        "\tg0245d_con_putc(' ');\n"
        "\tfor (i = 0; label[i] != '\\0' && i + 5 < g0245d_con_cols; i++) {\n"
        "\t\tg0245d_con_putc(label[i]);\n"
        "\t}\n"
        "\tg0245d_con_row = row;\n"
        "\tg0245d_con_col = col;\n"
        "\tg0245d_con_sync();\n"
        "}\n"
        "\n"
        "/* g0245d v236: the trace sequence, so the pinned row can say at which\n"
    )
    src = src.replace(anchor, probe2, 1)
    ARM.write_text(src, encoding="utf-8")
    print("patch_v406: g0245d_probe2 installed (pins con_rows - 4)")

# ------------------------------------------------------------ bsd_init.c
bs = BSD.read_text(encoding="utf-8")
old_call = (
    "\t\t\t{ extern void g0245d_probe(const char *);\n"
    "\t\t\t  g0245d_probe(v405b_buf); }\n"
)
new_call = (
    "\t\t\t{ extern void g0245d_probe2(const char *);\n"
    "\t\t\t  g0245d_probe2(v405b_buf); }\n"
)
if "g0245d_probe2(v405b_buf)" in bs:
    print("patch_v406: bsdinit row-b already on probe2 -- skip")
else:
    n = bs.count(old_call)
    if n != 1:
        sys.exit("patch_v406: v405b probe call anchor found %d times" % n)
    bs = bs.replace(old_call, new_call, 1)
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v406: v405b row switched to g0245d_probe2")

print("patch_v406: done")
