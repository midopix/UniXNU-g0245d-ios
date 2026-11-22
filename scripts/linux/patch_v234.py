#!/usr/bin/env python3
"""g0245d v234: name the static constructor that OSlibrkernInit() dies in.

v233's photo reads in order (the wrap-clearing works):

    39 clock_init ... 55 sysctl
    56 PE_init_iokit      57 v232 PE_init_iokit enter
    58 v232 iokit printf rearmed   59 pict done   60 images done
    61 progress done      62 v232 InitIOKit enter
    63 v233 IOLibInit enter        64 v233 IOLibInit done
    65 v233 OSlibrkernInit enter   66 v230 early_random calls 0x800
    ABCDEFGH... ruler
    >v233 OSlibrkernInit

So IOLibInit() is fine and the machine stops inside OSlibrkernInit()
(libkern/c++/OSRuntime.cpp:131), which is three lines:

    OSMetaClassBase::initialize();
    g_kernel_kmod_info.address = (vm_address_t) &_mh_execute_header;
    OSRuntimeInitializeCPP(NULL);      <-- runs every kernel static ctor

OSRuntimeInitializeCPP(NULL) walks every LC_SEGMENT_64 of the kernel and calls
each pointer in __mod_init_func.  That list is fixed and known:

    0..17   libkern/c++: OSDebug, OSMetaClass, OSObject, OSArray, ... OSSymbol
    18..28  iig-generated IOKit classes (OSAction .. IOWorkGroup)
    29..90  IOKit core (IORegistryEntry, IOService, power, workloop, memory ...)
    91..95  IOPMrootDomain, ArmDTPlatform, ArmCpu, NativeAES
    96..97  _last_kernel_constructor, bootstrap.cpp

so a probe that prints the index of the structor about to be called names the
one that hung, without a symbol table on the device.

Changes:

1. osfmk/arm/arm_init.c -- g0245d_probe_pc(): the pinned probe row prints
   "<index> 0x<16 hex digits>" for the address about to be called.

2. libkern/c++/OSRuntime.cpp -- traces in OSlibrkernInit() around
   OSRuntimeInitializeCPP(), a trace at each structor section, and the probe
   immediately before (*structor)().

Idempotent: anchors asserted unique, 'v234' markers on every hunk.
"""

import os
import sys

BASE = os.environ.get(
    "XNU_WORK",
    os.path.expanduser("~/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66"
    "/g0245d/tree/.cache/xnu-work"),
)

ARM_INIT = os.path.join(BASE, "osfmk/arm/arm_init.c")
OSRT = os.path.join(BASE, "libkern/c++/OSRuntime.cpp")


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
    if marker in text:
        print("  skip %s (already applied)" % what)
        return False
    return True


# ------------------------------------------------------------ arm_init.c

src = read(ARM_INIT)

if once(src, "g0245d_probe_pc(uintptr_t pc", "arm_init: probe_pc"):
    src = sub(
        src,
        "static unsigned int g0245d_trace_seq;\n",
        "/* g0245d v234: the same pinned row, for a raw address.  Printed as\n"
        " * <index> 0x<16 hex digits> so a photo of the panel can be matched\n"
        " * against the kernel's __mod_init_func table without symbols.\n"
        " */\n"
        "void\n"
        "g0245d_probe_pc(uintptr_t pc, unsigned int idx)\n"
        "{\n"
        "\tunsigned int   row;\n"
        "\tunsigned int   col;\n"
        "\tunsigned int   i;\n"
        "\tunsigned int   d;\n"
        "\n"
        "\tif (!g0245d_con_ready || g0245d_con_rows < 4) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\trow = g0245d_con_row;\n"
        "\tcol = g0245d_con_col;\n"
        "\tg0245d_con_row = g0245d_con_rows - 3;\n"
        "\tg0245d_con_col = 0;\n"
        "\tg0245d_con_fill_row(g0245d_con_row);\n"
        "\tg0245d_con_putu((unsigned long)idx, 10, 0);\n"
        "\tg0245d_con_putc(' ');\n"
        "\tg0245d_con_putu((unsigned long)(pc >> 48), 16, 0);\n"
        "\tfor (i = 0; i < 12; i++) {\n"
        "\t\td = (unsigned int)((pc >> (44 - 4 * i)) & 0xf);\n"
        "\t\tg0245d_con_putc((char)(d < 10 ? '0' + d : 'a' + d - 10));\n"
        "\t}\n"
        "\tg0245d_con_row = row;\n"
        "\tg0245d_con_col = col;\n"
        "\tg0245d_con_sync();\n"
        "}\n"
        "\n"
        "static unsigned int g0245d_trace_seq;\n",
        "arm_init: probe_pc body")

    write(ARM_INIT, src)
    print("  patched arm_init.c")
else:
    src = ""

# ------------------------------------------------------------ OSRuntime.cpp

src = read(OSRT)

if once(src, "v234 libkern init enter", "OSRuntime: ladder"):
    src = sub(
        src,
        "#include <sys/cdefs.h>\n"
        "#if defined(HAS_APPLE_PAC)\n",
        "#include <sys/cdefs.h>\n"
        "\n"
        "/* g0245d v234: framebuffer console probes, from osfmk/arm/arm_init.c.\n"
        " * g0245d_probe_pc() writes <index> 0x<addr> on the pinned row.\n"
        " * Declared outside the HAS_APPLE_PAC block below on purpose: that\n"
        " * block is compiled out on this target, which is exactly how the\n"
        " * first attempt at this patch failed to build.\n"
        " */\n"
        'extern "C" void g0245d_trace(const char *label);\n'
        'extern "C" void g0245d_probe_pc(uintptr_t pc, unsigned int idx);\n'
        "\n"
        "#if defined(HAS_APPLE_PAC)\n",
        "OSRuntime: extern decls")

    src = sub(
        src,
        "\t// This must be called before calling OSRuntimeInitializeCPP.\n"
        "\tOSMetaClassBase::initialize();\n"
        "\n"
        "\tg_kernel_kmod_info.address = (vm_address_t) &_mh_execute_header;\n"
        "\n"
        "\tif (kOSReturnSuccess != OSRuntimeInitializeCPP(NULL)) {\n",
        "\t/* g0245d v234: v233 stopped between these lines.  One label per\n"
        "\t * step; the structor probe names the constructor if it is the\n"
        "\t * one that never returns.\n"
        "\t */\n"
        "\tg0245d_trace(\"v234 metaClassBase init enter\");\n"
        "\t// This must be called before calling OSRuntimeInitializeCPP.\n"
        "\tOSMetaClassBase::initialize();\n"
        "\tg0245d_trace(\"v234 metaClassBase init done\");\n"
        "\n"
        "\tg_kernel_kmod_info.address = (vm_address_t) &_mh_execute_header;\n"
        "\n"
        "\tg0245d_trace(\"v234 cpp enter\");\n"
        "\tif (kOSReturnSuccess != OSRuntimeInitializeCPP(NULL)) {\n",
        "OSRuntime: libkern init")

    src = sub(
        src,
        "\tgKernelCPPInitialized = true;\n"
        "\n"
        "\treturn;\n"
        "}\n",
        "\tg0245d_trace(\"v234 cpp done\");\n"
        "\n"
        "\tgKernelCPPInitialized = true;\n"
        "\n"
        "\treturn;\n"
        "}\n",
        "OSRuntime: cpp done")

    # a label at every structor section, so the probe index can be split into
    # the three __mod_init_func sections (96 + 1 + 1).
    src = sub(
        src,
        "\t\tstructor_t structor;\n"
        "\t\tuintptr_t value;\n"
        "\t\tunsigned long num_structors = section->size / sizeof(structor_t);\n",
        "\t\tstructor_t structor;\n"
        "\t\tuintptr_t value;\n"
        "\t\tunsigned long num_structors = section->size / sizeof(structor_t);\n"
        "\n"
        "\t\t/* g0245d v234: one label per section; the probe index keeps\n"
        "\t\t * counting across sections, so 0..95 is __DATA_CONST,\n"
        "\t\t * 96 is _last_kernel_constructor, 97 is bootstrap.cpp.\n"
        "\t\t */\n"
        "\t\tg0245d_trace(\"v234 structors section\");\n",
        "OSRuntime: section label")

    # the probe itself, right before the call
    src = sub(
        src,
        "\t\t\t\t(*structor)();\n",
        "\t\t\t\t/* g0245d v234: name the constructor before running it.\n"
        "\t\t\t\t * A hang inside it leaves this row pointing at it.\n"
        "\t\t\t\t */\n"
        "\t\t\t\tg0245d_probe_pc(value,\n"
        "\t\t\t\t    g0245d_structor_index++);\n"
        "\t\t\t\t(*structor)();\n",
        "OSRuntime: structor probe")

    # counter + traces around preModLoad and the segment loop
    src = sub(
        src,
        "static bool gKernelCPPInitialized = false;\n",
        "static bool gKernelCPPInitialized = false;\n"
        "\n"
        "/* g0245d v234: index into the kernel's __mod_init_func array.  Kept\n"
        " * across sections and segments so a photo always names one entry of\n"
        " * the static table scripts/structor_map.py prints.\n"
        " */\n"
        "static unsigned int g0245d_structor_index;\n",
        "OSRuntime: counter")

    src = sub(
        src,
        "\tmetaHandle = OSMetaClass::preModLoad(kmodInfo->name);\n"
        "\tassert(metaHandle);\n",
        "\tg0245d_trace(\"v234 preModLoad enter\");\n"
        "\tmetaHandle = OSMetaClass::preModLoad(kmodInfo->name);\n"
        "\tassert(metaHandle);\n"
        "\tg0245d_trace(\"v234 preModLoad done\");\n",
        "OSRuntime: preModLoad")

    src = sub(
        src,
        "\tfor (segment = firstsegfromheader(header);\n"
        "\t    segment != NULL && load_success;\n"
        "\t    segment = nextsegfromheader(header, segment)) {\n",
        "\tg0245d_trace(\"v234 segment walk enter\");\n"
        "\tfor (segment = firstsegfromheader(header);\n"
        "\t    segment != NULL && load_success;\n"
        "\t    segment = nextsegfromheader(header, segment)) {\n",
        "OSRuntime: segment walk")

    src = sub(
        src,
        "\t/* We failed so call all of the destructors. We must do this before\n",
        "\tg0245d_trace(\"v234 structors done\");\n"
        "\n"
        "\t/* We failed so call all of the destructors. We must do this before\n",
        "OSRuntime: structors done")

    write(OSRT, src)
    print("  patched OSRuntime.cpp")
else:
    src = ""

print("v234 ok")
