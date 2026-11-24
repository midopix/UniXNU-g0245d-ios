#!/usr/bin/env python3
"""g0245d v351 -- step through the fatal pmap switch, and capture the fault.

What v349 proved (from the on-screen trace ring):

    v349 vs old 0xffffffff03890a7e0
    v349 pmap ttep 0x96c3b808
    v349 pmap asid 0x1

The target pmap is *alive*: its translation table root is non-zero and its
hardware ASID is 1 (pmap_alloc_id() hands out ASIDs starting at 1, ASID 0
is reserved for the kernel).  So the "ttep == 0 means the pmap was
destroyed" hypothesis is wrong and the v349 guard never fires.  The fault
is inside pmap_switch_internal().

v351 does three things at once:

 1. vm_map_switch() numbers its calls, so the photo says *which* switch
    faulted.  exec_mach_imgact() calls it twice on the success path: once
    to enter the new map for the copyout window, once to come back.

 2. pmap_switch_internal() marks every step boundary, through
    g0245d_tracev() so the markers survive in the trace ring.  The last
    marker that made it to the ring names the statement that faulted.

 3. sleh_synchronous_sp1() traces the ESR, the FAR and the PC.  The panic
    text does not fit on the console row, so a photo only ever shows a
    truncated "Synchronous exception taken while SP1 selected at pc 0x...".
    The FAR is the address that actually faulted, which is what tells
    "the MMU walked a bad page table" from "the CPU executed a bad
    pointer".

Every step is applied independently and each file is written as soon as it
is patched, so a failure half way through leaves a tree that the next run
can continue from.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PMAPC = os.path.join(W, 'osfmk/arm/pmap/pmap.c')
SLEH = os.path.join(W, 'osfmk/arm64/sleh.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')


def apply(text, old, new, what, marker=None):
    """Replace one occurrence, tolerating an already-patched file."""
    if (marker or what) in text:
        print('  %-22s already applied' % what)
        return text
    n = text.count(old)
    assert n == 1, '%s: found %d matches' % (what, n)
    print('  %-22s patched' % what)
    return text.replace(old, new, 1)


def trace(label):
    return ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
            '\t  g0245d_tracev("%s", (unsigned long long)(uintptr_t)0); }\n' % label)


# ---------------------------------------------------------------- vm_map.c
v = open(VMAP, encoding='utf-8').read()
A0 = ('\tthread_t        thread = current_thread();\n'
      '\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v349 vs map", (unsigned long long)(uintptr_t)map);\n'
      '\t  g0245d_tracev("v349 vs old", (unsigned long long)(uintptr_t)oldmap); }\n')
B0 = ('\tthread_t        thread = current_thread();\n'
      '\tvm_map_t        oldmap = thread->map;\n'
      '\t/* g0245d v351: number the switches.  exec_mach_imgact() calls\n'
      '\t * vm_map_switch() twice on the success path (once to enter the new\n'
      '\t * map for the copyout window, once to come back), and the photo has\n'
      '\t * to say which of them faulted. */\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  static unsigned int v351_vsn = 0;\n'
      '\t  g0245d_tracev("v351 vs call", (unsigned long long)(++v351_vsn));\n'
      '\t  g0245d_tracev("v351 vs map", (unsigned long long)(uintptr_t)map);\n'
      '\t  g0245d_tracev("v351 vs old", (unsigned long long)(uintptr_t)oldmap); }\n')
v = apply(v, A0, B0, 'vm_map.c vs counter', 'v351 vs call')
open(VMAP, 'w', encoding='utf-8').write(v)

# ------------------------------------------------------- arm/pmap/pmap.c
p = open(PMAPC, encoding='utf-8').read()

A1 = ('\tif (__improbable((asid_index == 0) && (pmap != kernel_pmap))) {\n'
      '\t\tpanic("%s: attempt to activate pmap with invalid ASID %p", __func__, pmap);\n'
      '\t}\n')
B1 = (A1 +
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v351 step1 asid", (unsigned long long)asid_index); }\n')
p = apply(p, A1, B1, 'pmap.c step1 asid', 'v351 step1 asid')

A2 = ('#if __ARM_MIXED_PAGE_SIZE__\n'
      '\tif (pt_attr->pta_tcr_value != get_tcr()) {\n'
      '\t\tbreak_before_make = true;\n'
      '\t}\n'
      '#endif\n')
B2 = (A2 +
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v351 step2 tcr now", (unsigned long long)get_tcr());\n'
      '\t  g0245d_tracev("v351 step2 tcr want", (unsigned long long)pt_attr->pta_tcr_value); }\n')
p = apply(p, A2, B2, 'pmap.c step2 tcr', 'v351 step2 tcr now')

A3 = ('\tif (__improbable(break_before_make && !pmap_user_ttb_is_clear())) {\n'
      '\t\tPMAP_TRACE(1, PMAP_CODE(PMAP__CLEAR_USER_TTB), VM_KERNEL_ADDRHIDE(pmap), PMAP_VASID(pmap), pmap->hw_asid);\n'
      '\t\tpmap_clear_user_ttb_internal();\n'
      '\t}\n')
B3 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v351 step3 ttb before", (unsigned long long)get_mmu_ttb());\n'
      '\t  g0245d_tracev("v351 step3 invalid", (unsigned long long)invalid_ttep); }\n' +
      A3 +
      trace('v351 step3 cleared'))
p = apply(p, A3, B3, 'pmap.c step3 clear ttb', 'v351 step3 ttb before')

A4 = ('\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n'
      '\t\tsync_tlb_flush_local();\n'
      '\t}\n'
      '\n'
      '\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n')
B4 = ('\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n'
      '\t\tsync_tlb_flush_local();\n'
      '\t}\n' +
      trace('v351 step4 flushed') +
      '\n'
      '\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n' +
      trace('v351 step5 ttb set'))
p = apply(p, A4, B4, 'pmap.c step4/5', 'v351 step4 flushed')

A5 = ('\tif (pmap != kernel_pmap) {\n'
      '\t\tset_mmu_ttb((pmap->ttep & TTBR_BADDR_MASK) | (((uint64_t)pmap->hw_asid) << TTBR_ASID_SHIFT));\n'
      '\t} else if (!pmap_user_ttb_is_clear()) {\n'
      '\t\tpmap_clear_user_ttb_internal();\n'
      '\t}\n')
B5 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v351 ttb want", (unsigned long long)((pmap->ttep & TTBR_BADDR_MASK) | (((uint64_t)pmap->hw_asid) << TTBR_ASID_SHIFT))); }\n'
      '\tif (pmap != kernel_pmap) {\n'
      '\t\tset_mmu_ttb((pmap->ttep & TTBR_BADDR_MASK) | (((uint64_t)pmap->hw_asid) << TTBR_ASID_SHIFT));\n'
      '\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t\t  g0245d_tracev("v351 ttb now", (unsigned long long)get_mmu_ttb()); }\n'
      '\t} else if (!pmap_user_ttb_is_clear()) {\n'
      '\t\tpmap_clear_user_ttb_internal();\n'
      '\t}\n')
p = apply(p, A5, B5, 'pmap.c set_mmu_ttb', 'v351 ttb want')

open(PMAPC, 'w', encoding='utf-8').write(p)

# ------------------------------------------------------------ arm64/sleh.c
s = open(SLEH, encoding='utf-8').read()
A6 = ('void\n'
      'sleh_synchronous_sp1(arm_context_t *context, uint32_t esr, vm_offset_t far)\n'
      '{\n'
      '\tesr_exception_class_t  class = ESR_EC(esr);\n'
      '\tarm_saved_state_t    * state = &context->ss;\n')
B6 = ('void\n'
      'sleh_synchronous_sp1(arm_context_t *context, uint32_t esr, vm_offset_t far)\n'
      '{\n'
      '\tesr_exception_class_t  class = ESR_EC(esr);\n'
      '\tarm_saved_state_t    * state = &context->ss;\n'
      '\n'
      '\t/* g0245d v351: the panic text does not fit on the console row, so a\n'
      '\t * photo never shows the faulting address.  Trace the ESR and the FAR\n'
      '\t * instead -- the FAR is the address that actually faulted. */\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v351 esr", (unsigned long long)esr);\n'
      '\t  g0245d_tracev("v351 far", (unsigned long long)(uintptr_t)far);\n'
      '\t  g0245d_tracev("v351 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state)); }\n')
s = apply(s, A6, B6, 'sleh.c esr/far/pc', 'v351 far')
open(SLEH, 'w', encoding='utf-8').write(s)

print('patch_v351: pmap switch stepped through, and the ESR/FAR/PC are traced')
