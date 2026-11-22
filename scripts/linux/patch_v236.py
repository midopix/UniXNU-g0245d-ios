#!/usr/bin/env python3
"""g0245d v236 -- make the console prove whether it is still advancing.

The v235 photo is self-contradictory on purpose-built evidence:

  * the pinned row reads "97 fffffff0079b9154", which decodes to this very
    build's __GLOBAL__sub_I_bootstrap.cpp (v234's was ...b90fc), so the
    walk did reach entry 97 -- all 98 constructors;
  * the scrolling area holds only "71 segment walk enter" and
    "72 structors section", with rows 2..31 blank, so the ring cannot have
    printed the eight lines that must follow section one.

Program order cannot do both.  Either the ring's row/sequence has stopped
advancing (a console bug), or the screen is left over from an earlier boot
and the device rebooted into a second one.  Those two have very different
fingerprints, so v236 puts the fingerprint on the panel:

  * the pinned row now carries "<idx>/98 s<trace_seq>", i.e. the sequence
    number at the moment the probe was drawn.  If it says s72 then the
    console is frozen at 72 while the walk keeps running; if it says s87
    then the screen is stale and the device rebooted.
  * every 8th constructor gets a ring line "v236 ctor <idx>", so a photo
    shows how far the walk actually got, independently of the pinned row.
  * g0245d_trace() re-arms the console if something clears g0245d_con_ready
    while the framebuffer base is still valid, and says so on the panel.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
OSR = os.path.join(WORK, "libkern/c++/OSRuntime.cpp")

MARK = "g0245d v236"


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
    # 1. forward declaration of the sequence counter, needed by probe_pc.
    s = sub(
        s,
        """/* g0245d v234: the same pinned row, for a raw address.""",
        """/* g0245d v236: the trace sequence, so the pinned row can say at which
 * point in the log it was drawn -- that is what separates "console frozen"
 * from "screen left over from an earlier boot".
 */
static unsigned int g0245d_trace_seq;

/* g0245d v234: the same pinned row, for a raw address.""",
        "arm_init: forward decl trace_seq")

    # 2. probe row: "<idx>/98 s<seq> <addr>"
    s = sub(
        s,
        """	g0245d_con_putu((unsigned long)idx, 10, 0);
	g0245d_con_putc(' ');
	g0245d_con_putu((unsigned long)(pc >> 48), 16, 0);""",
        """	g0245d_con_putu((unsigned long)idx, 10, 0);
	g0245d_con_putc('/');
	g0245d_con_putu(98, 10, 0);
	g0245d_con_putc(' ');
	g0245d_con_putc('s');
	/* g0245d v236: the log line number this probe belongs to. */
	g0245d_con_putu((unsigned long)g0245d_trace_seq, 10, 0);
	g0245d_con_putc(' ');
	g0245d_con_putu((unsigned long)(pc >> 48), 16, 0);""",
        "arm_init: probe row carries seq")

    # 3. the definition later in the file must not conflict.
    s = sub(
        s,
        """static unsigned int g0245d_trace_seq;

void
g0245d_trace(const char *label)
{
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_con_sync();
}""",
        """void
g0245d_trace(const char *label)
{
	/* g0245d v236: if something cleared the console's ready flag while
	 * the framebuffer is still valid, take it back instead of going
	 * silent.  Silence here would look exactly like a hang.
	 */
	if (!g0245d_con_ready && g0245d_con_base != 0) {
		g0245d_con_ready = 1;
		g0245d_con_owns_text = 1;
		g0245d_con_printf("%u v236 console rearmed\\n",
		    ++g0245d_trace_seq);
		g0245d_con_sync();
	}
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_con_sync();
}""",
        "arm_init: trace re-arms console")

    # 4. a trace that carries one unsigned value.
    s = sub(
        s,
        """void
g0245d_tracev(const char *label, unsigned long long value)""",
        """/* g0245d v236: label + one index, used to log walk progress. */
void
g0245d_trace_u(const char *label, unsigned int value)
{
	g0245d_con_printf("%u %s %u\\n", ++g0245d_trace_seq, label, value);
	g0245d_con_sync();
}

void
g0245d_tracev(const char *label, unsigned long long value)""",
        "arm_init: g0245d_trace_u")

    write(ARM, s)
    print("arm_init: v236 changes applied")
else:
    print("arm_init: already patched")

# --------------------------------------------------------------- OSRuntime.cpp
s = read(OSR)
if MARK not in s:
    s = sub(
        s,
        'extern "C" void g0245d_trace_seg(const char *label, const char *segname);',
        'extern "C" void g0245d_trace_seg(const char *label, const char *segname);\n'
        'extern "C" void g0245d_trace_u(const char *label, unsigned int value);',
        "OSRuntime: extern g0245d_trace_u")

    s = sub(
        s,
        """				unsigned int thisIdx = g0245d_structor_index++;
				g0245d_probe_pc(value, thisIdx);""",
        """				unsigned int thisIdx = g0245d_structor_index++;
				g0245d_probe_pc(value, thisIdx);
				/* g0245d v236: one ring line per 8 constructors.
				 * The pinned row alone cannot tell "the walk is
				 * still running" from "the console stopped
				 * advancing"; the ring can.
				 */
				if ((thisIdx & 7) == 0) {
					g0245d_trace_u("v236 ctor", thisIdx);
				}""",
        "OSRuntime: per-8 ctor log")

    s = sub(
        s,
        """	g0245d_trace("v234 structors done");""",
        """	g0245d_trace("v234 structors done");
	g0245d_trace_u("v236 walk done i", g0245d_structor_index);""",
        "OSRuntime: walk done with index")

    write(OSR, s)
    print("OSRuntime: v236 changes applied")
else:
    print("OSRuntime: already patched")

print("v236 patch applied")
