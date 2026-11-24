#!/usr/bin/env python3
"""g0245d v352 -- keep the probes out of the PMAP_TEXT section.

v351 put g0245d_tracev() calls inside pmap_switch_internal() and
pmap_switch_user_ttb().  Both are MARK_AS_PMAP_TEXT functions.  The photo
from v351 shows what that cost:

    8656 v351 step3 ttb before 0x9619c000
    8657 v351 step3 invalid 0x9619c000
    8658 v351 step3 cleared 0x0
    8659 v351 step4 flushed 0x0
    8661 v351 ttb now
    status row: PE_lockdown_iokit

Three things went wrong at once:

  * the last trace sequence number is 8661, while v349 got to 8744 before
    it died, so v351 died *much* earlier in the boot than the exec path;
  * the status row still reads "PE_lockdown_iokit", a kernel_bootstrap()
    message, so none of the exec-path status labels were ever printed --
    the exec path was never reached;
  * no "v351 esr" / "v351 far" ever appeared, so the exception handler
    never ran either.

MARK_AS_PMAP_TEXT puts the function in the __PPLTEXT section, which the
kernel runs with restricted calling conventions: it may not call back into
ordinary code that touches the heap, takes locks, or flushes the
framebuffer console.  g0245d_tracev() does all three -- it formats through
a static buffer, calls g0245d_con_printf(), and g0245d_con_sync() issues
"dc civac" over the whole text area.  Calling it from a PMAP_TEXT
function is what killed the boot.

v352 therefore:

  * removes every probe from pmap_switch_internal() and
    pmap_switch_user_ttb(), restoring those functions to their upstream
    shape;
  * keeps the vm_map_switch() call counter, which lives in ordinary VM
    code and is safe;
  * keeps the ESR / FAR / PC capture in sleh_synchronous_sp1(), which is
    ordinary code on the exception path;
  * adds a *safe* probe pair around the page table switch itself, in
    pmap_switch_user(), which is ordinary code (no MARK_AS_PMAP_TEXT):
    the ttep that is about to be loaded, and the TTB the CPU is running
    with right before the switch.

So the photo still names the faulting statement -- through the ESR / FAR
that the exception handler now records -- but nothing in a PMAP_TEXT
function calls into the console any more.

v352 also plants a plain global, g0245d_pmap_marker, that the
PMAP_TEXT code may write without calling anything.  Ordinary code reads
it and turns it into a trace line.  That keeps a way to see how far a
PMAP_TEXT function got without putting a console call inside it.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PMAPC = os.path.join(W, 'osfmk/arm/pmap/pmap.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')
INIT = os.path.join(W, 'osfmk/arm/arm_init.c')

p = open(PMAPC, encoding='utf-8').read()
if 'v352' in p:
    print('patch_v352: already applied')
    sys.exit(0)


def undo(text, fragment, what):
    """Remove one probe block that v351 added."""
    if fragment not in text:
        print('  %-24s already removed' % what)
        return text
    print('  %-24s removed' % what)
    return text.replace(fragment, '', 1)


# ---- pmap_switch_internal(): strip every probe.
for frag, what in (
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step1 asid", (unsigned long long)asid_index); }\n',
     'pmap.c step1 asid'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step2 tcr now", (unsigned long long)get_tcr());\n'
     '\t  g0245d_tracev("v351 step2 tcr want", (unsigned long long)pt_attr->pta_tcr_value); }\n',
     'pmap.c step2 tcr'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step3 ttb before", (unsigned long long)get_mmu_ttb());\n'
     '\t  g0245d_tracev("v351 step3 invalid", (unsigned long long)invalid_ttep); }\n',
     'pmap.c step3 ttb'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step3 cleared", (unsigned long long)(uintptr_t)0); }\n',
     'pmap.c step3 cleared'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step4 flushed", (unsigned long long)(uintptr_t)0); }\n',
     'pmap.c step4 flushed'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 step5 ttb set", (unsigned long long)(uintptr_t)0); }\n',
     'pmap.c step5 ttb set'),
    ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v351 ttb want", (unsigned long long)((pmap->ttep & TTBR_BADDR_MASK) | (((uint64_t)pmap->hw_asid) << TTBR_ASID_SHIFT))); }\n',
     'pmap.c ttb want'),
    ('\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t\t  g0245d_tracev("v351 ttb now", (unsigned long long)get_mmu_ttb()); }\n',
     'pmap.c ttb now'),
):
    p = undo(p, frag, what)

# ---- pmap_switch_user(): ordinary code, safe to probe.  Report the ttep
#      that is about to be loaded and the TTB in use before the switch.
A0 = ('\tthread->map = new_map;\n'
      '\tpmap_set_pmap(new_pmap, thread);\n')
B0 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v352 ttb in use", (unsigned long long)get_mmu_ttb());\n'
      '\t  g0245d_tracev("v352 ttep", (unsigned long long)new_pmap->ttep);\n'
      '\t  g0245d_tracev("v352 asid", (unsigned long long)new_pmap->hw_asid); }\n'
      '\tthread->map = new_map;\n'
      '\tpmap_set_pmap(new_pmap, thread);\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v352 switch done", (unsigned long long)get_mmu_ttb()); }\n')
assert p.count(A0) == 1, p.count(A0)
p = p.replace(A0, B0, 1)
print('  %-24s added' % 'pmap.c safe probes')
# ---- arm_init.c: a plain global that PMAP_TEXT code may write without
#      calling anything.  Ordinary code turns it into a trace line.
i = open(INIT, encoding='utf-8').read()
A1 = ("static unsigned long g0245d_hb_count;   /* g0245d v254 */\n"
      "static const char *g0245d_last_label;   /* g0245d v265: newest trace label */\n")
B1 = (A1 +
      "/* g0245d v352: progress marker for code that runs in the PMAP_TEXT\n"
      " * section.  That section may not call back into ordinary code, so the\n"
      " * marker is a plain word that ordinary code reads back and prints. */\n"
      "unsigned long g0245d_pmap_marker;\n")
if 'g0245d_pmap_marker' not in i:
    assert i.count(A1) == 1, i.count(A1)
    i = i.replace(A1, B1, 1)
    open(INIT, 'w', encoding='utf-8').write(i)
    print('  %-24s added' % 'arm_init.c marker')
else:
    print('  %-24s already applied' % 'arm_init.c marker')

# ---- pmap.c: write the marker from PMAP_TEXT, read it from ordinary code.
A2 = ('\tif (new_map == NULL || new_pmap == NULL || new_pmap->ttep == 0) {\n')
B2 = ('\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x100; }\n' +
      A2)
if 'g0245d_pmap_marker = 0x100' not in p:
    assert p.count(A2) == 1, p.count(A2)
    p = p.replace(A2, B2, 1)
    print('  %-24s added' % 'pmap.c marker write')

A3 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_tracev("v352 marker", (unsigned long long)g0245d_pmap_marker);\n'
      '\t  g0245d_tracev("v352 ttb in use", (unsigned long long)get_mmu_ttb());\n')
B3 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v352 ttb in use", (unsigned long long)get_mmu_ttb());\n')
if 'v352 marker' not in p:
    assert p.count(A3) == 1, p.count(A3)
    p = p.replace(A3, B3, 1)
    print('  %-24s adjusted' % 'pmap.c marker read')

A3b = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
       '\t  g0245d_tracev("v352 switch done", (unsigned long long)get_mmu_ttb()); }\n')
B3b = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
       '\t  extern unsigned long g0245d_pmap_marker;\n'
       '\t  g0245d_tracev("v352 switch done", (unsigned long long)get_mmu_ttb());\n'
       '\t  g0245d_tracev("v352 marker", (unsigned long long)g0245d_pmap_marker); }\n')
if 'v352 marker' not in p:
    assert p.count(A3b) == 1, p.count(A3b)
    p = p.replace(A3b, B3b, 1)
    print('  %-24s added' % 'pmap.c marker read')

open(PMAPC, 'w', encoding='utf-8').write(p)

# ---- pmap_switch_internal(): record the progress in the marker word only.
#      No console call, no function call: just a store to a plain global.
A4 = ('\tif (__improbable((asid_index == 0) && (pmap != kernel_pmap))) {\n'
      '\t\tpanic("%s: attempt to activate pmap with invalid ASID %p", __func__, pmap);\n'
      '\t}\n')
B4 = ('\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x201; }\n' +
      A4)
if 'g0245d_pmap_marker = 0x201' not in p:
    assert p.count(A4) == 1, p.count(A4)
    p = p.replace(A4, B4, 1)
    print('  %-24s added' % 'pmap.c step1 marker')

A5 = ('\tif (__improbable(break_before_make && !pmap_user_ttb_is_clear())) {\n'
      '\t\tPMAP_TRACE(1, PMAP_CODE(PMAP__CLEAR_USER_TTB), VM_KERNEL_ADDRHIDE(pmap), PMAP_VASID(pmap), pmap->hw_asid);\n'
      '\t\tpmap_clear_user_ttb_internal();\n'
      '\t}\n')
B5 = ('\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x202; }\n' +
      A5 +
      '\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x203; }\n')
if 'g0245d_pmap_marker = 0x202' not in p:
    assert p.count(A5) == 1, p.count(A5)
    p = p.replace(A5, B5, 1)
    print('  %-24s added' % 'pmap.c step2/3 markers')

A6 = ('\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n'
      '\t\tsync_tlb_flush_local();\n'
      '\t}\n'
      '\n'
      '\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n')
B6 = ('\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x204; }\n'
      '\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n'
      '\t\tsync_tlb_flush_local();\n'
      '\t}\n'
      '\n'
      '\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n'
      '\t{ extern unsigned long g0245d_pmap_marker;\n'
      '\t  g0245d_pmap_marker = 0x205; }\n')
if 'g0245d_pmap_marker = 0x204' not in p:
    assert p.count(A6) == 1, p.count(A6)
    p = p.replace(A6, B6, 1)
    print('  %-24s added' % 'pmap.c step4/5 markers')

open(PMAPC, 'w', encoding='utf-8').write(p)

# ---- vm_map.c: rename the counter so the photo is unambiguous.
v = open(VMAP, encoding='utf-8').read()
v = v.replace('v351 vs call', 'v352 vs call')
v = v.replace('v351 vs map', 'v352 vs map')
v = v.replace('v351 vs old', 'v352 vs old')
v = v.replace('static unsigned int v351_vsn = 0;', 'static unsigned int v352_vsn = 0;')
v = v.replace('(++v351_vsn)', '(++v352_vsn)')
open(VMAP, 'w', encoding='utf-8').write(v)
print('  %-24s added' % 'vm_map.c counter')

# ---- sleh.c: keep the ESR and the FAR.  These are the whole point of the
#      exercise: the FAR is the address the CPU actually faulted on, and
#      the PC says which statement it was executing.
SLEH = os.path.join(W, 'osfmk/arm64/sleh.c')
s = open(SLEH, encoding='utf-8').read()
if 'v352 esr' in s:
    print('  %-24s already applied' % 'sleh.c esr/far/pc')
else:
    A6 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v351 esr", (unsigned long long)esr);\n'
          '\t  g0245d_tracev("v351 far", (unsigned long long)(uintptr_t)far);\n'
          '\t  g0245d_tracev("v351 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state)); }\n')
    B6 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v352 esr", (unsigned long long)esr);\n'
          '\t  g0245d_tracev("v352 far", (unsigned long long)(uintptr_t)far);\n'
          '\t  g0245d_tracev("v352 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state)); }\n')
    assert s.count(A6) == 1, s.count(A6)
    s = s.replace(A6, B6, 1)
    open(SLEH, 'w', encoding='utf-8').write(s)
    print('  %-24s added' % 'sleh.c esr/far/pc')

print('patch_v352: PMAP_TEXT probes removed, safe probes added around the switch')