#!/usr/bin/env python3
"""g0245d v251 -- decisive markers around the arm_vm_prot_finalize epilogue.

v250's panel stays at 8071 v246 avp done even after a 15-second wait and a
fresh boot, while v249 went on to 8098.  But v249 and v250 have byte-identical
segment tables, identical kernel.macho size, and identical addresses for
machine_lockdown, arm_vm_prot_finalize and every console variable.  v250 only
added traces in bsd_init.c and vfs_init.c, which cannot run at 8071.

In v246, "v246 avp done" is the very last statement of arm_vm_prot_finalize,
placed after __builtin_arm_dsb(DSB_ISH) and flush_mmu_tlb().  The next trace is
"v246 ml avp done" at the call site in machine_lockdown().  So a stop on that
line means "somewhere between the final statement and the return", which for
a C function is just the epilogue -- or the console lost the ability to show
later lines.

v251 adds two bracket traces around the dsb/flush pair and one on the pinned
row, so one photo answers all three questions:

  * no v251 marker at all        -> the phone is not booting this kernel
  * v251 before flush, no after  -> the dsb / flush_mmu_tlb() is where it dies
  * v251 after flush, no avp done -> the final call/return path is the stop
  * all markers plus later lines -> the earlier photos were stale, boot is fine
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AVM = os.path.join(WORK, "osfmk/arm64/arm_vm_init.c")

MARK = "g0245d v251"


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
        """	g0245d_trace("v247 dataconst rnx done");

	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();
	g0245d_trace("v246 avp done");""",
        """	g0245d_trace("v247 dataconst rnx done");

	/* g0245d v251: bracket the last two operations, then leave a marker
	 * on the pinned row as a second channel in case the ring stops.
	 */
	g0245d_probe_u("v251", 251);
	g0245d_trace("v251 before flush");
	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();
	g0245d_trace("v251 after flush");
	g0245d_trace("v246 avp done");""",
        "arm_vm_init: flush bracket",
    )
    write(AVM, s)
    print("arm_vm_init: v251 changes applied")
else:
    print("arm_vm_init: already patched")

print("v251 patch applied")
