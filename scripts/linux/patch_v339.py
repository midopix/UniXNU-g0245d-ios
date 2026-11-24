#!/usr/bin/env python3
"""g0245d v339 -- the exact kern_return_t from map_segment.

v338's panic worked and gave us:

    g0245d v338 mseg ret=5 seg=45545f5f vm=100000-102000 f=0-2000 ubc=1

so __PAGEZERO mapped fine (seg 41505f5f, rc 0), ubc_getobject() *did* return an
object, and it is __TEXT that fails.  But `ret=5` there is map_segment's own
return value (LOAD_NOSPACE == 5), not the underlying KERN_* code.

map_segment has three vm_map_enter_mem_object* call sites:
    b1  the leading 4K page            (only when vm_start is not page aligned)
    b2  the file-backed bulk
    b3  the zero-fill tail

Label them and print the kern_return_t plus page shift so the next photo says
exactly which mapping failed and why:

    g0245d v339 b2 kr=<kern_return_t> cur=<a>-<b> f=<c>-<d> pg=<page_shift>

KERN_NO_SPACE=3, KERN_INVALID_ARGUMENT=4, KERN_FAILURE=5, KERN_INVALID_ADDRESS=1.
pg 12 == 4 KB pages, 14 == 16 KB.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/mach_loader.c')

s = open(PATH, encoding='utf-8').read()
if 'v339 b2' in s:
    print('patch_v339: already applied')
    sys.exit(0)

BLK = ('\t\tif (ret != KERN_SUCCESS) {\n'
       '\t\t\treturn LOAD_NOSPACE;\n'
       '\t\t}\n'
       '\t\tcur_offset += cur_end - cur_start;\n')

new_blocks = []
for tag in ('b1', 'b2', 'b3'):
    new_blocks.append(
        '\t\tif (ret != KERN_SUCCESS) {\n'
        '\t\t\tpanic("g0245d v339 %s kr=%%d cur=%%llx-%%llx f=%%llx-%%llx pg=%%d",\n'
        '\t\t\t    (int)ret,\n'
        '\t\t\t    (uint64_t)cur_start, (uint64_t)cur_end,\n'
        '\t\t\t    (uint64_t)file_start, (uint64_t)file_end,\n'
        '\t\t\t    (int)vm_map_page_shift(map));\n'
        '\t\t\treturn LOAD_NOSPACE;\n'
        '\t\t}\n'
        '\t\tcur_offset += cur_end - cur_start;\n' % tag)

assert s.count(BLK) == 3, s.count(BLK)
for nb in new_blocks:
    s = s.replace(BLK, nb, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v339: map_segment failure sites labelled b1/b2/b3 with kern_return_t')
