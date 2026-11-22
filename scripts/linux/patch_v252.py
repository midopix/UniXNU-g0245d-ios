#!/usr/bin/env python3
"""g0245d v252 -- heartbeat on the pinned row plus a real bracket inside vfs_event_init.

v251's photo settles the v250 "regression": it did NOT stop at 8071.  The
panel now reads

    8093 v250 vntblinit done
    8104 v250 vfs event enter
    (faint third line)

so both v250 and v251 run well past 8071; that earlier report was another
photo-timing artifact.  The new stop is at vfs_event_init(), whose entire body
is klist_init(&fs_klist) -> SLIST_INIT(list): a single store, which cannot
hang.  Either the photo is again early, or the console stops updating after
that store for a different reason.

v252 makes the next photo decisive in two independent ways:

  * g0245d_trace() writes the current trace sequence to the pinned row
    (rows-4) on every call.  A frozen ring with an advancing pinned row means
    the panel is not repainting that region, not that the CPU stopped.
  * vfs_event_init() and nchinit() get before/after probes on rows-3, a
    separate row, so we can see exactly which call returned.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
SUBR = os.path.join(WORK, "bsd/vfs/vfs_subr.c")
VFSI = os.path.join(WORK, "bsd/vfs/vfs_init.c")

MARK = "g0245d v252"


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
        """	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);
	g0245d_con_sync();""",
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
	g0245d_con_col = 0;""",
        "arm_init: heartbeat",
    )
    write(ARM, s)
    print("arm_init: v252 changes applied")
else:
    print("arm_init: already patched")

# --------------------------------------------------------------- vfs_subr.c
s = read(SUBR)
if MARK not in s:
    s = sub(
        s,
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v252: framebuffer console probes, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_probe(const char *label);""",
        "vfs_subr: externs",
    )
    s = sub(
        s,
        """vfs_event_init(void)
{
	klist_init(&fs_klist);
}""",
        """vfs_event_init(void)
{
	g0245d_trace("v252 klist enter");
	klist_init(&fs_klist);
	g0245d_probe("v252 klist done");
	g0245d_trace("v252 klist done");
}""",
        "vfs_subr: klist bracket",
    )
    write(SUBR, s)
    print("vfs_subr: v252 changes applied")
else:
    print("vfs_subr: already patched")

# --------------------------------------------------------------- vfs_init.c
s = read(VFSI)
if MARK not in s:
    s = sub(
        s,
        """	g0245d_trace("v250 nchinit enter");
	nchinit();
	g0245d_trace("v250 nchinit done");""",
        """	g0245d_trace("v250 nchinit enter");
	nchinit();
	g0245d_probe("v252 nch done");
	g0245d_trace("v250 nchinit done");""",
        "vfs_init: nch probe",
    )
    write(VFSI, s)
    print("vfs_init: v252 changes applied")
else:
    print("vfs_init: already patched")

print("v252 patch applied")
