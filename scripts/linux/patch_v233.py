#!/usr/bin/env python3
"""g0245d v233: find out where InitIOKit() dies, and stop the ring from
scrambling the panel.

v232's photo read, top to bottom:

    42 code_signing_init ... 55 sysctl
    56 PE_init_iokit
    57 v232 PE_init_iokit enter
    58 v232 iokit printf rearmed
    59 v232 iokit pict done
    60 v232 iokit images done
    61 v232 iokit progress done
    62 v232 InitIOKit enter
    63 v230 early_random calls 0x800
    32 sched_init ... 41 coalitions_init      <- older lines, ring wrap
    ABCDEFGH... ruler
    >PE_init_iokit                            <- pinned status row

So the kernel walks the whole bootstrap ladder (sched_init through sysctl),
enters PE_init_iokit(), and dies *inside* InitIOKit() -- after about 2048
zone allocations (early_random is called once per allocation, and it prints
every 1024).  Two notes on the reading:

  * The number restarting at 32 is not a second counter: the ring is 33 rows
    and the panel shows it linearly, so the wrap point lands in the middle of
    the screen.  Everything above the wrap is the newest text, everything
    below it is stale -- that is the "half here, half there" look v231 could
    not fix by moving pixels.  v233 clears the ring when it wraps.

  * InitIOKit() is the first place this kernel converts the flattened device
    tree into live OSObjects, which is exactly what a machine with no arm-io
    node would trip over.

Three changes:

1. osfmk/arm/arm_init.c -- clear every ring row when the cursor wraps back to
   row 0, so the panel always reads newest-at-top without stale rows
   interleaved.  Also a probe line pinned at row rows-3 that the device-tree
   walk updates once per node.

2. iokit/Kernel/IOStartIOKit.cpp -- a trace ladder across InitIOKit():
   IOLibInit, OSlibrkernInit, IOMachPortInitialize, symbol creation,
   interruptAccountingInit, root nub alloc, root nub init, root nub attach.

3. iokit/Kernel/IODeviceTreeSupport.cpp -- stage traces in
   IODeviceTreeAlloc() plus one probe per node, printed *before* the node is
   converted, so a hang names the node it was working on.

Idempotent: every anchor is asserted unique and a 'v233' marker guards each
hunk.
"""

import os
import sys

BASE = os.environ.get(
    "XNU_WORK",
    os.path.expanduser("~/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66"
    "/g0245d/tree/.cache/xnu-work"),
)

ARM_INIT = os.path.join(BASE, "osfmk/arm/arm_init.c")
IO_START = os.path.join(BASE, "iokit/Kernel/IOStartIOKit.cpp")
IO_DT = os.path.join(BASE, "iokit/Kernel/IODeviceTreeSupport.cpp")


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


# ------------------------------------------------------------ arm_init.c

src = read(ARM_INIT)

if once(src, "v233 con probe", "arm_init: probe line"):
    # 1. one more pinned row: rows-3 is the probe, rows-2 the ruler,
    #    rows-1 the status line.  The ring keeps rows 0..rows-4.
    src = sub(
        src,
        "\t/* g0245d v231: row rows-2 is the column ruler and row rows-1 the\n"
        "\t * status line; neither is in the ring, so both stay put. */\n"
        "\tg0245d_con_nscroll = (g0245d_con_rows > 2) ?\n"
        "\t    g0245d_con_rows - 2 : g0245d_con_rows;\n",
        "\t/* g0245d v231: row rows-2 is the column ruler and row rows-1 the\n"
        "\t * status line; neither is in the ring, so both stay put. */\n"
        "\t/* g0245d v233: row rows-3 is the probe line -- one live label that\n"
        "\t * the device-tree walk overwrites per node, so it survives every\n"
        "\t * ring wrap and always names the last node converted. */\n"
        "\tg0245d_con_nscroll = (g0245d_con_rows > 3) ?\n"
        "\t    g0245d_con_rows - 3 : g0245d_con_rows;\n",
        "arm_init: nscroll")

    # 2. clear the ring when the cursor wraps, so the panel never shows the
    #    newest lines above stale ones.
    src = sub(
        src,
        "\tif (c == '\\n' || g0245d_con_col >= g0245d_con_cols) {\n"
        "\t\tg0245d_con_col = 0;\n"
        "\t\tg0245d_con_row = (g0245d_con_row + 1) % g0245d_con_nscroll;\n"
        "\t\tg0245d_con_fill_row(g0245d_con_row);\n",
        "\tif (c == '\\n' || g0245d_con_col >= g0245d_con_cols) {\n"
        "\t\tunsigned int wrap_row;\n"
        "\t\tg0245d_con_col = 0;\n"
        "\t\tg0245d_con_row = (g0245d_con_row + 1) % g0245d_con_nscroll;\n"
        "\t\t/* g0245d v233: the ring is shown linearly, so once the cursor\n"
        "\t\t * wraps the panel holds newest text on top and stale text\n"
        "\t\t * below, which reads as scrambled output.  Blank the whole\n"
        "\t\t * ring on wrap instead: the panel then always reads\n"
        "\t\t * newest-at-top with nothing old mixed in.\n"
        "\t\t */\n"
        "\t\tif (g0245d_con_row == 0) {\n"
        "\t\t\tfor (wrap_row = 1; wrap_row < g0245d_con_nscroll;\n"
        "\t\t\t    wrap_row++) {\n"
        "\t\t\t\tg0245d_con_fill_row(wrap_row);\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tg0245d_con_fill_row(g0245d_con_row);\n",
        "arm_init: ring wrap")

    # 3. the probe line itself.
    src = sub(
        src,
        "static unsigned int g0245d_trace_seq;\n",
        "/* g0245d v233 con probe: one pinned line directly above the ruler.\n"
        " * The device-tree walk calls this once per node, so the panel names\n"
        " * the node that was being converted when the machine stopped -- even\n"
        " * after the ring has wrapped a dozen times.  Cheap enough to call\n"
        " * per node: one row fill, at most cols-6 glyphs, one cache clean.\n"
        " */\n"
        "static unsigned int g0245d_probe_seq;\n"
        "\n"
        "void\n"
        "g0245d_probe(const char *label)\n"
        "{\n"
        "\tunsigned int   row;\n"
        "\tunsigned int   col;\n"
        "\tunsigned int   i;\n"
        "\n"
        "\tif (!g0245d_con_ready || g0245d_con_rows < 4 || label == 0) {\n"
        "\t\treturn;\n"
        "\t}\n"
        "\trow = g0245d_con_row;\n"
        "\tcol = g0245d_con_col;\n"
        "\tg0245d_con_row = g0245d_con_rows - 3;\n"
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
        "static unsigned int g0245d_trace_seq;\n",
        "arm_init: probe body")

    write(ARM_INIT, src)
    print("  patched arm_init.c")
else:
    src = ""

# -------------------------------------------------------- IOStartIOKit.cpp

src = read(IO_START)

if once(src, "v233 IOLibInit enter", "IOStartIOKit: ladder"):
    src = sub(
        src,
        '#include "IOKitKernelInternal.h"\n',
        '#include "IOKitKernelInternal.h"\n'
        "\n"
        "/* g0245d v233: framebuffer text console probes, from\n"
        " * osfmk/arm/arm_init.c.  g0245d_status pins a label on the bottom row\n"
        " * of the panel; g0245d_trace appends a scrolling numbered line.\n"
        " */\n"
        "extern \"C\" void g0245d_trace(const char *label);\n"
        "extern \"C\" void g0245d_status(const char *label);\n",
        "IOStartIOKit: extern decls")

    src = sub(
        src,
        "\tIOLibInit();\n"
        "\tOSlibkernInit();\n"
        "\tIOMachPortInitialize();\n"
        "\n"
        "\tgIOProgressBackbufferKey  = OSSymbol::withCStringNoCopy(kIOProgressBackbufferKey);\n"
        "\tgIORemoveOnReadProperties = OSSet::withObjects((const OSObject **) &gIOProgressBackbufferKey, 1);\n"
        "\n"
        "\tinterruptAccountingInit();\n"
        "\n"
        "\tgRootNub = new IOPlatformExpertDevice;\n"
        "\tif (__improbable(gRootNub == NULL)) {\n"
        "\t\tpanic(\"Failed to allocate IOKit root nub\");\n"
        "\t}\n"
        "\tbool ok = gRootNub->init(dtTop);\n"
        "\tif (__improbable(!ok)) {\n"
        "\t\tpanic(\"Failed to initialize IOKit root nub\");\n"
        "\t}\n"
        "\tgRootNub->attach(NULL);\n",
        "\t/* g0245d v233: v232 died in here after ~2048 zone allocations.\n"
        "\t * One label per call; the last one printed names the callee that\n"
        "\t * never returned.\n"
        "\t */\n"
        "\tg0245d_status(\"v233 IOLibInit\");\n"
        "\tg0245d_trace(\"v233 IOLibInit enter\");\n"
        "\tIOLibInit();\n"
        "\tg0245d_trace(\"v233 IOLibInit done\");\n"
        "\n"
        "\tg0245d_status(\"v233 OSlibrkernInit\");\n"
        "\tg0245d_trace(\"v233 OSlibrkernInit enter\");\n"
        "\tOSlibkernInit();\n"
        "\tg0245d_trace(\"v233 OSlibrkernInit done\");\n"
        "\n"
        "\tg0245d_status(\"v233 IOMachPortInit\");\n"
        "\tg0245d_trace(\"v233 IOMachPortInit enter\");\n"
        "\tIOMachPortInitialize();\n"
        "\tg0245d_trace(\"v233 IOMachPortInit done\");\n"
        "\n"
        "\tg0245d_status(\"v233 IOKit symbols\");\n"
        "\tg0245d_trace(\"v233 IOKit symbols enter\");\n"
        "\tgIOProgressBackbufferKey  = OSSymbol::withCStringNoCopy(kIOProgressBackbufferKey);\n"
        "\tgIORemoveOnReadProperties = OSSet::withObjects((const OSObject **) &gIOProgressBackbufferKey, 1);\n"
        "\tg0245d_trace(\"v233 IOKit symbols done\");\n"
        "\n"
        "\tg0245d_status(\"v233 intrAccounting\");\n"
        "\tg0245d_trace(\"v233 intrAccounting enter\");\n"
        "\tinterruptAccountingInit();\n"
        "\tg0245d_trace(\"v233 intrAccounting done\");\n"
        "\n"
        "\tg0245d_status(\"v233 root nub alloc\");\n"
        "\tg0245d_trace(\"v233 root nub alloc\");\n"
        "\tgRootNub = new IOPlatformExpertDevice;\n"
        "\tif (__improbable(gRootNub == NULL)) {\n"
        "\t\tpanic(\"Failed to allocate IOKit root nub\");\n"
        "\t}\n"
        "\tg0245d_trace(\"v233 root nub allocated\");\n"
        "\n"
        "\tg0245d_status(\"v233 root nub init\");\n"
        "\tg0245d_trace(\"v233 root nub init enter\");\n"
        "\tbool ok = gRootNub->init(dtTop);\n"
        "\tif (__improbable(!ok)) {\n"
        "\t\tpanic(\"Failed to initialize IOKit root nub\");\n"
        "\t}\n"
        "\tg0245d_trace(\"v233 root nub init done\");\n"
        "\n"
        "\tg0245d_status(\"v233 root nub attach\");\n"
        "\tg0245d_trace(\"v233 root nub attach enter\");\n"
        "\tgRootNub->attach(NULL);\n"
        "\tg0245d_trace(\"v233 root nub attached\");\n",
        "IOStartIOKit: InitIOKit body")

    write(IO_START, src)
    print("  patched IOStartIOKit.cpp")
else:
    src = ""

# -------------------------------------------------- IODeviceTreeSupport.cpp

src = read(IO_DT)

if once(src, "v233 dtree alloc enter", "IODeviceTreeSupport: ladder"):
    src = sub(
        src,
        "static IORegistryEntry * MakeReferenceTable( DTEntry dtEntry, bool copy );\n",
        "/* g0245d v233: one pinned console line, from osfmk/arm/arm_init.c. */\n"
        'extern "C" void g0245d_probe(const char *label);\n'
        'extern "C" void g0245d_trace(const char *label);\n'
        "\n"
        "static IORegistryEntry * MakeReferenceTable( DTEntry dtEntry, bool copy );\n",
        "dt: extern decls")

    src = sub(
        src,
        "IORegistryEntry *\n"
        "IODeviceTreeAlloc( void * dtTop )\n"
        "{\n",
        "IORegistryEntry *\n"
        "IODeviceTreeAlloc( void * dtTop )\n"
        "{\n"
        "\t/* g0245d v233: this is the first place the kernel turns the\n"
        "\t * flattened device tree into live OSObjects, and it is where\n"
        "\t * v232 stopped, so the whole function gets labels.\n"
        "\t */\n"
        "\tg0245d_trace(\"v233 dtree alloc enter\");\n",
        "dt: entry")

    src = sub(
        src,
        "\tassert(    gIODTDefaultInterruptController && gIODTNWInterruptMappingKey\n"
        "\t    && gIODTAAPLInterruptsKey\n"
        "\t    && gIODTPHandleKey && gIODTInterruptParentKey\n"
        "\t    && gIODTPHandles && gIODTPHandleMap && gIODTInterruptCellKey\n"
        "\t    && gIODTResolvers && gIODTResolvers->lock && gIODTResolvers->resolvers\n"
        "\t    );\n",
        "\tassert(    gIODTDefaultInterruptController && gIODTNWInterruptMappingKey\n"
        "\t    && gIODTAAPLInterruptsKey\n"
        "\t    && gIODTPHandleKey && gIODTInterruptParentKey\n"
        "\t    && gIODTPHandles && gIODTPHandleMap && gIODTInterruptCellKey\n"
        "\t    && gIODTResolvers && gIODTResolvers->lock && gIODTResolvers->resolvers\n"
        "\t    );\n"
        "\tg0245d_trace(\"v233 dtree syms done\");\n",
        "dt: symbols")

    src = sub(
        src,
        "\tparent = MakeReferenceTable((DTEntry)dtTop, freeDT );\n"
        "\n"
        "\tstack = OSArray::withObjects((const OSObject **) &parent, 1, 10 );\n"
        "\tSecureDTInitEntryIterator((DTEntry)dtTop, &iter );\n",
        "\tg0245d_trace(\"v233 dtree root enter\");\n"
        "\tparent = MakeReferenceTable((DTEntry)dtTop, freeDT );\n"
        "\tg0245d_trace(\"v233 dtree root done\");\n"
        "\n"
        "\tstack = OSArray::withObjects((const OSObject **) &parent, 1, 10 );\n"
        "\tSecureDTInitEntryIterator((DTEntry)dtTop, &iter );\n"
        "\tg0245d_trace(\"v233 dtree walk enter\");\n",
        "dt: root")

    src = sub(
        src,
        "\t\t\tchild = MakeReferenceTable( dtChild, freeDT );\n",
        "\t\t\t/* g0245d v233: name the node *before* converting it, so a\n"
        "\t\t\t * hang inside MakeReferenceTable() still names its victim.\n"
        "\t\t\t * The counter in front climbs once per node, which is also\n"
        "\t\t\t * how a walk that never advances shows up on the panel.\n"
        "\t\t\t */\n"
        "\t\t\t{\n"
        "\t\t\t\tvoid const *  dtName = NULL;\n"
        "\t\t\t\tunsigned int  dtNameSize = 0;\n"
        "\n"
        "\t\t\t\tif ((kSuccess == SecureDTGetProperty( dtChild, \"name\",\n"
        "\t\t\t\t    &dtName, &dtNameSize )) && (dtName != NULL)) {\n"
        "\t\t\t\t\tg0245d_probe((const char *) dtName);\n"
        "\t\t\t\t} else {\n"
        "\t\t\t\t\tg0245d_probe(\"(unnamed)\");\n"
        "\t\t\t\t}\n"
        "\t\t\t}\n"
        "\t\t\tchild = MakeReferenceTable( dtChild, freeDT );\n",
        "dt: per node")

    src = sub(
        src,
        "\t} while (stack->getCount()\n"
        "\t    && (kSuccess == SecureDTExitEntry( &iter, &dtChild)));\n"
        "\n"
        "\tstack->release();\n",
        "\t} while (stack->getCount()\n"
        "\t    && (kSuccess == SecureDTExitEntry( &iter, &dtChild)));\n"
        "\tg0245d_trace(\"v233 dtree walk done\");\n"
        "\n"
        "\tstack->release();\n",
        "dt: walk done")

    src = sub(
        src,
        "\tparent->attachToParent( IORegistryEntry::getRegistryRoot(), gIODTPlane);\n"
        "\tparent->release();\n",
        "\tparent->attachToParent( IORegistryEntry::getRegistryRoot(), gIODTPlane);\n"
        "\tparent->release();\n"
        "\tg0245d_trace(\"v233 dtree attached\");\n",
        "dt: attach")

    src = sub(
        src,
        "\treturn parent;\n"
        "}\n"
        "#endif\n",
        "\tg0245d_trace(\"v233 dtree done\");\n"
        "\treturn parent;\n"
        "}\n"
        "#endif\n",
        "dt: done")

    write(IO_DT, src)
    print("  patched IODeviceTreeSupport.cpp")
else:
    src = ""

print("v233 ok")
