#!/usr/bin/env python3
"""g0245d v237 -- follow OSRuntimeInitializeCPP past the constructor walk.

The v236 photo finally reads in sequence, and it settles v235's contradiction
in favour of "the console was fine all along":

  103 v235 ctor ret           <- constructor 97, the last of 98
  104 v235 sect checked
  105 v235 seg __KLDDATA      <- segment 6 of 18 in the load commands
  106 v235 seg __DATA
  ...
  115 v235 seg __LINKINFO
  116 v235 seg __LINKEDIT     <- segment 17, the last one
  117 v234 structors done     <- printed after the walk loop exits

and the pinned row says "97/98 s99", i.e. entry 97 of 98 was reached at log
line 99.  So: all 98 constructors ran, and the loop walked every segment.

The very next statement in OSRuntimeInitializeCPP() is
g0245d_trace_u("v236 walk done i", g0245d_structor_index) -- and that line
never reached the panel, with 17 ring rows of empty space below it.  One
function call separates the last visible line from the stop, so v237 splits
it: a plain g0245d_trace() first, the numbered call kept as a canary, and
then the three things that follow -- the failed-load destructor walk,
OSMetaClass::postModLoad(), and OSRuntimeFinalizeCPP().

postModLoad() is where the 98 classes collected during the constructor walk
are turned into OSObjects: it builds sAllClassesDict, looks up the kernel's
OSKext by identifier, then twice walks every stalled class.  Any of those
steps can be the stop, so it gets a per-class line and a second pinned row.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
OSR = os.path.join(WORK, "libkern/c++/OSRuntime.cpp")
MET = os.path.join(WORK, "libkern/c++/OSMetaClass.cpp")

MARK = "g0245d v237"


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


def after(src, anchor, add, what):
    return sub(src, anchor, anchor + add, what)


def before(src, anchor, add, what):
    return sub(src, anchor, add + anchor, what)


# ---------------------------------------------------------------- arm_init.c
s = read(ARM)
if MARK not in s:
    # A second pinned row, so postModLoad progress survives even if the ring
    # path (printf) goes quiet.  rows-3 belongs to the constructor probe.
    s = after(
        s,
        """	for (i = 0; i < 12; i++) {
		d = (unsigned int)((pc >> (44 - 4 * i)) & 0xf);
		g0245d_con_putc((char)(d < 10 ? '0' + d : 'a' + d - 10));
	}
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}
""",
        """
/* g0245d v237: a second pinned row, for "which class is postModLoad on".
 * The constructor probe owns rows-3; this one owns rows-4, so a single photo
 * shows both at once.  It writes straight to the panel like probe_pc(), i.e.
 * it does not depend on the ring or on the %u path of con_printf().
 */
void
g0245d_probe_u(const char *tag, unsigned int value)
{
	unsigned int row;
	unsigned int col;

	if (!g0245d_con_ready || g0245d_con_rows < 5) {
		return;
	}
	row = g0245d_con_row;
	col = g0245d_con_col;
	g0245d_con_row = g0245d_con_rows - 4;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	if (tag) {
		g0245d_con_puts(tag);
		g0245d_con_putc(' ');
	}
	g0245d_con_putu((unsigned long)value, 10, 0);
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}
""",
        "arm_init: g0245d_probe_u",
    )

    # Safety net: if the ready flag is ever cleared while the framebuffer is
    # still valid, con_printf() silently dropping every line looks exactly
    # like a hang.  Re-arm quietly here; g0245d_trace() still says so loudly.
    s = before(
        s,
        """	if (!g0245d_con_ready) {
		return;
	}
	va_start(ap, fmt);""",
        """	if (!g0245d_con_ready) {
		if (g0245d_con_base == 0) {
			return;
		}
		/* g0245d v237: take the console back instead of going silent. */
		g0245d_con_ready = 1;
		g0245d_con_owns_text = 1;
	}
""",
        "arm_init: con_printf re-arms",
    )

    write(ARM, s)
    print("arm_init: v237 changes applied")
else:
    print("arm_init: already patched")

# --------------------------------------------------------------- OSRuntime.cpp
s = read(OSR)
if MARK not in s:
    s = after(
        s,
        'extern "C" void g0245d_trace_u(const char *label, unsigned int value);',
        '\nextern "C" void g0245d_probe_u(const char *tag, unsigned int value);',
        "OSRuntime: extern g0245d_probe_u",
    )

    # 1. split the two calls that were adjacent in v236.
    s = sub(
        s,
        """	g0245d_trace("v234 structors done");
	g0245d_trace_u("v236 walk done i", g0245d_structor_index);""",
        """	g0245d_trace("v234 structors done");
	/* g0245d v237: v236 put the numbered call immediately after this
	 * line and only the first one reached the panel, so the two are now
	 * separated by a plain trace and the numbered call stays last, as a
	 * canary for the %u path itself.
	 */
	g0245d_trace("v237 walk done");
	g0245d_trace(load_success ? "v237 load ok" : "v237 load failed");
	g0245d_trace_u("v236 walk done i", g0245d_structor_index);""",
        "OSRuntime: split walk done",
    )

    # 2. the destructor walk that only runs when a constructor failed.
    #    Anchor on the loop head, not on the comment above it: anchoring on a
    #    block comment's first line splits the comment in two (that is how the
    #    first v237 build failed to compile).
    s = before(
        s,
        """		for (segment = firstsegfromheader(header);
		    segment != failure_segment && segment != NULL;""",
        """		g0245d_trace("v237 destructors enter");
""",
        "OSRuntime: destructors enter",
    )
    s = sub(
        s,
        """		} /* for (segment...) */
	}

	/* Now, regardless of success so far, do the post-init registration""",
        """		} /* for (segment...) */
		g0245d_trace("v237 destructors done");
	}

	/* Now, regardless of success so far, do the post-init registration""",
        "OSRuntime: destructors done",
    )

    # 3. postModLoad, the point where the 98 classes become objects.
    s = sub(
        s,
        """	result = OSMetaClass::postModLoad(metaHandle);""",
        """	g0245d_trace("v237 pml enter");
	result = OSMetaClass::postModLoad(metaHandle);
	g0245d_trace("v237 pml done");
	/* g0245d v237: the canary -- if everything above appears and this one
	 * does not, the %u path of con_printf() is what stops, not the kernel.
	 */
	g0245d_trace_u("v237 pml result", (unsigned int)result);""",
        "OSRuntime: postModLoad brackets",
    )

    # 4. the teardown that runs when postModLoad fails.
    s = sub(
        s,
        """		(void)OSRuntimeFinalizeCPP(theKext); //kmodInfo, sectionNames, textStart, textEnd);""",
        """		g0245d_trace("v237 finalize enter");
		(void)OSRuntimeFinalizeCPP(theKext); //kmodInfo, sectionNames, textStart, textEnd);
		g0245d_trace("v237 finalize done");""",
        "OSRuntime: finalize brackets",
    )

    # 5. one line out of OSRuntimeInitializeCPP, whatever the outcome.
    s = sub(
        s,
        """	if (theKext && load_success && result == KMOD_RETURN_SUCCESS) {
		theKext->setCPPInitialized(true);
	}
finish:
	return result;
}""",
        """	if (theKext && load_success && result == KMOD_RETURN_SUCCESS) {
		theKext->setCPPInitialized(true);
	}
finish:
	g0245d_probe_u("cppR", (unsigned int)result);
	return result;
}""",
        "OSRuntime: cpp return",
    )

    write(OSR, s)
    print("OSRuntime: v237 changes applied")
else:
    print("OSRuntime: already patched")

# ------------------------------------------------------------- OSMetaClass.cpp
s = read(MET)
if MARK not in s:
    # Declarations go above every #if on purpose: the PAC block is compiled out
    # on this target, and both v234 and v235 lost a round to that.
    s = after(
        s,
        "#include <libkern/c++/OSSerialize.h>",
        """

/* g0245d v237: framebuffer console probes, from osfmk/arm/arm_init.c. */
extern "C" void g0245d_trace(const char *label);
extern "C" void g0245d_trace_u(const char *label, unsigned int value);
extern "C" void g0245d_trace_seg(const char *label, const char *segname);
extern "C" void g0245d_probe_u(const char *tag, unsigned int value);
""",
        "OSMetaClass: extern block",
    )

    s = before(
        s,
        """	if (!sStalled || loadHandle != sStalled) {""",
        """	g0245d_trace("v237 pml body");
""",
        "OSMetaClass: pml body",
    )
    s = sub(
        s,
        """		result = kOSMetaClassInternal;
		goto finish;""",
        """		g0245d_trace("v237 pml no stalled");
		result = kOSMetaClassInternal;
		goto finish;""",
        "OSMetaClass: pml no stalled",
    )

    s = before(
        s,
        """			sAllClassesDict = OSDictionary::withCapacity(kClassCapacityIncrement);""",
        """			g0245d_trace("v237 pml dict enter");
""",
        "OSMetaClass: pml dict enter",
    )
    s = after(
        s,
        """			sAllClassesDict->setOptions(OSCollection::kSort, OSCollection::kSort);""",
        """
			g0245d_trace("v237 pml dict ok");""",
        "OSMetaClass: pml dict ok",
    )

    s = before(
        s,
        """			myKext = OSKext::lookupKextWithIdentifier(myKextName);""",
        """			g0245d_trace("v237 pml kext lookup");
""",
        "OSMetaClass: pml kext lookup",
    )
    s = before(
        s,
        """				result = kOSMetaClassNoKext;""",
        """				g0245d_trace("v237 pml no kext");
""",
        "OSMetaClass: pml no kext",
    )
    s = before(
        s,
        """			/* First pass checking classes aren't already loaded. If any already""",
        """			g0245d_trace("v237 pml kext ok");
""",
        "OSMetaClass: pml kext ok",
    )

    # pass 1: names every class, pins the index where the ring cannot help.
    s = after(
        s,
        """				const OSMetaClass * me = sStalled->classes[i];""",
        """
				g0245d_probe_u("pml1", i);
				if ((i & 7) == 0) {
					g0245d_trace_seg("v237 cls",
					    (const char *)me->className);
				}""",
        "OSMetaClass: pml pass1 probes",
    )
    s = before(
        s,
        """			// Second pass symbolling strings and inserting classes in dictionary""",
        """			g0245d_trace("v237 pml pass1 done");
""",
        "OSMetaClass: pml pass1 done",
    )

    s = after(
        s,
        """			IOLockLock(sAllClassesLock);
			for (i = 0; i < sStalled->count; i++) {
			        OSMetaClass * me = sStalled->classes[i];""",
        """
				g0245d_probe_u("pml2", i);""",
        "OSMetaClass: pml pass2 probe",
    )

    s = after(
        s,
        """finish:
	/* Don't call logError() for success or the conditions logged above""",
        """
	g0245d_probe_u("pmlR", (unsigned int)result);""",
        "OSMetaClass: pml finish",
    )

    write(MET, s)
    print("OSMetaClass: v237 changes applied")
else:
    print("OSMetaClass: already patched")

print("v237 patch applied")
