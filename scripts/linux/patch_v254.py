#!/usr/bin/env python3
"""g0245d v254 -- give the heartbeat its own row instead of the ring's last row.

v252/v253 photos all show the same frame: ring lines 8103..8106, while the
heartbeat row reads "hb 8188".  The gap is not a hang -- it is a bug of mine:

    g0245d_con_nscroll = (rows > 3) ? rows - 3 : rows;   /* ring = rows 0..rows-4 */

and the heartbeat is drawn on `rows - 4`, which IS the last ring row.  So the
sequence is: g0245d_con_printf() writes the new trace, its newline advances the
cursor to rows-4, and g0245d_hb() immediately clears and overwrites that row
with "hb <seq>".  Every new trace erases itself.  The ring therefore always
looks frozen a few lines after the last wrap, while the heartbeat keeps
counting -- exactly what the three photos show (8103..8106 + hb 8188).

v254 shrinks the ring by one row so the four fixed rows are
    rows-1 status, rows-2 ruler, rows-3 probe, rows-4 heartbeat
and the ring is rows 0..rows-5.  It also prints "<seq>/<hb count>" so a gap
between the two numbers is visible at a glance, and adds a probe after
vfs_event_init().
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
VFSI = os.path.join(WORK, "bsd/vfs/vfs_init.c")

MARK = "g0245d v254"


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
        """	g0245d_con_nscroll = (g0245d_con_rows > 3) ?
	    g0245d_con_rows - 3 : g0245d_con_rows;""",
        """	/* g0245d v254: rows-4 is the heartbeat line and it used to be the last
	 * ring row, so each new trace was written and then immediately erased by
	 * the heartbeat.  Keep the ring at 0..rows-5; the four rows below it are
	 *   rows-1 status, rows-2 ruler, rows-3 probe, rows-4 heartbeat.
	 */
	g0245d_con_nscroll = (g0245d_con_rows > 4) ?
	    g0245d_con_rows - 4 : g0245d_con_rows;""",
        "arm_init: keep heartbeat out of the ring",
    )

    s = sub(
        s,
        """	g0245d_con_puts("hb ");
	g0245d_con_putu((unsigned long)g0245d_trace_seq, 10, 0);
	g0245d_con_sync();
	g0245d_con_row = save_row;
	g0245d_con_col = save_col;""",
        """	g0245d_con_puts("hb ");
	g0245d_con_putu((unsigned long)g0245d_trace_seq, 10, 0);
	g0245d_con_putc('/');
	g0245d_con_putu((unsigned long)++g0245d_hb_count, 10, 0);
	g0245d_con_sync();
	g0245d_con_row = save_row;
	g0245d_con_col = save_col;""",
        "arm_init: hb counter",
    )

    s = sub(
        s,
        """static void
g0245d_hb(void)
{""",
        """static unsigned long g0245d_hb_count;   /* g0245d v254 */

static void
g0245d_hb(void)
{""",
        "arm_init: hb counter var",
    )

    write(ARM, s)
    print("arm_init: v254 changes applied")
else:
    print("arm_init: already patched")

# --------------------------------------------------------------- vfs_init.c
s = read(VFSI)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v250 vfs event enter");
	vfs_event_init();
	g0245d_trace("v250 vfs event done");""",
        """	g0245d_trace("v250 vfs event enter");
	vfs_event_init();
	g0245d_probe("v254 vfs done");
	g0245d_trace("v250 vfs event done");""",
        "vfs_init: probe after vfs_event_init",
    )
    write(VFSI, s)
    print("vfs_init: v254 changes applied")
else:
    print("vfs_init: already patched")

print("v254 patch applied")
