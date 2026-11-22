#!/usr/bin/env python3
"""g0245d v265 -- show the newest label on the heartbeat row.

Three photos all show the same frame: one ring line "8189 v259 mc tcall enter"
and a pinned row "hb 8220/8164".  The heartbeat says the trace sequence is at
8220, 31 lines past the only visible line, so the machine is running; the ring
was cleared (row wrapped to 0) and only its first line got drawn.  Reading
progress from the ring is therefore unreliable at the moment, and we cannot
tell where the boot actually is.

v265 keeps the newest label in a static and appends it to the heartbeat row,
clipped to the row width:

    hb 8220/8164 v259 mc bkt done

One photo then reports the current stage even when the ring is blank, and also
prints rows/cols/nscroll once at console init so a bad ring geometry is
visible instead of guessed.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")

MARK = "g0245d v265"


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


s = read(ARM)
if MARK not in s:
    # 1. remember the newest label
    s = sub(
        s,
        """static unsigned long g0245d_hb_count;   /* g0245d v254 */""",
        """static unsigned long g0245d_hb_count;   /* g0245d v254 */
static const char *g0245d_last_label;   /* g0245d v265: newest trace label */""",
        "arm_init: last label var",
    )

    # 2. append the label to the heartbeat row, clipped so it cannot wrap
    s = sub(
        s,
        """	g0245d_con_putc('/');
	g0245d_con_putu((unsigned long)++g0245d_hb_count, 10, 0);
	g0245d_con_sync();""",
        """	g0245d_con_putc('/');
	g0245d_con_putu((unsigned long)++g0245d_hb_count, 10, 0);
	/* g0245d v265: the ring can be cleared mid-wrap, leaving no readable
	 * newest line.  Append the label here, clipped so it never wraps.
	 */
	if (g0245d_last_label != 0) {
		unsigned int n = 0;
		g0245d_con_puts(" ");
		while (g0245d_last_label[n] != '\\0' && n < 40 &&
		    g0245d_con_col + 1 < g0245d_con_cols) {
			g0245d_con_putc(g0245d_last_label[n++]);
		}
	}
	g0245d_con_sync();""",
        "arm_init: hb label",
    )

    # 3. record it in every trace entry point
    s = sub(
        s,
        """	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_hb();""",
        """	g0245d_last_label = label;
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_hb();""",
        "arm_init: trace records label",
    )

    # 4. one-time geometry report
    s = sub(
        s,
        """	g0245d_con_ready = 1;
	g0245d_con_owns_text = 1;
	for (r = 0; r < g0245d_con_rows; r++) {
		g0245d_con_fill_row(r);
	}
	g0245d_con_sync();""",
        """	g0245d_con_ready = 1;
	g0245d_con_owns_text = 1;
	for (r = 0; r < g0245d_con_rows; r++) {
		g0245d_con_fill_row(r);
	}
	g0245d_con_sync();
	/* g0245d v265: record the ring geometry once, so a bad rows/nscroll
	 * value is visible instead of having to be inferred from behaviour.
	 */
	g0245d_con_row = 0;
	g0245d_con_col = 0;
	g0245d_con_printf("%u v265 geom rows %u cols %u nscroll %u\\n",
	    ++g0245d_trace_seq, g0245d_con_rows, g0245d_con_cols,
	    g0245d_con_nscroll);
	g0245d_con_sync();""",
        "arm_init: geometry report",
    )

    write(ARM, s)
    print("arm_init: v265 changes applied")
else:
    print("arm_init: already patched")

print("v265 patch applied")
