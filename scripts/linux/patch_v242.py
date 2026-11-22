#!/usr/bin/env python3
"""g0245d v242 -- make the startup-routine counter readable in a dim photo.

v241's photo is a big step: it reaches the EARLY_BOOT startup ladder and runs
twelve routines of it.  The status row says >early_boot, the pinned row says
"14 v241 nouuid" (so the uuid skip worked and fromPath("/chosen") is confirmed
as the previous stop), and the ring holds

    103 v241 startup fn 0xfffffff0079a5e60   _source_pthread_bootstrap
    104 v241 startup fn 0xfffffff0079a6250   _telemetry_init
    105 v241 startup fn 0xfffffff0079acd48   _iotrace_init
    106 v241 startup fn 0xfffffff0079af9cc   _vm_pageout_create_gc_thread
    107 (very dim, only the tops of the digits)

so the EARLY_BOOT phase (subsystem 16) is running and stops in the routine
after _vm_pageout_create_gc_thread.  The kernel has exactly twelve EARLY_BOOT
entries, so the field is small -- but the 38-character address line is exactly
the line that goes dim in the photo, which is why v242 changes the *shape* of
the output rather than adding more of it:

  * the pinned row (crisp in every photo so far) gets "su <idx> <8 hex>",
    redrawn before every routine, so the last one is always legible;
  * the ring gets a short "v242 su <idx>" before and "v242 ok <idx>" after each
    routine, so a stop is either "inside routine N" or "after routine N".

Twelve entries also means we can enumerate them offline; the index is enough to
name the victim once the build is done.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
START = os.path.join(WORK, "osfmk/kern/startup.c")

MARK = "g0245d v242"


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
g0245d_probe_cls(unsigned int idx, unsigned int total, unsigned int stage,""",
        """/* g0245d v242: <index> <low 32 bits of a function pointer> on the pinned
 * row.  The ring line that names a startup routine is 38 characters and is
 * exactly the line that turns to fuzz when the machine dies mid-flush; the
 * pinned row is redrawn whole every time and has stayed legible in every
 * photo so far.
 */
void
g0245d_probe_fn(unsigned int idx, unsigned long long fn)
{
	unsigned int row;
	unsigned int col;
	unsigned int i;
	unsigned int d;

	if (!g0245d_con_ready || g0245d_con_rows < 5) {
		return;
	}
	row = g0245d_con_row;
	col = g0245d_con_col;
	g0245d_con_row = g0245d_con_rows - 4;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	g0245d_con_puts("su ");
	g0245d_con_putu((unsigned long)idx, 10, 0);
	g0245d_con_putc(' ');
	for (i = 0; i < 8; i++) {
		d = (unsigned int)((fn >> (28 - 4 * (int)i)) & 0xf);
		g0245d_con_putc((char)(d < 10 ? '0' + d : 'a' + d - 10));
	}
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}

void
g0245d_probe_cls(unsigned int idx, unsigned int total, unsigned int stage,""",
        "arm_init: g0245d_probe_fn",
    )
    write(ARM, s)
    print("arm_init: v242 changes applied")
else:
    print("arm_init: already patched")

# ---------------------------------------------------------------- startup.c
s = read(START)
if MARK not in s:
    s = sub(
        s,
        """extern void g0245d_tracev(const char *label, unsigned long long value);""",
        """extern void g0245d_tracev(const char *label, unsigned long long value);
extern void g0245d_trace_u(const char *label, unsigned int value);
extern void g0245d_probe_fn(unsigned int idx, unsigned long long fn);""",
        "startup: externs",
    )

    s = sub(
        s,
        """	struct startup_entry *cur = startup_entry_cur;""",
        """	struct startup_entry *cur = startup_entry_cur;
	static unsigned int g0245d_su;   /* g0245d v242: routines run so far */""",
        "startup: counter",
    )

    s = sub(
        s,
        """		/* g0245d v241: name the routine before running it.  kernel_bootstrap_log
		 * only names the subsystem, and a subsystem can hold dozens of routines.
		 * The value is the function pointer, resolved offline with llvm-nm.
		 */
		g0245d_tracev("v241 startup fn", (unsigned long long)cur->func);
		cur->func(cur->arg);""",
        """		/* g0245d v242: no more 38-character address lines in the ring --
		 * that is exactly the line the photo loses.  Short index before and
		 * after the call, plus index+address on the pinned row.
		 */
		++g0245d_su;
		g0245d_probe_fn(g0245d_su, (unsigned long long)cur->func);
		g0245d_trace_u("v242 su", g0245d_su);
		cur->func(cur->arg);
		g0245d_trace_u("v242 ok", g0245d_su);""",
        "startup: index pair",
    )

    write(START, s)
    print("startup: v242 changes applied")
else:
    print("startup: already patched")

print("v242 patch applied")
