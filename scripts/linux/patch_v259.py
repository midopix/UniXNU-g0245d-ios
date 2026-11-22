#!/usr/bin/env python3
"""g0245d v259 -- open up mcache_init() statement by statement.

v258's photo:

    8174 bsd calling proc_uuid_policy_init()
    8175 v256 hi elements 64
    8176 v256 hi size 64
    8177 v256 hi alloc enter
    8178 v256 hi alloc ret 0xfffffff41973bc00
    8179 v250 mcache enter        (this is the v258 bracket)
    (dark rows)
    hb 8181/8126

so ml_wait_max_cpus() is no longer the wall (the bracket was reached, which is
*after* the v258 fix let lockdown declare max_cpus), and mcache_init() prints
its entry but never "v258 mcache done".  The body is:

    ncpu = ml_wait_max_cpus();
    (void) mcache_cache_line_size();
    mcache_reap_tcall  = thread_call_allocate(...);
    mcache_update_tcall= thread_call_allocate(...);
    mcache_zone = zone_create("mcache", MCACHE_ALLOC_SIZE,
                              ZC_PGZ_USE_GUARDS | ZC_DESTRUCTIBLE);
    LIST_INIT(&mcache_head);
    for (each bkttype) mcache_create(name, ...);
    mcache_audit_cache = mcache_create("audit", ...);
    mcache_applyall(mcache_cache_bkt_enable);
    mcache_ready = 1;

Candidates: thread_call_allocate (zone/Z_WAITOK), zone_create with
ZC_PGZ_USE_GUARDS (page-guard zones, which this bring-up only half-initialised),
and mcache_applyall which sizes per-CPU bucket arrays.  v259 brackets every one
of them.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MC = os.path.join(WORK, "bsd/kern/mcache.c")

MARK = "g0245d v259"


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


s = read(MC)
if MARK not in s:
    s = sub(
        s,
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v259: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);""",
        "mcache: externs",
    )

    s = sub(
        s,
        """	ncpu = ml_wait_max_cpus();
	(void) mcache_cache_line_size();        /* prime it */

	mcache_reap_tcall = thread_call_allocate(mcache_reap_timeout, NULL);
	mcache_update_tcall = thread_call_allocate(mcache_update, NULL);""",
        """	g0245d_trace("v259 mc wait enter");
	ncpu = ml_wait_max_cpus();
	g0245d_trace_u("v259 mc ncpu", ncpu);
	(void) mcache_cache_line_size();        /* prime it */
	g0245d_trace("v259 mc line done");

	g0245d_trace("v259 mc tcall enter");
	mcache_reap_tcall = thread_call_allocate(mcache_reap_timeout, NULL);
	mcache_update_tcall = thread_call_allocate(mcache_update, NULL);
	g0245d_trace("v259 mc tcall done");""",
        "mcache: wait/cacheline/tcall",
    )

    s = sub(
        s,
        """	mcache_zone = zone_create("mcache", MCACHE_ALLOC_SIZE,
	    ZC_PGZ_USE_GUARDS | ZC_DESTRUCTIBLE);

	LIST_INIT(&mcache_head);""",
        """	g0245d_trace("v259 mc zone enter");
	mcache_zone = zone_create("mcache", MCACHE_ALLOC_SIZE,
	    ZC_PGZ_USE_GUARDS | ZC_DESTRUCTIBLE);
	g0245d_trace("v259 mc zone done");

	LIST_INIT(&mcache_head);""",
        "mcache: zone_create",
    )

    s = sub(
        s,
        """		btp->bt_cache = mcache_create(name,
		    (btp->bt_bktsize + 1) * sizeof(void *), 0, 0, MCR_SLEEP);
	}""",
        """		g0245d_trace_u("v259 mc bkt", i);
		btp->bt_cache = mcache_create(name,
		    (btp->bt_bktsize + 1) * sizeof(void *), 0, 0, MCR_SLEEP);
	}
	g0245d_trace("v259 mc bkt done");""",
        "mcache: bkt loop",
    )

    s = sub(
        s,
        """	mcache_audit_cache = mcache_create("audit", sizeof(mcache_audit_t),
	    0, 0, MCR_SLEEP);

	mcache_applyall(mcache_cache_bkt_enable);
	mcache_ready = 1;""",
        """	g0245d_trace("v259 mc audit enter");
	mcache_audit_cache = mcache_create("audit", sizeof(mcache_audit_t),
	    0, 0, MCR_SLEEP);
	g0245d_trace("v259 mc audit done");

	g0245d_trace("v259 mc applyall enter");
	mcache_applyall(mcache_cache_bkt_enable);
	g0245d_trace("v259 mc applyall done");
	mcache_ready = 1;""",
        "mcache: audit/applyall",
    )

    write(MC, s)
    print("mcache: v259 changes applied")
else:
    print("mcache: already patched")

print("v259 patch applied")
