#!/usr/bin/env python3
"""g0245d v353 -- find out why one pmap's root table is not page aligned.

Two photos of v352 give a clean comparison.

First switch (the exec map, ASID 2) -- succeeded:

    8720 v352 ttb in use 0x1000096c3d000
    8721 v352 ttep 0x970e2000
    8722 v352 asid 0x2
    8723 v352 switch done 0x20000970e2000

Second switch (the init task's own map, ASID 1) -- died inside
pmap_set_pmap(), before "v352 switch done" could be printed:

    8749 v352 vs call 0x2
    8750 v352 vs map 0xffffffff45507f040
    8751 v352 vs old 0xffffffff45507fac0
    8752 v349 pmap ttep 0x96c51800
    8753 v349 pmap asid 0x1
    8754 v352 ttb in use 0x20000970e2000

The two root tables differ in their alignment:

    0x970e2000 & 0xfff == 0x000   16K aligned, switch worked
    0x96c51800 & 0xfff == 0x800   only 2K aligned, switch died

TTBR0 needs the translation table root to be aligned to the granule, so a
root that is not page aligned produces a table the MMU cannot walk: the
switch appears to succeed and the next access aborts.

pmap->ttep is computed as ml_static_vtop(p->tte), and p->tte comes from
pmap_tt1_allocate().  v353 therefore prints the whole chain for the pmap
about to be activated:

    v353 tte        - the kernel virtual address of the root table
    v353 tte        - the kernel virtual address of the root table
    v353 is64       - whether the pmap is a 64-bit address space

and, in vm_map_switch(), which map and which thread map are involved, so
the photo names the two maps that differ.

Everything goes through g0245d_tracev() from ordinary code:
pmap_switch_user() is not a MARK_AS_PMAP_TEXT function, unlike
pmap_switch_internal() and pmap_switch_user_ttb(), where a console call
kills the boot.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PMAPC = os.path.join(W, 'osfmk/arm/pmap/pmap.c')

p = open(PMAPC, encoding='utf-8').read()
if 'v353 tte' in p:
    print('patch_v353: already applied')
    sys.exit(0)

A0 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v352 ttb in use", (unsigned long long)get_mmu_ttb());\n'
      '\t  g0245d_tracev("v352 ttep", (unsigned long long)new_pmap->ttep);\n'
      '\t  g0245d_tracev("v352 asid", (unsigned long long)new_pmap->hw_asid); }\n')
B0 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v353 ttb in use", (unsigned long long)get_mmu_ttb());\n'
      '\t  g0245d_tracev("v353 ttep", (unsigned long long)new_pmap->ttep);\n'
      '\t  g0245d_tracev("v353 asid", (unsigned long long)new_pmap->hw_asid);\n'
      '\t  g0245d_tracev("v353 tte", (unsigned long long)(uintptr_t)new_pmap->tte);\n'
      '\t  g0245d_tracev("v353 is64", (unsigned long long)new_pmap->is_64bit); }\n')
assert p.count(A0) == 1, p.count(A0)
p = p.replace(A0, B0, 1)
open(PMAPC, 'w', encoding='utf-8').write(p)
print('patch_v353: root table alignment chain printed before every pmap switch')
