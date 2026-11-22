#!/usr/bin/env python3
"""g0245d v278 -- bracket fbt_init/fbt_attach step by step.

v277 boot picture decoded:

  * The pseudo_inits loop ran deep: pseu 7001/8001/9001/10001 = indices
    7-10 (helper/lockstat/lockprof/sdt) all returned.  Heartbeat froze on
    label "v277 pseu" with seq 8411: the last two traces (8410, 8411) were
    two more pseu ENTRY probes -- index 11 (systrace_init) returned, and
    index 12 = fbt_init entered and never came back.  Table (generated
    ioconf.c): 0 pty 1 ptmx 2 mdev 3 bpf 4 fsevents 5 random 6 dtrace
    7 helper 8 lockstat 9 lockprof 10 sdt 11 systrace 12 FBT 13 profile.
  * fbt_blacklist_init is trivial (boot-arg + strcmp loop), so the stall is
    inside fbt_attach:  kmem_zalloc(128KB, KM_SLEEP) / dtrace_invop_add /
    ddi_create_minor_node / dtrace_register -- none of them probed.
  * No early_random checkpoint fired after fbt entry (label unchanged),
    which weakens the "allocation storm" theory: could equally be devfs
    (devfs is not mounted yet at this point -- mountroot comes later) or a
    dtrace lock.

v278 probes each step:

  1. fbt_init: "v278 fbt cdev" after cdevsw_add, "v278 fbt bl" after
     fbt_blacklist_init.
  2. fbt_attach: "v278 fbt enter" before the probetab kmem_zalloc,
     "v278 fbt zalloc" after it, "v278 fbt invop" after dtrace_invop_add,
     then the compound if is split so "v278 fbt node" prints after
     ddi_create_minor_node and "v278 fbt reg" after dtrace_register
     (semantics preserved: node failure skips register, either failure
     runs fbt_cleanup and returns DDI_FAILURE).
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

FBT = os.path.join(WORK, "bsd/dev/dtrace/fbt.c")

MARK = "g0245d v278"

TRACE = "{ extern void g0245d_trace(const char *);\n" \
        "  extern void g0245d_trace_u(const char *, unsigned int);\n" \
        "  g0245d_trace_u(\"v278 er calls\", 0); }\n"


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


s = read(FBT)
if MARK not in s:
    s = sub(
        s,
        """	int majdevno = cdevsw_add(FBT_MAJOR, &fbt_cdevsw);

	if (majdevno < 0) {
		printf("fbt_init: failed to allocate a major number!\\n");
		return;
	}

	fbt_blacklist_init();""",
        """	int majdevno = cdevsw_add(FBT_MAJOR, &fbt_cdevsw);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt cdev"); }

	if (majdevno < 0) {
		printf("fbt_init: failed to allocate a major number!\\n");
		return;
	}

	fbt_blacklist_init();
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt bl"); }""",
        "fbt: init bracketed",
    )
    s = sub(
        s,
        """	fbt_probetab_mask = fbt_probetab_size - 1;
	fbt_probetab =
	    kmem_zalloc(fbt_probetab_size * sizeof(fbt_probe_t *), KM_SLEEP);

	dtrace_invop_add(fbt_invop);

	if (ddi_create_minor_node(devi, "fbt", S_IFCHR, 0,
	    DDI_PSEUDO, 0) == DDI_FAILURE ||
	    dtrace_register("fbt", &fbt_attr, DTRACE_PRIV_KERNEL, NULL,
	    &fbt_pops, NULL, &fbt_id) != 0) {
		fbt_cleanup(devi);
		return DDI_FAILURE;
	}

	return DDI_SUCCESS;""",
        """	fbt_probetab_mask = fbt_probetab_size - 1;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt enter"); }
	fbt_probetab =
	    kmem_zalloc(fbt_probetab_size * sizeof(fbt_probe_t *), KM_SLEEP);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt zalloc"); }

	dtrace_invop_add(fbt_invop);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v278 fbt invop"); }

	/* g0245d v278: split the compound check so each half can be traced.
	 * Semantics unchanged: node failure skips register; any failure
	 * cleans up and reports DDI_FAILURE. */
	{
		int g0245d_node = ddi_create_minor_node(devi, "fbt", S_IFCHR, 0,
		    DDI_PSEUDO, 0);
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v278 fbt node"); }
		kern_return_t g0245d_reg = 0;
		if (g0245d_node == DDI_FAILURE) {
			g0245d_reg = -1;
		} else {
			g0245d_reg = dtrace_register("fbt", &fbt_attr,
			    DTRACE_PRIV_KERNEL, NULL, &fbt_pops, NULL, &fbt_id);
		}
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v278 fbt reg"); }
		if (g0245d_reg != 0) {
			fbt_cleanup(devi);
			return DDI_FAILURE;
		}
	}

	return DDI_SUCCESS;""",
        "fbt: attach fully probed",
    )
    write(FBT, s)
    print("fbt.c: init + attach probed")
else:
    print("fbt.c: already patched")

print("v278 done")
