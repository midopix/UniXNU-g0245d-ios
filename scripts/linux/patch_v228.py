#!/usr/bin/env python3
"""v228: read the trace instead of guessing at it, and follow arm_init out.

v227 proved three things at once: PE_create_console() runs to completion, our
sink is acceptable to kprintf, and dump_kva_space() prints.  Then the screen
goes quiet.  The code after that point is, in order:

    dump_kva_space()            (DEBUG only)
    cpu_machine_idle_init(TRUE)
    PE_init_platform(TRUE, &BootCpuData)
    ml_map_cpu_pio()
    cpu_timebase_init(TRUE)
    PE_init_cpu(); fiq_context_init(TRUE)
    SecureDTLookupEntry("/chosen") / dram-base / dram-size

Every one of those can plausibly be the stop, and two of them
(PE_init_platform(TRUE) and cpu_timebase_init) are exactly where the G0345D
port reported timebase=0 with quotient=0 and index=0xffffffff.  So this
version adds one checkpoint per call, at rows below the text region.

It also stops the colour ladder from eating the log.  Bands live at rows
620..1760 and the console owns rows 0..1140, so every band drawn after the
console came up erased up to eight rows of text underneath it -- which is why
v227's photo looks like two interleaved blocks.  Once the console is ready,
bands inside its rows are dropped; the ladder still paints below 1140 and in
every phase before the console exists.
"""
import sys
from pathlib import Path

XNU = Path('$HOME/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work')
ARM = XNU / 'osfmk/arm/arm_init.c'


def sub1(text, old, new, what):
    if new.strip().split('\n')[0] in text and old not in text:
        print('  skip (already applied): %s' % what)
        return text
    if old not in text:
        sys.exit('anchor missing: %s' % what)
    if text.count(old) != 1:
        sys.exit('anchor not unique (%d): %s' % (text.count(old), what))
    print('  patch: %s' % what)
    return text.replace(old, new, 1)


def main():
    src = ARM.read_text()

    # 1. A flag the band painter can consult before it overwrites text.
    src = sub1(
        src,
        "extern boolean_t g0245d_kva_live;\n"
        "extern vm_offset_t g0245d_fb_kva(vm_offset_t pa);\n",
        "extern boolean_t g0245d_kva_live;\n"
        "extern vm_offset_t g0245d_fb_kva(vm_offset_t pa);\n"
        "\n"
        "/* g0245d v228: set once the text console owns rows 0..G0245D_CON_TOP. */\n"
        "unsigned int g0245d_con_owns_text;\n",
        'owns-text flag')

    # 2. Bands must not paint over the log they are meant to corroborate.
    src = sub1(
        src,
        "\tif (fb == 0 || rowbytes == 0) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\n"
        "\t/* g0245d v221: past the TTBR switch",
        "\tif (fb == 0 || rowbytes == 0) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\n"
        "\t/* g0245d v228: the console owns rows 0..G0245D_CON_TOP.  A band\n"
        "\t * drawn there after the console is up would erase up to eight rows\n"
        "\t * of text that is now the better evidence.  The ladder survives\n"
        "\t * below G0245D_CON_TOP and in every pre-console phase.\n"
        "\t */\n"
        "\tif (g0245d_con_owns_text && row < 1140) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\n"
        "\t/* g0245d v221: past the TTBR switch",
        'band/text guard')

    # 3. Raise the flag when the console is ready.
    src = sub1(
        src,
        "\tg0245d_con_ready = 1;\n",
        "\tg0245d_con_ready = 1;\n"
        "\tg0245d_con_owns_text = 1;\n",
        'raise owns-text')

    # 4. One checkpoint per call on the way out of arm_init.
    src = sub1(
        src,
        "\tcpu_machine_idle_init(TRUE);\n",
        "\tg0245d_mark(args, 1780, 0x00, 0xA0, 0xFF, \"after dump_kva_space\");\n"
        "\tcpu_machine_idle_init(TRUE);\n"
        "\tg0245d_mark(args, 1800, 0x60, 0x00, 0xFF, \"cpu_machine_idle_init returned\");\n",
        'idle-init marks')

    src = sub1(
        src,
        "\tPE_init_platform(TRUE, &BootCpuData);\n",
        "\tPE_init_platform(TRUE, &BootCpuData);\n"
        "\tg0245d_mark(args, 1820, 0xFF, 0x40, 0x00, \"PE_init_platform(TRUE) returned\");\n",
        'PE_init_platform(TRUE) mark')

    src = sub1(
        src,
        "\tml_map_cpu_pio();\n#endif\n",
        "\tml_map_cpu_pio();\n"
        "\tg0245d_mark(args, 1840, 0x00, 0xC0, 0x40, \"ml_map_cpu_pio returned\");\n"
        "#endif\n",
        'cpu-pio mark')

    src = sub1(
        src,
        "\tcpu_timebase_init(TRUE);\n",
        "\tcpu_timebase_init(TRUE);\n"
        "\tg0245d_mark(args, 1860, 0xFF, 0xD0, 0x00, \"cpu_timebase_init returned\");\n",
        'timebase mark')

    src = sub1(
        src,
        "\tPE_init_cpu();\n\tfiq_context_init(TRUE);\n",
        "\tPE_init_cpu();\n\tfiq_context_init(TRUE);\n"
        "\tg0245d_mark(args, 1880, 0xFF, 0x00, 0xC0, \"PE_init_cpu/fiq returned\");\n",
        'cpu/fiq mark')

    src = sub1(
        src,
        "\tgDramSize = *dram_size;\n",
        "\tgDramSize = *dram_size;\n"
        "\tg0245d_mark(args, 1900, 0x00, 0xFF, 0xFF, \"chosen dram-base/size done\");\n",
        'chosen-dram mark')

    ARM.write_text(src)
    print('wrote %s' % ARM)


if __name__ == '__main__':
    main()
