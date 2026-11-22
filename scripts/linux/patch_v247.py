#!/usr/bin/env python3
"""g0245d v247 -- skip cpu_stack_alloc(), the next silent stop.

Both v246 photos show the same tail:

    8057 v245 oskext jettison done
    8058 machine_lockdown
    8059 v245 machine lockdown enter
    8060 v246 ml enter
    8061 v246 avp enter
    8062 v246 avp mfree1 done
    8063 v246 avp rnx enter
    8064 v246 avp rnx done
    (nothing more)
    status: >machine_lockdown

The next trace in arm_vm_prot_finalize() is "v246 avp stack alloc done",
placed immediately after cpu_stack_alloc(&BootCpuData).  So the stop is in
cpu_stack_alloc(), whose entire body is two calls:

    kmem_alloc(kernel_map, &irq_stack, INTSTACK_SIZE + ptoa(2),
        KMA_NOFAIL | KMA_PERMANENT | KMA_ZERO | KMA_GUARD_FIRST |
        KMA_GUARD_LAST | KMA_KSTACK | KMA_KOBJECT, VM_KERN_MEMORY_STACK);
    kmem_alloc(kernel_map, &exc_stack, EXCEPSTACK_SIZE + ptoa(2), ...same...);

Interrupts were enabled a few lines earlier (spllo), and kmem_alloc on
kernel_map under KMA_PERMANENT takes locks and calls pmap.  Either way, these
are *new* stacks for the switch we already skipped in v246 -- nothing uses
them.  v247 skips the allocation, keeps the original under #if 0, and marks
the next real step (the __DATA_CONST RNX) with its own pair of traces so the
same photograph tells us where the stop moved to.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AVM = os.path.join(WORK, "osfmk/arm64/arm_vm_init.c")

MARK = "g0245d v247"


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
        """/* g0245d v246: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);""",
        """/* g0245d v246/v247: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_probe_u(const char *tag, unsigned int value);""",
        "arm_vm_init: extern probe_u",
    )

    s = sub(
        s,
        """	cpu_stack_alloc(&BootCpuData);
	g0245d_trace("v246 avp stack alloc done");""",
        """	/* g0245d v247: v246 stops inside cpu_stack_alloc(), which does
	 * two kmem_alloc(kernel_map, ..., KMA_NOFAIL | KMA_PERMANENT, ...)
	 * calls -- the first heavy kmem allocation after interrupts were
	 * enabled.  The stacks it allocates feed arm64_replace_bootstack(),
	 * which v246 already skipped, so nothing needs them here.
	 */
	g0245d_probe_u("nostack", 247);
	g0245d_trace("v247 stack alloc skipped");
#if 0   /* g0245d v247: original cpu_stack_alloc(&BootCpuData); */
	cpu_stack_alloc(&BootCpuData);
	g0245d_trace("v246 avp stack alloc done");
#endif
	g0245d_trace("v247 stack done");""",
        "arm_vm_init: skip cpu_stack_alloc",
    )

    s = sub(
        s,
        """	arm_vm_page_granular_RNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);

	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();""",
        """	g0245d_trace("v247 dataconst rnx enter");
	arm_vm_page_granular_RNX(segDATACONSTB, segSizeDATACONST, ARM64_GRANULE_ALLOW_BLOCK);
	g0245d_trace("v247 dataconst rnx done");

	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();""",
        "arm_vm_init: dataconst bracket",
    )

    write(AVM, s)
    print("arm_vm_init: v247 changes applied")
else:
    print("arm_vm_init: already patched")

print("v247 patch applied")
