#!/usr/bin/env python3
"""g0245d v343 -- what does create_unix_stack() return?

v342's boot cleared the whole tpro..swapmap stretch: the status row ended on
`v341 f stack call`, so exec_setup_tpro, the vm_map limits, the CS flags,
vm_map_exec, fdt_exec, exec_handle_sugid, swap_task_map and
activate_exec_state all completed.  The trace even shows the loader paging in
file page 2 (`v312 blkoff 4096`), i.e. the __TEXT code page.

So the remaining gate is create_unix_stack(): it allocates the user stack at the
top of the fresh address space.  Historically it stores its kern_return_t only
in the condition, and on failure the code jumps to badtoolate -> SIGKILL ->
"unexpected exit of init", which tells us nothing.

Keep the code and print it:

    kr != 0  ->  panic "g0245d v343 stack kr=<n>"
    kr == 0  ->  status "v343 g stack ok"

plus a final breadcrumb `v343 h exec done` just before `goto done`.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(PATH, encoding='utf-8').read()
if 'v343 stack' in s:
    print('patch_v343: already applied')
    sys.exit(0)

A1 = ('\tif (load_result.unixproc &&\n'
      '\t    create_unix_stack(get_task_map(task),\n'
      '\t    &load_result,\n'
      '\t    p) != KERN_SUCCESS) {\n'
      '\t\terror = load_return_to_errno(LOAD_NOSPACE);\n')
B1 = ('\tint v343_stack_kr = (int)KERN_SUCCESS;\n'
      '\tif (load_result.unixproc) {\n'
      '\t\tv343_stack_kr = (int)create_unix_stack(get_task_map(task),\n'
      '\t\t    &load_result, p);\n'
      '\t\tif (v343_stack_kr != (int)KERN_SUCCESS) {\n'
      '\t\t\tpanic("g0245d v343 stack kr=%d", v343_stack_kr);\n'
      '\t\t}\n'
      '\t\t{ extern void g0245d_status(const char *);\n'
      '\t\t  g0245d_status("v343 g stack ok"); }\n'
      '\t}\n'
      '\tif (load_result.unixproc && v343_stack_kr != (int)KERN_SUCCESS) {\n'
      '\t\terror = load_return_to_errno(LOAD_NOSPACE);\n')
assert s.count(A1) == 1, s.count(A1)
s = s.replace(A1, B1, 1)

A2 = ('\t\tuserspace_coredump_name = NULL;\n'
      '\t}\n'
      '\n'
      '\tgoto done;\n')
B2 = ('\t\tuserspace_coredump_name = NULL;\n'
      '\t}\n'
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v343 h exec done"); }\n'
      '\n'
      '\tgoto done;\n')
assert s.count(A2) == 1, s.count(A2)
s = s.replace(A2, B2, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v343: create_unix_stack return code captured, exec_done breadcrumb added')
