#!/usr/bin/env python3
"""g0245d v341 -- breadcrumbs on the status row after load_machfile succeeds.

v340's boot showed heartbeat `v333 lret` with no `v338 lret=` panic, i.e.
load_machfile returned LOAD_SUCCESS: the fixture is finally a *loadable* Mach-O.
Everything died shortly afterwards (a `v328 ec 37` data abort, then the
debugger), so the failure is now between the loader returning 0 and userland.

The trace ring is useless here (it blanks on every wrap), but the status row at
the bottom persists.  So drop breadcrumbs there -- each overwrites the last, and
whichever one is still on screen when it dies names the step it never finished:

    v341 a lret ok          load_machfile returned 0
    v341 b tpro ok          exec_setup_tpro
    v341 c swapmap ok       swap_task_map(task, thread, map)
    v341 d oldmap freed     vm_map_deallocate(old_map)
    v341 e exec state ok    activate_exec_state (installs pc/sp from LC_UNIXTHREAD)
    v341 f stack call       about to create_unix_stack
    v341 g execve ret       execve() returned in load_init_program_at_path
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(PATH, encoding='utf-8').read()
if 'v341 a lret ok' in s:
    print('patch_v341: already applied')
    sys.exit(0)


def mark(label, indent='\t'):
    return ('%s{ extern void g0245d_status(const char *);\n'
            '%s  g0245d_status("%s"); }\n' % (indent, indent, label))


edits = [
    # a: right after the lret panic guard
    ('\tif (lret != LOAD_SUCCESS) {\n'
     '\t\tpanic("g0245d v338 lret=%d", (int)lret);\n'
     '\t}\n',
     '\tif (lret != LOAD_SUCCESS) {\n'
     '\t\tpanic("g0245d v338 lret=%d", (int)lret);\n'
     '\t}\n' + mark('v341 a lret ok')),

    # b: after exec_setup_tpro
    ('\texec_setup_tpro(imgp, &load_result);\n',
     '\texec_setup_tpro(imgp, &load_result);\n' + mark('v341 b tpro ok')),

    # c: after swap_task_map
    ('\told_map = swap_task_map(task, thread, map);\n',
     '\told_map = swap_task_map(task, thread, map);\n' + mark('v341 c swapmap ok')),

    # d: after the old map is released
    ('\tvm_map_deallocate(old_map);\n\told_map = NULL;\n',
     '\tvm_map_deallocate(old_map);\n\told_map = NULL;\n' + mark('v341 d oldmap freed')),

    # e: after the thread state is installed
    ('\tlret = activate_exec_state(task, p, thread, &load_result);\n',
     '\tlret = activate_exec_state(task, p, thread, &load_result);\n' +
     mark('v341 e exec state ok')),

    # f: just before the unix stack is created
    ('\tif (load_result.unixproc &&\n'
     '\t    create_unix_stack(get_task_map(task),\n',
     mark('v341 f stack call') +
     '\tif (load_result.unixproc &&\n'
     '\t    create_unix_stack(get_task_map(task),\n'),

    # g: execve returned
    ('\terror = execve(p, &init_exec_args, retval);\n',
     '\terror = execve(p, &init_exec_args, retval);\n' + mark('v341 g execve ret')),
]

for old, new in edits:
    assert s.count(old) == 1, (old[:40], s.count(old))
    s = s.replace(old, new, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v341: 7 status-row breadcrumbs installed')
