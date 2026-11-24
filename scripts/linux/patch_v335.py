#!/usr/bin/env python3
"""g0245d v335 -- stage markers inside load_machfile.

v334 fixed the ramdisk alignment and the loader finally saw a real header:

    v333 magic      0xfeedfacf      correct
    v333 type ncmds 131074          = (MH_EXECUTE << 16) | 2
    v333 szcmds     360             correct

and then nothing: no `v333 lret`, no `v333 bad err`, no execve return.  So the
kernel stops between the header checks and load_machfile() returning.  The
suspects, in execution order:

    pmap_create_options()      new task pmap, page tables for this port
    vm_map_create_options()    new user map
    ASLR block                 random()/vm_map_get_max_aslr_slide_*
    parse_machfile()           walks the load commands, maps segments
    in_exec halt block         task_start_halt / proc_transcommit /
                               task_complete_halt (waits for other threads)

One marker per step pinpoints it.  `v333 lret` afterwards still tells whether
load_machfile returned at all.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/mach_loader.c')

DECL = '\t{ extern void g0245d_trace(const char *);\n\t  extern void g0245d_trace_u(const char *, unsigned int);\n'
DECL_ONE = '\t{ extern void g0245d_trace(const char *);\n'


def mark(label):
    return DECL + '\t  g0245d_trace("%s"); }\n' % label


def mark_u(label, expr):
    return DECL + '\t  g0245d_trace_u("%s", (unsigned int)(%s)); }\n' % (label, expr)


s = open(PATH, encoding='utf-8').read()
if 'v335 pmap ok' in s:
    print('patch_v335: already applied')
    sys.exit(0)

# 1. after the new pmap exists
A1 = ('\tif (pmap == NULL) {\n\t\treturn LOAD_RESOURCE;\n\t}\n'
      '\tmap = vm_map_create_options(pmap, 0,\n')
B1 = ('\tif (pmap == NULL) {\n\t\treturn LOAD_RESOURCE;\n\t}\n' +
      mark('v335 pmap ok') +
      '\tmap = vm_map_create_options(pmap, 0,\n')
assert s.count(A1) == 1
s = s.replace(A1, B1, 1)

# 2. after the new map exists (anchor is the end of the create call)
A2 = '\t    VM_MAP_CREATE_PAGEABLE);\n'
B2 = '\t    VM_MAP_CREATE_PAGEABLE);\n' + mark('v335 map ok')
assert s.count(A2) == 1
s = s.replace(A2, B2, 1)

# 3. right before parse_machfile
A3 = ('\tlret = parse_machfile(vp, map, thread, header, file_offset, macho_size,\n'
      '\t    0, aslr_page_offset, dyld_aslr_page_offset, result,\n'
      '\t    NULL, imgp);\n')
B3 = mark('v335 aslr ok') + A3
assert s.count(A3) == 1
s = s.replace(A3, B3, 1)

# 4. after parse_machfile succeeded
A4 = ('\tif (lret != LOAD_SUCCESS) {\n'
      '\t\tvm_map_deallocate(map); /* will lose pmap reference too */\n'
      '\t\treturn lret;\n'
      '\t}\n')
B4 = A4 + mark('v335 parse ok')
assert s.count(A4) == 1
s = s.replace(A4, B4, 1)

# 5. after the in_exec halt block
A5 = '\t\ttask_rollup_accounting_info(get_threadtask(thread), task);\n\t}\n'
B5 = A5 + mark('v335 halt ok')
assert s.count(A5) == 1
s = s.replace(A5, B5, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v335: 5 stage markers installed in load_machfile')
