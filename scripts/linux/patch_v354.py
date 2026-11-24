#!/usr/bin/env python3
"""g0245d v354: force every translation-table root to be a full, granule
aligned page.

pmap_tt1_allocate() carves sub-page roots (PMAP_ROOT_ALLOC_SIZE = 2 KB on
this build) out of one zeroed page and pushes the remaining chunks onto a
free list for later callers.  The first caller gets the page base, which is
aligned; everyone after that gets a chunk at page_base + k*2 KB, so the root
physical address is only 2 KB aligned -- the photos show exactly that:

    v349 pmap ttep 0x96c3b808     low bits 0x808
    v352 ttep     0x970e2000      low bits 0x000   (fresh page, aligned)
    v353 boot:    ttep 0x96c51800 low bits 0x800

TTBR0 on this SoC requires the root to be aligned to the granule (16 KB
here).  Loading a 2 KB aligned root makes every user-space translation
fault, and the exec path -- which runs entirely in EL1 -- then dies in a
write / level-2 translation fault storm:

    ESR 0x96000145 = EC 37 (data abort, current EL), WnR=1 (write),
                     DFSC 0x5 (translation fault, level 2)

repeated until the exception frames overflow the kernel stack and the
panic "Invalid kernel stack pointer (probably overflow)" fires.  The first
switch, onto the freshly allocated exec map with an aligned root, always
works; everything after the misaligned root is loaded dies.

v354 removes the carving: any root smaller than a page is rounded up to a
full page in BOTH pmap_tt1_allocate() and pmap_tt1_deallocate(), so every
root is granule aligned and the free lists stay consistent.  The unused
tail of the page stays zeroed, which is exactly what the hardware walk
expects for the unmapped remainder of the address space.  The extra cost is
a few pages of physical memory, which is nothing on a bring-up.

One probe is added next to the v353 ones:

    v354 ttep low  - new_pmap->ttep & 0x3FFF; must print 0x0 for every
                     switch once the fix is in.  Anything else means a
                     misaligned root is still being handed out.
"""

import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PMAPC = os.path.join(W, 'osfmk/arm/pmap/pmap.c')

p = open(PMAPC, encoding='utf-8').read()

# ---- 1. round every sub-page root up to a full page ----------------------
# The identical snippet appears in pmap_tt1_allocate() and
# pmap_tt1_deallocate(); both must agree or the free lists corrupt.
OLD = ("\tif ((size < PAGE_SIZE) && (size != PMAP_ROOT_ALLOC_SIZE)) {\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")
NEW = ("\tif (size < PAGE_SIZE) {\n"
       "\t\t/* g0245d v354: roots must be granule aligned.  Carving a\n"
       "\t\t * sub-page root out of a shared page hands out addresses\n"
       "\t\t * like 0x96c51800 -- only 2 KB aligned -- and TTBR0 on this\n"
       "\t\t * SoC faults every user translation on such a root\n"
       "\t\t * (ESR 0x96000145: EC 37, WnR=1, DFSC 5, until the\n"
       "\t\t * exception frames overflow the kernel stack).  Round every\n"
       "\t\t * root up to a full page; the unused tail stays zeroed. */\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")

n = p.count(OLD)
if n == 0:
    if 'v354' in p:
        print('patch_v354: already applied')
    else:
        sys.exit('patch_v354: size-normalisation snippet not found')
else:
    assert n == 2, 'expected the snippet in allocate+deallocate, found %d' % n
    p = p.replace(OLD, NEW)
    print('  %-30s patched (allocate + deallocate)' % 'pmap.c root alignment')

# ---- 2. probe: the root alignment, printed for every switch --------------
A1 = '\t  g0245d_tracev("v353 is64", (unsigned long long)new_pmap->is_64bit); }\n'
B1 = ('\t  g0245d_tracev("v353 is64", (unsigned long long)new_pmap->is_64bit);\n'
      '\t  g0245d_tracev("v354 ttep low",\n'
      '\t      (unsigned long long)((unsigned long long)new_pmap->ttep & 0x3FFFULL)); }\n')
if 'v354 ttep low' not in p:
    assert p.count(A1) == 1, 'v353 probe block not found: %d' % p.count(A1)
    p = p.replace(A1, B1, 1)
    print('  %-30s added' % 'pmap.c v354 ttep low probe')

open(PMAPC, 'w', encoding='utf-8').write(p)
print('patch_v354: done -- roots are now always granule aligned')
