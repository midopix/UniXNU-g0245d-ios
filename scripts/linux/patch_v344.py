#!/usr/bin/env python3
"""g0245d v344 -- breadcrumbs after create_unix_stack, plus the thread's PC/SP.

v343's boot reached `v343 g stack ok`, so create_unix_stack() succeeded and the
user stack exists.  The last trace was `v316 spec done`, i.e. the kernel was
paging in the __TEXT code page (file offset 0x1000) when it died.

What is left in exec_mach_imgact between create_unix_stack() and `goto done`:

    task_set_platform_binary
    task_set_exc_guard_ctrl_port_default
    exec_add_apple_strings()    <- copyout into user space
    vm_map_switch(new map)
    exec_copyout_strings()      <- copyout argv/envp onto the new user stack
    thread_setuserstack
    ... dynlinker handling (skipped, no LC_LOAD_DYLINKER)

Two of those are copyouts into the freshly created user stack, which is exactly
the kind of thing that faulted earlier today (the scratch page at 0x1000 had to
be wired before copyout would work).

Breadcrumbs i..n mark each step, and the status row now carries the actual
entry point and user stack address:

    v344 ep=<hex> sp=<hex> sz=<hex>
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(PATH, encoding='utf-8').read()
if 'v344 ep=' in s:
    print('patch_v344: already applied')
    sys.exit(0)


def mark(label, indent='\t'):
    return ('%s{ extern void g0245d_status(const char *);\n'
            '%s  g0245d_status("%s"); }\n' % (indent, indent, label))


edits = [
    # the stack is up: show the entry point and the stack we are about to use
    ('\t\t{ extern void g0245d_status(const char *);\n'
     '\t\t  g0245d_status("v343 g stack ok"); }\n',
     '\t\t{ extern void g0245d_status(const char *);\n'
     '\t\t  static char v344buf[96];\n'
     '\t\t  snprintf(v344buf, sizeof(v344buf),\n'
     '\t\t      "v344 ep=%llx sp=%llx sz=%llx",\n'
     '\t\t      (unsigned long long)load_result.entry_point,\n'
     '\t\t      (unsigned long long)load_result.user_stack,\n'
     '\t\t      (unsigned long long)load_result.user_stack_size);\n'
     '\t\t  g0245d_status(v344buf); }\n'),

    # i: platform binary flag
    ('\t\ttask_set_platform_binary(task, FALSE);\n\t}\n',
     '\t\ttask_set_platform_binary(task, FALSE);\n\t}\n' + mark('v344 i platform')),

    # j: exception guard control port
    ('\t    load_result.ip_platform,\n'
     '\t    load_result.lr_sdk);\n',
     '\t    load_result.ip_platform,\n'
     '\t    load_result.lr_sdk);\n' + mark('v344 j excguard')),

    # k: apple strings copied out
    ('\terror = exec_add_apple_strings(imgp, &load_result); /* copies out main thread port */\n',
     '\terror = exec_add_apple_strings(imgp, &load_result); /* copies out main thread port */\n' +
     mark('v344 k applestr')),

    # l: switched to the new map
    ('\told_map = vm_map_switch(get_task_map(task));\n',
     '\told_map = vm_map_switch(get_task_map(task));\n' + mark('v344 l mapswitch')),

    # m: argv/envp copied onto the new user stack
    ('\t\terror = exec_copyout_strings(imgp, &ap);\n',
     '\t\terror = exec_copyout_strings(imgp, &ap);\n' + mark('v344 m copystr')),

    # n: the thread now has its stack
    ('\t\tthread_setuserstack(thread, ap);\n\t}\n',
     '\t\tthread_setuserstack(thread, ap);\n\t}\n' + mark('v344 n userstack')),
]

for old, new in edits:
    assert s.count(old) == 1, (old.split('\n')[0][:55], s.count(old))
    s = s.replace(old, new, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v344: i..n breadcrumbs + entry point / stack address on the status row')
