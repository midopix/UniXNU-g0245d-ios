#!/usr/bin/env python3
"""g0245d v246 -- open up arm_vm_prot_finalize(), especially the stack switch.

v245's photo reaches the very end of kernel_bootstrap():

    8049 v245 trust cache skipped
    8050/8051 v245 lockdown routines enter/done
    8052 OSKextRemoveKextBootstrap
    8053 v245 oskext jettison enter
    8054 v234 constructors section ... 8057 v235 sect checked
    (half line)
    status: >machine_lockdown
    pinned: 28/98 s8054 fffffff0079bd1e0

So OSKextRemoveKextBootstrap returned, kernel_bootstrap_log("machine_lockdown")
ran, and the machine stops inside machine_lockdown().

The compiled machine_lockdown() is tiny: its disassembly is just
`bl arm_vm_prot_finalize`, an optional indirect invalidate_hmac_function(),
and setting lockdown_done = 1.  KTRR/CTRR/monitor are all compiled out here,
so there is no Apple-specific register write to blame.

arm_vm_prot_finalize() does free early memory, tighten a few page ranges,
then -- critically -- `cpu_stack_alloc(&BootCpuData); arm64_replace_bootstack(&BootCpuData);`
which switches SP_EL1 to the exception stack, then frees the old BOOTDATA
pages.  A bad new stack would kill the next trace with no output, which is
exactly what the panel shows.  v246 skips the stack switch and the BOOTDATA
free that depends on it (the boot stack stays valid), and brackets every
other step so the photo says which one is responsible if it is not the stack.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AVM = os.path.join(WORK, "osfmk/arm64/arm_vm_init.c")
MR = os.path.join(WORK, "osfmk/arm64/machine_routines.c")

MARK = "g0245d v246"


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


# ----------------------------------------------------------- arm_vm_init.c
s = read(AVM)
if MARK not in s:
    s = sub(
        s,
        "#include <mach_kdp.h>",
        """#include <mach_kdp.h>

/* g0245d v246: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);""",
        "arm_vm_init: extern",
    )

    s = sub(
        s,
        """	ml_static_mfree(phystokv(gPhysBase), segLOWEST - gVirtBase);""",
        """	g0245d_trace("v246 avp enter");
	ml_static_mfree(phystokv(gPhysBase), segLOWEST - gVirtBase);
	g0245d_trace("v246 avp mfree1 done");""",
        "arm_vm_init: first free",
    )

    s = sub(
        s,
        """	arm_vm_page_granular_RNX(segPRELINKTEXTB, segSizePRELINKTEXT, ARM64_GRANULE_ALLOW_BLOCK);
	arm_vm_page_granular_RNX(segPLKDATACONSTB, segSizePLKDATACONST, ARM64_GRANULE_ALLOW_BLOCK);""",
        """	g0245d_trace("v246 avp rnx enter");
	arm_vm_page_granular_RNX(segPRELINKTEXTB, segSizePRELINKTEXT, ARM64_GRANULE_ALLOW_BLOCK);
	arm_vm_page_granular_RNX(segPLKDATACONSTB, segSizePLKDATACONST, ARM64_GRANULE_ALLOW_BLOCK);
	g0245d_trace("v246 avp rnx done");""",
        "arm_vm_init: rnx",
    )

    s = sub(
        s,
        """	cpu_stack_alloc(&BootCpuData);
	arm64_replace_bootstack(&BootCpuData);
	ml_static_mfree(phystokv(segBOOTDATAB - gVirtBase + gPhysBase), segSizeBOOTDATA);""",
        """	cpu_stack_alloc(&BootCpuData);
	g0245d_trace("v246 avp stack alloc done");
	/* g0245d v246: arm64_replace_bootstack() switches SP_EL1 to the
	 * exception stack; the next statement frees the old BOOTDATA pages,
	 * where our current stack lives.  If the new stack is not usable,
	 * the next call dies with no output -- exactly v245's symptom.
	 * Skip both for bring-up; the original boot stack stays valid.
	 * Restore as a pair once the exception stack is proven.
	 */
#if 0   /* g0245d v246: arm64_replace_bootstack(&BootCpuData); */
	g0245d_trace("v246 avp stack switch enter");
	arm64_replace_bootstack(&BootCpuData);
	g0245d_trace("v246 avp stack switch done");
#endif
	/* g0245d v246: also keep BOOTDATA mapped, since we stayed on it. */
#if 0   /* g0245d v246: ml_static_mfree(...BOOTDATA...) */
	ml_static_mfree(phystokv(segBOOTDATAB - gVirtBase + gPhysBase), segSizeBOOTDATA);
#endif
	g0245d_trace("v246 avp stack kept");""",
        "arm_vm_init: stack switch skip",
    )

    s = sub(
        s,
        """	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();
}""",
        """	__builtin_arm_dsb(DSB_ISH);
	flush_mmu_tlb();
	g0245d_trace("v246 avp done");
}""",
        "arm_vm_init: avp done",
    )

    write(AVM, s)
    print("arm_vm_init: v246 changes applied")
else:
    print("arm_vm_init: already patched")

# ------------------------------------------------------ machine_routines.c
s = read(MR)
if MARK not in s:
    s = sub(
        s,
        """machine_lockdown(void)
{
	arm_vm_prot_finalize(PE_state.bootArgs);""",
        """machine_lockdown(void)
{
	g0245d_trace("v246 ml enter");
	arm_vm_prot_finalize(PE_state.bootArgs);
	g0245d_trace("v246 ml avp done");""",
        "machine_routines: ml enter",
    )
    s = sub(
        s,
        """	if (NULL != invalidate_hmac_function) {
		invalidate_hmac_function();
	}

	lockdown_done = 1;""",
        """	if (NULL != invalidate_hmac_function) {
		g0245d_trace("v246 ml hmac enter");
		invalidate_hmac_function();
		g0245d_trace("v246 ml hmac done");
	}

	lockdown_done = 1;
	g0245d_trace("v246 ml done");""",
        "machine_routines: ml done",
    )
    # machine_routines.c has no console trace extern yet.
    s = sub(
        s,
        "#include <arm64/machine_machdep.h>",
        """#include <arm64/machine_machdep.h>

/* g0245d v246: framebuffer console trace, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);""",
        "machine_routines: extern",
    )
    write(MR, s)
    print("machine_routines: v246 changes applied")
else:
    print("machine_routines: already patched")

print("v246 patch applied")
