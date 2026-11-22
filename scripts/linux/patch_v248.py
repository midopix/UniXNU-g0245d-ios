#!/usr/bin/env python3
"""g0245d v248 -- trace the BSD init stage ladder.

v247's photo reaches the end of the lockdown chain:

    8071 v246 avp done
    8072 v246 ml avp done
    8073 v246 ml done
    8074 v245 machine lockdown done
    8075 kernel_do_post - done
    8076 PE_lockdown_iokit
    8077 v245 PE lockdown enter
    8078 v245 start matching enter
    8079 v245 matching call enter
    8080 v245 matching call done
    8081 v245 start matching done
    8082 v245 PE lockdown done
    status: >PE_lockdown_iokit

So machine_lockdown, OSKextRemoveKextBootstrap, KTRR-free page tightening,
IOKit matching and PE_lockdown_iokit() are all behind us.  The next statements
in kernel_bootstrap() are vm_set_restrictions(), kperf_init_early() and
bsd_init(), with no trace on any of them.

bsd_init() is 1200 lines, but it already calls bsd_init_kprintf() at 47 named
points -- all of them plain string literals like "calling kauth_init\n".  With
DEBUG_BSDINIT == 0 that macro expands to boot_progress_stage(), which is
invisible on our console.  v248 adds a one-line trace to that macro, so the
existing 47 stage names become breadcrumbs without touching the body of
bsd_init(), and brackets the three calls in kernel_bootstrap() as well.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
START = os.path.join(WORK, "osfmk/kern/startup.c")
BSD = os.path.join(WORK, "bsd/kern/bsd_init.c")

MARK = "g0245d v248"


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
g0245d_tracev(const char *label, unsigned long long value)""",
        """/* g0245d v248: a trace whose label is a plain string literal, possibly
 * carrying a trailing newline (bsd_init's stage names do).  Copy at most 48
 * bytes and stop at the newline, so each stage still occupies one ring row.
 */
void
g0245d_trace_lit(const char *s)
{
	char           buf[49];
	unsigned int   i;

	if (!g0245d_con_ready || s == 0) {
		return;
	}
	for (i = 0; i < 48 && s[i] != '\\0' && s[i] != '\\n'; i++) {
		buf[i] = s[i];
	}
	buf[i] = '\\0';
	g0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, buf);
	g0245d_con_sync();
}

void
g0245d_tracev(const char *label, unsigned long long value)""",
        "arm_init: g0245d_trace_lit",
    )
    write(ARM, s)
    print("arm_init: v248 changes applied")
else:
    print("arm_init: already patched")

# ---------------------------------------------------------------- startup.c
s = read(START)
if MARK not in s:
    s = sub(
        s,
        """	vm_set_restrictions(machine_info.max_cpus);


#if KPERF
	kperf_init_early();
#endif

	/*
	 *	Start the user bootstrap.
	 */
#ifdef  MACH_BSD
	bsd_init();
#endif""",
        """	g0245d_trace("v248 vm restrictions enter");
	vm_set_restrictions(machine_info.max_cpus);
	g0245d_trace("v248 vm restrictions done");

#if KPERF
	g0245d_trace("v248 kperf enter");
	kperf_init_early();
	g0245d_trace("v248 kperf done");
#endif

	/*
	 *	Start the user bootstrap.
	 */
#ifdef  MACH_BSD
	g0245d_trace("v248 bsd init enter");
	bsd_init();
	g0245d_trace("v248 bsd init done");
#endif""",
        "startup: bracket pre-bsd and bsd_init",
    )
    write(START, s)
    print("startup: v248 changes applied")
else:
    print("startup: already patched")

# ------------------------------------------------------------- bsd_init.c
s = read(BSD)
if MARK not in s:
    s = sub(
        s,
        """	boot_progress_stage("bsd_init enter");""",
        """	boot_progress_stage("bsd_init enter");
	extern void g0245d_trace(const char *label);
	g0245d_trace("v248 bsd body enter");""",
        "bsd_init: enter",
    )
    s = sub(
        s,
        """#if DEBUG_BSDINIT
#define bsd_init_kprintf(x, ...) kprintf("bsd_init: " x, ## __VA_ARGS__)
#else
#define bsd_init_kprintf(x, ...) boot_progress_stage("bsd_init: " x)
#endif""",
        """#if DEBUG_BSDINIT
#define bsd_init_kprintf(x, ...) kprintf("bsd_init: " x, ## __VA_ARGS__)
#else
/* g0245d v248: the stage names are plain literals; replay them on the panel
 * in addition to boot_progress_stage(), which our console cannot see.
 */
extern void g0245d_trace_lit(const char *s);
#define bsd_init_kprintf(x, ...) do {                                   \\
        g0245d_trace_lit("bsd " x);                                     \\
        boot_progress_stage("bsd_init: " x);                            \\
} while (0)
#endif""",
        "bsd_init: stage macro",
    )
    write(BSD, s)
    print("bsd_init: v248 changes applied")
else:
    print("bsd_init: already patched")

print("v248 patch applied")
