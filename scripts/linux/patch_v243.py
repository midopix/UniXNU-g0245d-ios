#!/usr/bin/env python3
"""g0245d v243 -- open up pgz_init(), the eighth EARLY_BOOT routine.

v241's photo shows the EARLY_BOOT ladder at 103..106 with four exact function
pointers.  Replaying the kernel's own sort offline (scripts/startup_order.py:
parse __init_entry_set, compile bsd/kern/qsort.c on the host, run the same
comparator) reproduces that order exactly:

     1 _socd_client_set_primary_kernelcache_uuid
     2 _procinit
     3 _ulock_initialize
     4 _source_pthread_bootstrap       <- photo line 103
     5 _telemetry_init                 <- 104
     6 _iotrace_init                   <- 105
     7 _vm_pageout_create_gc_thread    <- 106
     8 _pgz_init                       <- 107 (the dim line)
     9 _set_awl_scratch_exists_flag_and_subscribe_for_pm
    10 _kmem_crypto_init
    11 _cs_text_fixup_init
    12 _personas_bootstrap

Four consecutive hits make the replay trustworthy, so the stop is the eighth
routine, pgz_init() -- page guard zones, an Apple Silicon memory-protection
feature.  It either returns immediately (pgz_uses == 0, no zone opted in) or
does real work: populate zone metadata over the PGZ range, allocate backtrace
storage, then run pmap_enter_options_addr() once per slot -- and pgz_slots is
sane_size >> 22, so ~200 slots per GB here, i.e. roughly 900 pmap calls.

v242 already prints the index on the pinned row and "v243 su/ok" pairs in the
ring; this build adds the pgz ladder so the same photo also says where inside
pgz_init it stops.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

Z = os.path.join(WORK, "osfmk/kern/zalloc.c")

MARK = "g0245d v243"


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


s = read(Z)
if MARK not in s:
    # Declarations at the top of the file, outside every #if (v234/v237 lesson).
    s = sub(
        s,
        "#include <vm/vm_kern.h>",
        """#include <vm/vm_kern.h>

/* g0245d v243: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_u(const char *label, unsigned int value);""",
        "zalloc: externs",
    )

    s = sub(
        s,
        """pgz_init(void)
{
	if (!pgz_uses) {
		return;
	}
""",
        """pgz_init(void)
{
	g0245d_trace("v243 pgz enter");
	if (!pgz_uses) {
		g0245d_trace("v243 pgz off");
		return;
	}
	g0245d_trace_u("v243 pgz uses", pgz_uses);
	g0245d_trace_u("v243 pgz slots", pgz_slots);
""",
        "zalloc: pgz head",
    )

    s = sub(
        s,
        """	struct mach_vm_range *r = &zone_info.zi_pgz_range;
	zone_info.zi_pgz_meta = zone_meta_from_addr(r->min_address);
	zone_meta_populate(r->min_address, mach_vm_range_size(r));
""",
        """	struct mach_vm_range *r = &zone_info.zi_pgz_range;
	g0245d_trace("v243 pgz meta enter");
	zone_info.zi_pgz_meta = zone_meta_from_addr(r->min_address);
	zone_meta_populate(r->min_address, mach_vm_range_size(r));
	g0245d_trace("v243 pgz meta done");
""",
        "zalloc: pgz meta",
    )

    s = sub(
        s,
        """	pgz_backtraces = zalloc_permanent(sizeof(struct pgz_backtrace) *
	    2 * pgz_slots, ZALIGN_PTR);
""",
        """	g0245d_trace("v243 pgz backtrace enter");
	pgz_backtraces = zalloc_permanent(sizeof(struct pgz_backtrace) *
	    2 * pgz_slots, ZALIGN_PTR);
	g0245d_trace("v243 pgz backtrace done");
""",
        "zalloc: pgz backtrace",
    )

    s = sub(
        s,
        """	for (uint32_t slot = 0; slot < pgz_slots; slot++) {
		(void)pmap_enter_options_addr(kernel_pmap, pgz_addr(slot), 0,
		    VM_PROT_NONE, VM_PROT_NONE, 0, FALSE,
		    PMAP_OPTIONS_NOENTER, NULL);
	}
""",
        """	for (uint32_t slot = 0; slot < pgz_slots; slot++) {
		if ((slot & 63) == 0) {
			g0245d_trace_u("v243 pgz pmap", slot);
		}
		(void)pmap_enter_options_addr(kernel_pmap, pgz_addr(slot), 0,
		    VM_PROT_NONE, VM_PROT_NONE, 0, FALSE,
		    PMAP_OPTIONS_NOENTER, NULL);
	}
	g0245d_trace("v243 pgz pmap done");
""",
        "zalloc: pgz pmap loop",
    )

    s = sub(
        s,
        """	percpu_foreach(counter, pgz_sample_counter) {
		*counter = zalloc_random_uniform32(0, 2 * pgz_sample_rate);
	}
}""",
        """	g0245d_trace("v243 pgz percpu enter");
	percpu_foreach(counter, pgz_sample_counter) {
		*counter = zalloc_random_uniform32(0, 2 * pgz_sample_rate);
	}
	g0245d_trace("v243 pgz done");
}""",
        "zalloc: pgz percpu",
    )

    write(Z, s)
    print("zalloc: v243 changes applied")
else:
    print("zalloc: already patched")

print("v243 patch applied")
