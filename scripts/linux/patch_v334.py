#!/usr/bin/env python3
"""g0245d v334 -- align the ramdisk image to a page boundary.

v333 proved the loader was handed a header of all zeros:

    v333 magic      0x0                   (want 0xfeedfacf)
    v333 type ncmds 0
    v333 szcmds     0
    v333 bad err    4294967295            (= -1, the magic/filetype check)

The image was never wrong -- the *address* was.  mdevstrategy computes the
source of a read as

    fvaddr = (mdev[devid].mdBase << 12) + blkoff;

and mdBase is stored as a page number (`va >> 12`), so the base is truncated to
a 4K boundary.  But g0245d_perm_pool_alloc() is just

    g0245d_perm_alloc(size, 15)            /* mask 15 == 16-byte alignment */

and this pool is also used for bufhashtbl, struct buf, fbt's probetab and more,
all allocated *before* the ramdisk.  The block therefore almost never starts on
a page boundary: the whole image shifted down by (va & 0xFFF) bytes, so offset 0
landed in the untouched pool area ahead of the image -- zeros.

Fix: over-allocate one extra page and align up to 4K ourselves before the
memcpy and before handing the page number to mdevadd().
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'iokit/bsddev/IOKitBSDInit.cpp')

OLD = ('\t\t\textern void *g0245d_perm_pool_alloc(unsigned long size);\n'
       '\t\t\tvm_offset_t g0245d_va = 0;\n'
       '\t\t\tg0245d_va = (vm_offset_t)(uintptr_t)\n'
       '\t\t\t    g0245d_perm_pool_alloc(0x2000);\n')

NEW = ('\t\t\textern void *g0245d_perm_pool_alloc(unsigned long size);\n'
       '\t\t\tvm_offset_t g0245d_raw = 0;\n'
       '\t\t\tvm_offset_t g0245d_va = 0;\n'
       '\t\t\t/* g0245d v334: the pool only guarantees 16-byte alignment\n'
       '\t\t\t * (g0245d_perm_alloc(size, 15)), but mdevstrategy derives the\n'
       '\t\t\t * read source as (mdBase << 12) + blkoff, i.e. it truncates the\n'
       '\t\t\t * base to a page boundary.  A base that was not page aligned\n'
       '\t\t\t * shifted the whole image, so the loader read zeros for\n'
       '\t\t\t * mach_header->magic (v333 magic 0x0).  Over-allocate one page\n'
       '\t\t\t * and align up before copying. */\n'
       '\t\t\tg0245d_raw = (vm_offset_t)(uintptr_t)\n'
       '\t\t\t    g0245d_perm_pool_alloc(0x3000);\n'
       '\t\t\tif (g0245d_raw != 0) {\n'
       '\t\t\t\tg0245d_va = (g0245d_raw + 0xFFFu) & ~(vm_offset_t)0xFFFu;\n'
       '\t\t\t}\n')

t = open(PATH, encoding='utf-8').read()
if 'g0245d v334' in t:
    print('patch_v334: already applied')
    sys.exit(0)
assert t.count(OLD) == 1, t.count(OLD)
open(PATH, 'w', encoding='utf-8').write(t.replace(OLD, NEW, 1))
print('patch_v334: ramdisk base is now page aligned (0x3000 alloc, align up)')
