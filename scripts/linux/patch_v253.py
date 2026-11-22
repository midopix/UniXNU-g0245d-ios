#!/usr/bin/env python3
"""g0245d v253 -- fix the v252 heartbeat so it stops corrupting the ring.

v252's photo answered both questions and exposed a bug of mine:

  * "hb 8188" on the pinned row, while the ring's newest line is around 8109:
    the trace sequence has advanced 79 lines past anything visible, so the
    machine is NOT stopped at vfs_event_init -- it keeps running.
  * "15 v252 klist done" on the probe row: klist_init() returned, confirming
    that the one-statement function was never the wall.
  * But the ring is scrambled: bsd stage lines 8093..8100 sit above
    constructor lines 7955..7959 and above su/ok pairs.  Cause: v252's
    heartbeat ends with

        g0245d_con_row = 0;
        g0245d_con_col = 0;

    which throws away the cursor position that g0245d_con_printf() had already
    advanced.  Every trace therefore restarts at row 0 and the ring wraps in
    the wrong order.

v253 saves and restores row/col around the heartbeat, and adds the same
heartbeat to g0245d_trace_lit()/g0245d_tracev()/g0245d_trace_u() so bsd
stage lines and value traces also tick it.  No boot behaviour changes.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")

MARK = "g0245d v253"


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


HEARTBEAT = """/* g0245d v252/v253: heartbeat on the pinned row.  Redrawn on every trace,
 * so its number keeps climbing even while a photo catches the ring between
 * two lines.  Row/col must be saved and restored: g0245d_con_printf() has
 * already advanced the cursor and resetting it to 0 scrambles the ring.
 */
static void
g0245d_hb(void)
{
	unsigned int    save_row = g0245d_con_row;
	unsigned int    save_col = g0245d_con_col;

	if (!g0245d_con_ready || g0245d_con_rows < 5) {
		return;
	}
	g0245d_con_row = g0245d_con_rows - 4;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	g0245d_con_puts("hb ");
	g0245d_con_putu((unsigned long)g0245d_trace_seq, 10, 0);
	g0245d_con_sync();
	g0245d_con_row = save_row;
	g0245d_con_col = save_col;
}

"""

s = read(ARM)
if MARK not in s:
    # 1. drop v252's inline heartbeat and put the fixed helper above g0245d_trace
    s = sub(
        s,
        """	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	/* g0245d v252: heartbeat.  The ring can look frozen when a photo is
	 * taken between two traces; the pinned row is redrawn on every call,
	 * so an advancing number there proves the CPU is still running.
	 */
	g0245d_con_row = g0245d_con_rows - 4;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	g0245d_con_puts("hb ");
	g0245d_con_putu((unsigned long)g0245d_trace_seq, 10, 0);
	g0245d_con_sync();
	g0245d_con_row = 0;
	g0245d_con_col = 0;
}""",
        """	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_hb();
}""",
        "arm_init: fix heartbeat",
    )

    # 2. helper definition goes immediately before g0245d_trace
    s = sub(
        s,
        """void
g0245d_trace(const char *label)""",
        HEARTBEAT + """void
g0245d_trace(const char *label)""",
        "arm_init: heartbeat helper",
    )

    # 3. tick the heartbeat from the other three trace entry points too
    s = sub(
        s,
        """	g0245d_con_printf("%u %s %u\\n", ++g0245d_trace_seq, label, value);
	g0245d_con_sync();""",
        """	g0245d_con_printf("%u %s %u\\n", ++g0245d_trace_seq, label, value);
	g0245d_con_sync();
	g0245d_hb();""",
        "arm_init: trace_u heartbeat",
    )
    s = sub(
        s,
        """	buf[i] = '\\0';
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, buf);
	g0245d_con_sync();""",
        """	buf[i] = '\\0';
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, buf);
	g0245d_con_sync();
	g0245d_hb();""",
        "arm_init: trace_lit heartbeat",
    )

    write(ARM, s)
    print("arm_init: v253 changes applied")
else:
    print("arm_init: already patched")

print("v253 patch applied")
