#!/usr/bin/env python3
"""g0245d v238 -- name the class where postModLoad's first pass stops.

The v237 photo is the first one that shows real progress inside
OSMetaClass::postModLoad():

  135 v237 cls IODMACommand
  136 v237 cls IOGeneralMemoryD...
  ...
  143 v237 cls IOSimpleReporter
  144 v237 cls IOUserServer...
  (rows 10..31 black)
  pml1 166
  97/98 s99 fffffff0079bd154
  >v233 OSlibrkernInit

so pass 1 is alive: it walks the stalled class array, prints every eighth
name, and the pinned row says it is on index 166.  Six iterations after the
last name (166 & 7 == 6) it stops, with no ring line at all.

That rules a lot out.  sAllClassesDict is still empty during pass 1 -- it is
filled in pass 2 -- so the duplicate lookup returns NULL immediately and
cannot be the stop.  What is left inside one iteration is the superclass
depth counter:

        unsigned int depth = 1;
        while ((me = me->superClassLink)) {
                depth++;
        }

A cycle (or a link field that points at something that is not a meta class)
makes that loop spin forever without allocating, logging, or printing --
exactly the silent stop the photo shows.

v238 therefore (a) prints the index, the total, a stage letter, the current
depth and the class name on the pinned row, so one photo names the victim,
(b) caps the walk at 32 and logs when the cap is hit, and (c) rejects a link
that is not a kernel pointer before dereferencing it.  The cap means that
even if the walk is the bug, this build keeps going and we see pass 2.

Also: v237's "pmlR" probe landed between the first and the second line of a
block comment, so it never ran.  Fixed here.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
MET = os.path.join(WORK, "libkern/c++/OSMetaClass.cpp")

MARK = "g0245d v238"


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


# ---------------------------------------------------------------- arm_init.c
s = read(ARM)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_con_putu((unsigned long)value, 10, 0);
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}
""",
        """	g0245d_con_putu((unsigned long)value, 10, 0);
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}

/* g0245d v238: the same pinned row, for "which class, how deep".
 * stage: 0 = loop top, 1 = after the duplicate lookup, 2 = inside the
 * superclass walk, 3 = walk finished, 4 = the link is not a kernel pointer.
 * The name is copied byte by byte with a fixed limit: className is still a
 * plain C string at this point, and a bring-up image is no place to trust
 * strlen() on whatever the link field happens to point at.
 */
void
g0245d_probe_cls(unsigned int idx, unsigned int total, unsigned int stage,
    unsigned int depth, const char *name)
{
	static const char stage_char[5] = { 'a', 'b', 'w', 'c', '!' };
	unsigned int      row;
	unsigned int      col;
	unsigned int      i;

	if (!g0245d_con_ready || g0245d_con_rows < 5) {
		return;
	}
	row = g0245d_con_row;
	col = g0245d_con_col;
	g0245d_con_row = g0245d_con_rows - 4;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	g0245d_con_putu((unsigned long)idx, 10, 0);
	g0245d_con_putc('/');
	g0245d_con_putu((unsigned long)total, 10, 0);
	g0245d_con_putc(' ');
	g0245d_con_putc(stage_char[stage < 5 ? stage : 4]);
	g0245d_con_putu((unsigned long)depth, 10, 0);
	g0245d_con_putc(' ');
	for (i = 0; i < 24 && name != 0 && name[i] != '\\0'; i++) {
		g0245d_con_putc(name[i]);
	}
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}
""",
        "arm_init: g0245d_probe_cls",
    )
    write(ARM, s)
    print("arm_init: v238 changes applied")
else:
    print("arm_init: already patched")

# ------------------------------------------------------------- OSMetaClass.cpp
s = read(MET)
if MARK not in s:
    s = sub(
        s,
        'extern "C" void g0245d_probe_u(const char *tag, unsigned int value);',
        'extern "C" void g0245d_probe_u(const char *tag, unsigned int value);\n'
        'extern "C" void g0245d_probe_cls(unsigned int idx, unsigned int total,\n'
        '    unsigned int stage, unsigned int depth, const char *name);',
        "OSMetaClass: extern g0245d_probe_cls",
    )

    # 1. the size of the list, so "166" can be read as "near the end" or not.
    s = sub(
        s,
        """			g0245d_trace("v237 pml kext ok");""",
        """			g0245d_trace("v237 pml kext ok");
			g0245d_trace_u("v238 count", sStalled->count);""",
        "OSMetaClass: stalled count",
    )

    # 2. pass 1: the pinned row now carries index/total/stage/depth/name.
    s = sub(
        s,
        """				g0245d_probe_u("pml1", i);
				if ((i & 7) == 0) {
					g0245d_trace_seg("v237 cls",
					    (const char *)me->className);
				}""",
        """				g0245d_probe_cls(i, sStalled->count, 0, 0,
				    (const char *)me->className);
				if ((i & 7) == 0) {
					g0245d_trace_seg("v238 cls",
					    (const char *)me->className);
				}""",
        "OSMetaClass: pass1 top probe",
    )

    # 3. stage b: the duplicate lookup is done (it cannot block -- the
    #    dictionary is empty during pass 1 -- but saying so costs one row).
    s = sub(
        s,
        """				OSMetaClass * orig = OSDynamicCast(OSMetaClass,
				    sAllClassesDict->getObject((const char *)me->className));
""",
        """				OSMetaClass * orig = OSDynamicCast(OSMetaClass,
				    sAllClassesDict->getObject((const char *)me->className));
				g0245d_probe_cls(i, sStalled->count, 1, 0,
				    (const char *)sStalled->classes[i]->className);
""",
        "OSMetaClass: pass1 lookup probe",
    )

    # 4. the depth walk: bounded, guarded, and it reports every step.
    s = sub(
        s,
        """				unsigned int depth = 1;
				while ((me = me->superClassLink)) {
				        depth++;
				}
				if (depth > sDeepestClass) {
				        sDeepestClass = depth;
				}""",
        """				unsigned int depth = 1;
				/* g0245d v238: the original loop was
				 *     while ((me = me->superClassLink)) depth++;
				 * with no bound and no validity check.  A single
				 * cycle in the chain -- or one link field holding
				 * something that is not a meta class -- turns it
				 * into a silent, allocation-free spin, which is
				 * what the panel shows after index 166.
				 */
				const OSMetaClass * walk = sStalled->classes[i]->superClassLink;

				while (walk != 0 && depth < 32) {
				        if ((unsigned long)walk < 0xfffffff000000000UL) {
				                g0245d_probe_cls(i, sStalled->count, 4,
				                    depth,
				                    (const char *)sStalled->classes[i]->className);
				                g0245d_trace_seg("v238 super badptr",
				                    (const char *)sStalled->classes[i]->className);
				                break;
				        }
				        depth++;
				        g0245d_probe_cls(i, sStalled->count, 2, depth,
				            (const char *)sStalled->classes[i]->className);
				        walk = walk->superClassLink;
				}
				if (depth >= 32) {
				        g0245d_trace_seg("v238 super cap",
				            (const char *)sStalled->classes[i]->className);
				}
				g0245d_probe_cls(i, sStalled->count, 3, depth,
				    (const char *)sStalled->classes[i]->className);
				if (depth > sDeepestClass) {
				        sDeepestClass = depth;
				}""",
        "OSMetaClass: bounded depth walk",
    )

    # 5. v237's pmlR went inside a block comment, so it never ran.  Take it
    #    out of the comment and put it where the function really returns.
    s = sub(
        s,
        """	/* Don't call logError() for success or the conditions logged above
	g0245d_probe_u("pmlR", (unsigned int)result);
	 * or by called function.
	 */""",
        """	/* Don't call logError() for success or the conditions logged above
	 * or by called function.
	 */""",
        "OSMetaClass: remove pmlR from comment",
    )
    s = sub(
        s,
        """	IOLockUnlock(sStalledClassesLock);

	return result;
}""",
        """	IOLockUnlock(sStalledClassesLock);

	/* g0245d v238: v237 put this one line inside the comment above, so
	 * the "did postModLoad return at all" question was never answered.
	 */
	g0245d_probe_u("pmlR", (unsigned int)result);
	return result;
}""",
        "OSMetaClass: pmlR on the real return",
    )

    write(MET, s)
    print("OSMetaClass: v238 changes applied")
else:
    print("OSMetaClass: already patched")

print("v238 patch applied")
