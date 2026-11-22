#!/usr/bin/env python3
"""g0245d v263 -- fix the reported physical memory size.

v262's photo prints the two numbers that explain a long list of failures:

    8207 v261 mbi nmbclusters 128
    8208 v262 sane_size MB 38
    8209 v262 max_mem MB 56
    8214 v261 mbi slab done

The machine has 4 GB of DRAM, but VM thinks it has 38 MB usable / 56 MB total.
Every size-derived default collapsed with it:

  * pgz_slots 9          (sane_size >> 22)
  * nmbclusters 128      (instead of 16384)
  * maxslabgrp 0         (rounds to zero MB)
  * hashinit(16384) failing in Z_NOWAIT and needing the static fallback

The source is osfmk/arm64/arm_vm_init.c:1924:

    gPhysSize = mem_size = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase;

args->memSize comes from the bootloader, and this bootloader evidently reports
only the span it loaded the kernel into (56 MB) rather than the DRAM window.
Since mem_size drives the physmap, the page tables and every accounting
default, v263 clamps it up when the reported value is implausibly small --
and prints the raw inputs so the next photo documents what the shim sent.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AVM = os.path.join(WORK, "osfmk/arm64/arm_vm_init.c")

MARK = "g0245d v263"


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


s = read(AVM)
if MARK not in s:
    s = sub(
        s,
        """	gPhysSize = mem_size = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase;

	mem_actual = args->memSizeActual ? args->memSizeActual : mem_size;""",
        """	g0245d_trace_u("v263 boot memSize MB", (unsigned int)(args->memSize >> 20));
	g0245d_tracev("v263 gPhysBase", (unsigned long long)gPhysBase);
	gPhysSize = mem_size = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase;

	/* g0245d v263: the shim reports only the kernel's own span as memSize
	 * (56 MB), so VM believes the machine has 38 MB usable.  That single
	 * number collapses every size-derived default: pgz slots 9,
	 * nmbclusters 128, maxslabgrp 0, and hashinit(Z_NOWAIT) failing.  When
	 * the report is implausibly small, clamp up to the real DRAM window
	 * (0x80000000..0x100000000 on this SoC), capped so the physmap stays
	 * within what the bootstrap tables can describe.
	 */
	if (mem_size < (256ULL * 1024 * 1024)) {
		uint64_t forced = 0x100000000ULL - (uint64_t)gPhysBase;
		if (forced > (1536ULL * 1024 * 1024)) {
			forced = 1536ULL * 1024 * 1024;
		}
		if (forced < (512ULL * 1024 * 1024)) {
			forced = 512ULL * 1024 * 1024;
		}
		g0245d_trace_u("v263 memSize forced MB", (unsigned int)(forced >> 20));
		mem_size = forced;
		gPhysSize = forced;
		args->memSize = forced;
		args->memSizeActual = forced;
	}

	mem_actual = args->memSizeActual ? args->memSizeActual : mem_size;""",
        "arm_vm_init: clamp mem_size",
    )
    write(AVM, s)
    print("arm_vm_init: v263 changes applied")
else:
    print("arm_vm_init: already patched")

print("v263 patch applied")
