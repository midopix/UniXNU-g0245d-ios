#!/usr/bin/env python3
"""g0245d v232: instrument PE_init_iokit(), and make panic output land on the
framebuffer console.

v231 finished the display work: the panel is now upright, row-aligned and shows
a pinned status row.  Its photo ended at:

    55 PE_init_iokit
    56 v230 early_random calls 0x800      (our own trace, direct to fb)
    57 v230 early_random calls 0x800

The stage names on that screen all come from g0245d_trace(), not from kprintf.
kernel_startup_log() would have printed "early_boot" as soon as PE_init_iokit()
returned and kernel_startup_initialize_upto(EARLY_BOOT) started (startup.c:716).
That line never appeared, so the machine is stuck *inside* PE_init_iokit() --
and PE_init_iokit() is also where the kernel first walks the device tree for
real (InitIOKit / ConfigureIOKit), which is exactly what a machine without an
arm-io node would trip over.

Two changes:

1. pexpert/arm/pe_init.c -- a trace ladder in PE_init_iokit(): enter, printf
   rearmed, device-tree pict done, images done, InitIOKit enter/done,
   ConfigureIOKit done.  The last label printed names the call that hung.

2. pexpert/arm/pe_kprintf.c -- PE_init_kprintf() runs a few lines after
   PE_init_iokit() returns and replaces PE_kputc with console_write_unbuffered,
   a back end we do not have (soc_base == 0 means no serial and no video
   console was ever registered).  Re-arm PE_kputc to the framebuffer console so
   that panic() -- which calls _doprnt(..., PE_kputc, ...) directly and ignores
   disable_kprintf_output -- becomes visible.  kprintf itself stays disabled, so
   the panel is not flooded.

Idempotent: every anchor is asserted unique and the marker 'v232' guards each
hunk.
"""

import os
import sys

BASE = os.environ.get(
    "XNU_WORK",
    os.path.expanduser("~/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66"
    "/g0245d/tree/.cache/xnu-work"),
)

PE_INIT = os.path.join(BASE, "pexpert/arm/pe_init.c")
PE_KPRINTF = os.path.join(BASE, "pexpert/arm/pe_kprintf.c")


def read(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)


def sub(text, old, new, what):
    n = text.count(old)
    if n != 1:
        sys.exit("anchor %s: expected 1 hit, got %d" % (what, n))
    return text.replace(old, new)


def once(text, marker, what):
    """Refuse to apply a hunk that is already in the file."""
    if marker in text:
        print("  skip %s (already applied)" % what)
        return False
    return True


# ---------------------------------------------------------------- pe_init.c

src = read(PE_INIT)

if once(src, "v232 PE_init_iokit enter", "pe_init: iokit ladder"):
    # File-scope declarations.  pe_init.c is C, so keep declarations at the top
    # of the function bodies that use them.
    src = sub(
        src,
        "/* g0245d v225: band probe from osfmk/arm/arm_init.c */\n",
        "/* g0245d v232: text checkpoints and the framebuffer console, both\n"
        " * exported from osfmk/arm/arm_init.c.  C89, so declare at file scope.\n"
        " */\n"
        "extern void g0245d_trace(const char *label);\n"
        "extern void g0245d_con_putc(char c);\n"
        "\n"
        "/* g0245d v225: band probe from osfmk/arm/arm_init.c */\n",
        "pe_init: extern decls")

    src = sub(
        src,
        "\tuint32_t        populate_registry_time_value = 0;\n"
        "\n"
        "\tPE_init_printf(TRUE);\n",
        "\tuint32_t        populate_registry_time_value = 0;\n"
        "\n"
        "\t/* g0245d v232: startup.c:706 logs this stage and then calls us;\n"
        "\t * startup.c:716 logs the next stage the moment we return.  Nothing\n"
        "\t * between the two ever appeared on the panel, so the hang is in\n"
        "\t * here.  One label per call, last label wins.\n"
        "\t */\n"
        "\tg0245d_trace(\"v232 PE_init_iokit enter\");\n"
        "\tPE_init_printf(TRUE);\n"
        "\tg0245d_trace(\"v232 iokit printf rearmed\");\n",
        "pe_init: iokit enter")

    src = sub(
        src,
        "\tpe_prepare_images();\n",
        "\tg0245d_trace(\"v232 iokit pict done\");\n"
        "\tpe_prepare_images();\n"
        "\tg0245d_trace(\"v232 iokit images done\");\n",
        "pe_init: pe_prepare_images")

    src = sub(
        src,
        "\tInitIOKit(PE_state.deviceTreeHead);\n"
        "\tConfigureIOKit();\n"
        "}\n",
        "\tg0245d_trace(\"v232 iokit progress done\");\n"
        "\tg0245d_trace(\"v232 InitIOKit enter\");\n"
        "\tInitIOKit(PE_state.deviceTreeHead);\n"
        "\tg0245d_trace(\"v232 InitIOKit done\");\n"
        "\tConfigureIOKit();\n"
        "\tg0245d_trace(\"v232 ConfigureIOKit done\");\n"
        "}\n",
        "pe_init: InitIOKit")

    write(PE_INIT, src)
    print("  patched pe_init.c")
else:
    src = ""

# ------------------------------------------------------------- pe_kprintf.c

src = read(PE_KPRINTF)

if once(src, "v232 kputc armed", "pe_kprintf: rearm"):
    src = sub(
        src,
        "static void serial_putc_crlf(char c);\n",
        "static void serial_putc_crlf(char c);\n"
        "\n"
        "/* g0245d v232: the framebuffer console from osfmk/arm/arm_init.c, and\n"
        " * its text checkpoint helper.\n"
        " */\n"
        "extern void g0245d_con_putc(char c);\n"
        "extern void g0245d_trace(const char *label);\n",
        "pe_kprintf: extern decls")

    src = sub(
        src,
        "\t\tPE_kputc = console_write_unbuffered;\n"
        "\t}\n"
        "}\n",
        "\t\tPE_kputc = console_write_unbuffered;\n"
        "\t}\n"
        "\n"
        "\t/* g0245d v232: on this machine serial_init() finds nothing (there is\n"
        "\t * no soc_base, so pe_serial never registers a driver) and no video\n"
        "\t * console was ever attached either, which makes\n"
        "\t * console_write_unbuffered a black hole.  Point kprintf at the\n"
        "\t * framebuffer console instead.  kprintf itself stays switched off by\n"
        "\t * disable_kprintf_output, so the panel is not flooded, but panic()\n"
        "\t * calls _doprnt(..., PE_kputc, ...) directly and therefore starts\n"
        "\t * talking to the panel from here on.\n"
        "\t */\n"
        "\tPE_kputc = g0245d_con_putc;\n"
        "\tg0245d_trace(\"v232 kputc armed\");\n"
        "}\n",
        "pe_kprintf: kputc rearm")

    write(PE_KPRINTF, src)
    print("  patched pe_kprintf.c")
else:
    src = ""

print("v232 ok")
