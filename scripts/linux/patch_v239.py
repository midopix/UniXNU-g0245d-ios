#!/usr/bin/env python3
"""g0245d v239 -- stop walking the superclass chain, print its pointer instead.

v238's photo is unambiguous:

    135..145 v238 cls IOInterruptEvent .. IOUserServerUserClient
    (rows 11..31 black)
    166/167 w2 NativeAES
    97/98 s99 fffffff0079bd154
    >v233 OSlibrkernInit

sStalled->count is 167 and index 166 is the *last* class, NativeAES.  The
pinned row says stage w (inside the walk), depth 2.  So the walk started: it
read classes[166]->superClassLink (which passed v238's `>= 0xfffffff000000000`
test), counted one step, printed w2, and died reading that object's
superClassLink.

That test was far too loose: 0xfffffff000000000..0xffffffffffffffff is 4 GB of
address space and almost none of it is mapped here.  A pointer into it looks
like a kernel pointer and cannot be read.

There is no reason to debug it.  sDeepestClass is only used as maxDepth in
OSMetaClass::applyToInstances(), so a constant is as good as the real depth.
v239 therefore drops the walk, keeps the pointer on the pinned row so the
value is not lost, and lets pass 1 finish -- index 166 is the last one, so one
line later the boot is in pass 2, which is real progress.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
MET = os.path.join(WORK, "libkern/c++/OSMetaClass.cpp")

MARK = "g0245d v239"


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
        """void
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
}""",
        """void
g0245d_probe_cls(unsigned int idx, unsigned int total, unsigned int stage,
    unsigned int depth, uintptr_t ptr, const char *name)
{
	static const char stage_char[5] = { 'a', 'b', 'w', 'c', '!' };
	unsigned int      row;
	unsigned int      col;
	unsigned int      i;
	unsigned int      d;

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
	/* g0245d v239: low 32 bits of the pointer, 8 hex digits.  Every meta
	 * class object in this kernel sits at 0xfffffff007xxxxxx, so the low
	 * half is enough to name one, and 8 digits keep the row readable.
	 */
	for (i = 0; i < 8; i++) {
		d = (unsigned int)((ptr >> (28 - 4 * (int)i)) & 0xf);
		g0245d_con_putc((char)(d < 10 ? '0' + d : 'a' + d - 10));
	}
	g0245d_con_putc(' ');
	for (i = 0; i < 18 && name != 0 && name[i] != '\\0'; i++) {
		g0245d_con_putc(name[i]);
	}
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}""",
        "arm_init: probe_cls gains a pointer",
    )
    write(ARM, s)
    print("arm_init: v239 changes applied")
else:
    print("arm_init: already patched")

# ------------------------------------------------------------- OSMetaClass.cpp
s = read(MET)
if MARK not in s:
    s = sub(
        s,
        """extern "C" void g0245d_probe_cls(unsigned int idx, unsigned int total,
    unsigned int stage, unsigned int depth, const char *name);""",
        """extern "C" void g0245d_probe_cls(unsigned int idx, unsigned int total,
    unsigned int stage, unsigned int depth, uintptr_t ptr, const char *name);""",
        "OSMetaClass: extern signature",
    )

    # stage a: name the class and its own address.
    s = sub(
        s,
        """				g0245d_probe_cls(i, sStalled->count, 0, 0,
				    (const char *)me->className);""",
        """				g0245d_probe_cls(i, sStalled->count, 0, 0,
				    (uintptr_t)me, (const char *)me->className);""",
        "OSMetaClass: stage a",
    )

    # stage b: the lookup is done; print the superclass link, not the class.
    s = sub(
        s,
        """				g0245d_probe_cls(i, sStalled->count, 1, 0,
				    (const char *)sStalled->classes[i]->className);""",
        """				g0245d_probe_cls(i, sStalled->count, 1, 0,
				    (uintptr_t)sStalled->classes[i]->superClassLink,
				    (const char *)sStalled->classes[i]->className);""",
        "OSMetaClass: stage b",
    )

    # the walk itself: gone.
    s = sub(
        s,
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
        """				unsigned int depth = 1;
				/* g0245d v239: the depth walk is gone.
				 * v238 walked it for real and died one step in
				 * (166/167 w2 NativeAES): classes[166] is the last
				 * class, its superClassLink survived v238's
				 * ">= 0xfffffff000000000" test -- which spans 4 GB
				 * of mostly unmapped address space -- and reading
				 * that object's own link field is where the machine
				 * stops.  sDeepestClass is only used as maxDepth in
				 * applyToInstances(), so the real depth buys us
				 * nothing; the link value is printed on the pinned
				 * row as stage b instead, which is the part worth
				 * knowing, and pass 1 can finish.
				 */
				if (depth > sDeepestClass) {
				        sDeepestClass = depth;
				}""",
        "OSMetaClass: drop the walk",
    )

    # one line so the ring says the walk is off, plus a sane sDeepestClass.
    s = sub(
        s,
        """			IOLockLock(sAllClassesLock);
			for (i = 0; i < sStalled->count; i++) {
				const OSMetaClass * me = sStalled->classes[i];""",
        """			IOLockLock(sAllClassesLock);
			/* g0245d v239: applyToInstances() panics at level 0
			 * when maxDepth is 0, so keep a plausible constant now
			 * that nothing measures it any more.
			 */
			if (sDeepestClass < 8) {
			        sDeepestClass = 8;
			}
			g0245d_trace("v239 nowalk");
			for (i = 0; i < sStalled->count; i++) {
				const OSMetaClass * me = sStalled->classes[i];""",
        "OSMetaClass: nowalk marker",
    )

    s = sub(
        s,
        """					g0245d_trace_seg("v238 cls",""",
        """					g0245d_trace_seg("v239 cls",""",
        "OSMetaClass: cls label",
    )

    write(MET, s)
    print("OSMetaClass: v239 changes applied")
else:
    print("OSMetaClass: already patched")

print("v239 patch applied")
