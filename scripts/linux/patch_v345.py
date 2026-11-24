#!/usr/bin/env python3
"""g0245d v345 -- where exactly does the tail of exec_mach_imgact die?

v344's boot cleared everything down to `v344 n userstack`, so both copyouts
(exec_add_apple_strings and exec_copyout_strings) worked and the thread got its
user stack.  The last trace was the page-in of the __TEXT code page
(`v312 blkoff 4096` -> `v316 spec done`), i.e. exactly what

    /* Avoid immediate VM faults back into kernel */
    exec_prefault_data(p, imgp, &load_result);

triggers: it calls vm_fault() on the entry point page.

Remaining tail:
    exec_prefault_data()   <- prefaults the entry point page (suspect #1)
    vm_map_switch(old_map)
    execsigs()             <- resets signal state
    _aio_exec()            <- "MAY BLOCK!"

Breadcrumbs o..s cover them, and exec_prefault_data now reports the kern_return_t
of its vm_fault() through the status row, so we can tell "the fault failed" from
"the fault never returned".
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(PATH, encoding='utf-8').read()
if 'v345 o prefault call' in s:
    print('patch_v345: already applied')
    sys.exit(0)


def mark(label, indent='\t'):
    return ('%s{ extern void g0245d_status(const char *);\n'
            '%s  g0245d_status("%s"); }\n' % (indent, indent, label))


# ---- exec_mach_imgact: wrap exec_prefault_data, then the three steps after it
A1 = ('\t/* Avoid immediate VM faults back into kernel */\n'
      '\texec_prefault_data(p, imgp, &load_result);\n')
B1 = ('\t/* Avoid immediate VM faults back into kernel */\n' +
      mark('v345 o prefault call') +
      '\texec_prefault_data(p, imgp, &load_result);\n' +
      mark('v345 p prefault ok'))
assert s.count(A1) == 1
s = s.replace(A1, B1, 1)

A2 = '\texecsigs(p, thread);\n'
B2 = mark('v345 q execsigs call') + '\texecsigs(p, thread);\n' + mark('v345 r execsigs ok')
assert s.count(A2) == 1
s = s.replace(A2, B2, 1)

A3 = '\t_aio_exec( p );\n'
B3 = '\t_aio_exec( p );\n' + mark('v345 s aio ok')
assert s.count(A3) == 1
s = s.replace(A3, B3, 1)

# ---- exec_prefault_data: surface the vm_fault() result on the status row
A4 = ('\tif (kr != KERN_SUCCESS) {\n'
      '\t\tDEBUG4K_ERROR("map %p va 0x%llx -> 0x%x\\n", current_map(), '
      '(uint64_t)vm_map_trunc_page(load_result->entry_point, vm_map_page_mask(current_map())), kr);\n'
      '\t}\n')
B4 = ('\tif (kr != KERN_SUCCESS) {\n'
      '\t\tDEBUG4K_ERROR("map %p va 0x%llx -> 0x%x\\n", current_map(), '
      '(uint64_t)vm_map_trunc_page(load_result->entry_point, vm_map_page_mask(current_map())), kr);\n'
      '\t\t{ extern void g0245d_status(const char *);\n'
      '\t\t  static char v345buf[80];\n'
      '\t\t  snprintf(v345buf, sizeof(v345buf), "v345 vm_fault kr=%d va=%llx",\n'
      '\t\t      (int)kr,\n'
      '\t\t      (unsigned long long)vm_map_trunc_page(load_result->entry_point,\n'
      '\t\t          vm_map_page_mask(current_map())));\n'
      '\t\t  g0245d_status(v345buf); }\n'
      '\t}\n')
assert s.count(A4) == 1
s = s.replace(A4, B4, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v345: prefault / execsigs / aio breadcrumbs + vm_fault kr readout')
