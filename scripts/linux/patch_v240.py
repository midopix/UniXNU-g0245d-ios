#!/usr/bin/env python3
"""g0245d v240 -- open up ConfigureIOKit(), the next stop.

v239's photo is the best one yet:

    167 v233 dtree walk enter
    168 v233 dtree walk done
    169 v233 dtree attached
    170 v230 early_random calls 0xc00
    171 v233 dtree done
    172 v233 root nub init done
    173 v233 root nub attach enter
    174 v233 root nub attached
    175 v232 InitIOKit done
    (rows 9..31 blank)

So OSMetaClass::postModLoad() is behind us (the whole pml ladder wrapped off
the top of the ring), IODeviceTreeAlloc() converted the tree, the root nub was
initialised and attached, and InitIOKit() returned.  The next statement is
ConfigureIOKit() -> gRootNub->configureDefaults(), and "v232 ConfigureIOKit
done" never appears.

configureDefaults() is three cheap-looking things: createNVRAM() (only if the
device tree has /options), publishing "serial-number" as a string, and
generatePlatformUUID() (only if /chosen has unique-chip-id and chip-id).  Any
of them can still be the stop, and each is a different fix, so v240 brackets
every step instead of guessing.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

IOK = os.path.join(WORK, "iokit/Kernel/IOStartIOKit.cpp")
PE = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")

MARK = "g0245d v240"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what):
    n = src.count(old)
    if n != 1:
        sys.exit("%s: anchor found %d times" % (what, n))
    return src.replace(old, new)


# ----------------------------------------------------------- IOStartIOKit.cpp
s = read(IOK)
if MARK not in s:
    s = sub(
        s,
        """void
ConfigureIOKit(void)
{
	assert(gRootNub != NULL);
	gRootNub->configureDefaults();
}""",
        """void
ConfigureIOKit(void)
{
	/* g0245d v240: separate "the function was reached" from "the defaults
	 * ran", because the assert below and the virtual call have very
	 * different failure modes.
	 */
	g0245d_trace("v240 cfg enter");
	assert(gRootNub != NULL);
	g0245d_trace("v240 cfg rootnub ok");
	gRootNub->configureDefaults();
	g0245d_trace("v240 cfg defaults done");
}""",
        "IOStartIOKit: ConfigureIOKit ladder",
    )
    write(IOK, s)
    print("IOStartIOKit: v240 changes applied")
else:
    print("IOStartIOKit: already patched")

# -------------------------------------------------------- IOPlatformExpert.cpp
s = read(PE)
if MARK not in s:
    # Declarations go above the first #if, for the reason v234 and v237 found
    # the hard way.
    s = sub(
        s,
        "#include <libkern/OSAtomic.h>",
        """#include <libkern/OSAtomic.h>

/* g0245d v240: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern "C" void g0245d_trace(const char *label);""",
        "IOPlatformExpert: extern block",
    )

    s = sub(
        s,
        """void
IOPlatformExpertDevice::configureDefaults( void )
{
	createNVRAM();
	// Parse the serial-number data and publish a user-readable string
	OSData* mydata = (OSData*) (getProperty("serial-number"));
	if (mydata != NULL) {
		OSString *serNoString = OSString::withCString((const char *)mydata->getBytesNoCopy());
		if (serNoString != NULL) {
			setProperty(kIOPlatformSerialNumberKey, serNoString);
			serNoString->release();
		}
	}
	generatePlatformUUID();
}""",
        """void
IOPlatformExpertDevice::configureDefaults( void )
{
	g0245d_trace("v240 nvram enter");
	createNVRAM();
	g0245d_trace("v240 nvram done");
	// Parse the serial-number data and publish a user-readable string
	OSData* mydata = (OSData*) (getProperty("serial-number"));
	g0245d_trace(mydata != NULL ? "v240 serial got" : "v240 serial none");
	if (mydata != NULL) {
		OSString *serNoString = OSString::withCString((const char *)mydata->getBytesNoCopy());
		g0245d_trace("v240 serial string ok");
		if (serNoString != NULL) {
			setProperty(kIOPlatformSerialNumberKey, serNoString);
			serNoString->release();
		}
	}
	g0245d_trace("v240 uuid enter");
	generatePlatformUUID();
	g0245d_trace("v240 uuid done");
}""",
        "IOPlatformExpert: configureDefaults ladder",
    )

    s = sub(
        s,
        """	IORegistryEntry *options = IORegistryEntry::fromPath("/options", gIODTPlane);
	if (options == NULL) {
		return; // /options may not be present
	}

	assert(gIOOptionsEntry == NULL);
	gIOOptionsEntry = new IODTNVRAM;

	assert(gIOOptionsEntry != NULL);

	gIOOptionsEntry->init(options, gIODTPlane);
	gIOOptionsEntry->attach(this);
	gIOOptionsEntry->start(this);""",
        """	g0245d_trace("v240 options frompath");
	IORegistryEntry *options = IORegistryEntry::fromPath("/options", gIODTPlane);
	g0245d_trace(options != NULL ? "v240 options found" : "v240 options absent");
	if (options == NULL) {
		return; // /options may not be present
	}

	assert(gIOOptionsEntry == NULL);
	g0245d_trace("v240 nvram new");
	gIOOptionsEntry = new IODTNVRAM;

	assert(gIOOptionsEntry != NULL);

	g0245d_trace("v240 nvram init enter");
	gIOOptionsEntry->init(options, gIODTPlane);
	g0245d_trace("v240 nvram init done");
	gIOOptionsEntry->attach(this);
	g0245d_trace("v240 nvram attach done");
	gIOOptionsEntry->start(this);
	g0245d_trace("v240 nvram start done");""",
        "IOPlatformExpert: createNVRAM ladder",
    )

    s = sub(
        s,
        """	entry = IORegistryEntry::fromPath( "/chosen", gIODTPlane );
	if (entry) {
		OSData * data1;

		data1 = OSDynamicCast( OSData, entry->getProperty( "unique-chip-id" ));""",
        """	g0245d_trace("v240 uuid chosen enter");
	entry = IORegistryEntry::fromPath( "/chosen", gIODTPlane );
	g0245d_trace(entry != NULL ? "v240 uuid chosen ok" : "v240 uuid no chosen");
	if (entry) {
		OSData * data1;

		data1 = OSDynamicCast( OSData, entry->getProperty( "unique-chip-id" ));
		g0245d_trace(data1 != NULL ? "v240 uuid chip1" : "v240 uuid no chip1");""",
        "IOPlatformExpert: uuid ladder",
    )

    write(PE, s)
    print("IOPlatformExpert: v240 changes applied")
else:
    print("IOPlatformExpert: already patched")

print("v240 patch applied")
