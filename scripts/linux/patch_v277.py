#!/usr/bin/env python3
"""g0245d v277 -- bracket bsd_autoconf's three sub-steps.

v276 boot picture decoded (major progress):

  * The AES stub worked.  Boot sailed through tcp_init (probes scrolled off
    screen), all remaining prinit dispatches (58/58/6/2/0 -- second-domain
    passes whose inits early-return silently), skywalk_init (hashinit 64
    buckets OK, caller resolves to _necp_init+0xd2), memorystatus_freeze_init,
    memorystatus_init, sysctl_mib_init.
  * Last stage line: "bsd calling bsd_autoconf" (seq 8394).  The stages that
    follow it in bsd_init (loopattach, ether_family_init, net_init_run, ...)
    never printed, so the stall is INSIDE bsd_autoconf, which has three
    sub-steps and no probes:
      kminit()                -- ttymalloc + makedev
      pseudo_inits loop       -- pseudo-device inits (zones, devfs, pty, ...)
      IOKitBSDInit()          -- publishResource("IOBSD")
  * Heartbeat label froze on "v274 er calls", i.e. >=1024 early_random calls
    happened after bsd_autoconf was entered -- consistent with zone-heavy
    pseudo-device init.

v277 instruments each sub-step:

  1. bsd_init.c: "v277 kminit done" after kminit(); per-iteration
     "v277 pseu <index*1000+count>" inside the pseudo_inits loop plus a
     final "v277 pseu done".
  2. km.c (arm): "v277 km tty" between ttymalloc and makedev.
  3. IOKitBSDInit.cpp: "v277 ioi enter" at entry, "v277 ioi pub" after
     publishResource("IOBSD").
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "bsd/kern/bsd_init.c")
KM = os.path.join(WORK, "bsd/dev/arm/km.c")
IOI = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")

MARK = "g0245d v277"


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


# ------------------------------------------------------------- bsd_init.c
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """	kprintf("bsd_autoconf: calling kminit\\n");
	kminit();""",
        """	kprintf("bsd_autoconf: calling kminit\\n");
	kminit();
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v277 kminit done"); }""",
        "bsd_init: after kminit",
    )
    s = sub(
        s,
        """	{
		struct pseudo_init *pi;

		for (pi = pseudo_inits; pi->ps_func; pi++) {
			(*pi->ps_func)(pi->ps_count);
		}
	}""",
        """	{
		struct pseudo_init *pi;
		int g0245d_pseu_i = 0;

		for (pi = pseudo_inits; pi->ps_func; pi++) {
			/* g0245d v277: value = index*1000 + unit count. */
			{ extern void g0245d_trace_u(const char *, unsigned int);
			  g0245d_trace_u("v277 pseu",
			      (unsigned)(g0245d_pseu_i * 1000 + pi->ps_count)); }
			(*pi->ps_func)(pi->ps_count);
			g0245d_pseu_i++;
		}
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v277 pseu done"); }
	}""",
        "bsd_init: pseudo_inits loop probed",
    )
    write(BSDINIT, s)
    print("bsd_init.c: bsd_autoconf sub-steps probed")
else:
    print("bsd_init.c: already patched")

# ----------------------------------------------------------------- km.c
s = read(KM)
if MARK not in s:
    s = sub(
        s,
        """	km_tty[0] = ttymalloc();
	km_tty[0]->t_dev = makedev(12, 0);""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v277 km enter"); }
	km_tty[0] = ttymalloc();
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v277 km tty"); }
	km_tty[0]->t_dev = makedev(12, 0);""",
        "km: kminit bracketed",
    )
    write(KM, s)
    print("km.c: kminit bracketed")
else:
    print("km.c: already patched")

# -------------------------------------------------------- IOKitBSDInit.cpp
s = read(IOI)
if MARK not in s:
    s = sub(
        s,
        """IOKitBSDInit( void )
{
	IOService::publishResource("IOBSD");""",
        """IOKitBSDInit( void )
{
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v277 ioi enter"); }
	IOService::publishResource("IOBSD");
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v277 ioi pub"); }""",
        "IOKitBSDInit: entry + publish bracketed",
    )
    write(IOI, s)
    print("IOKitBSDInit.cpp: bracketed")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v277 done")
