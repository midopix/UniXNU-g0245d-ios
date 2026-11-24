#!/usr/bin/env python3
"""g0245d v342 -- fill the gap between 'tpro ok' and 'swapmap ok'.

v341's boot was the cleanest yet and already tells us a lot:

    v337 seg 0x41505f5f (__PAGEZERO) ls rc 0
    v337 seg 0x45545f5f (__TEXT)     ls rc 0     __TEXT is mapped
    v335 parse ok
    v335 halt ok
    v333 lret 0                                 load_machfile fully succeeded
    status: v341 b tpro ok                      died before 'c swapmap ok'

So everything up to exec_setup_tpro() is done and swap_task_map() is never
reached.  In between:

    vm_map_set_size_limit / set_data_limit / set_user_wire_limit
    proc_unlock
    code-signing flag propagation
    vm_map_exec()        <- sets up the new address space for the task
    fdt_exec()           <- close-on-exec fd sweep
    exec_handle_sugid()

Breadcrumbs (b2..b7) divide that stretch so the next photo names the exact call.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(PATH, encoding='utf-8').read()
if 'v342 b4 vmexec call' in s:
    print('patch_v342: already applied')
    sys.exit(0)


def mark(label, indent='\t'):
    return ('%s{ extern void g0245d_status(const char *);\n'
            '%s  g0245d_status("%s"); }\n' % (indent, indent, label))


edits = [
    # b2: the three vm_map limit calls returned
    ('\tvm_map_set_size_limit(map, proc_limitgetcur(p, RLIMIT_AS));\n'
     '\tvm_map_set_data_limit(map, proc_limitgetcur(p, RLIMIT_DATA));\n'
     '\tvm_map_set_user_wire_limit(map, (vm_size_t)proc_limitgetcur(p, RLIMIT_MEMLOCK));\n',
     '\tvm_map_set_size_limit(map, proc_limitgetcur(p, RLIMIT_AS));\n'
     '\tvm_map_set_data_limit(map, proc_limitgetcur(p, RLIMIT_DATA));\n'
     '\tvm_map_set_user_wire_limit(map, (vm_size_t)proc_limitgetcur(p, RLIMIT_MEMLOCK));\n' +
     mark('v342 b2 limits ok')),

    # b3: code-signing flags propagated
    ('#if __has_feature(ptrauth_calls) && defined(XNU_TARGET_OS_OSX)\n'
     '\t/*\n'
     '\t * ptrauth version 0 is a preview ABI.',
     mark('v342 b3 cs ok') +
     '#if __has_feature(ptrauth_calls) && defined(XNU_TARGET_OS_OSX)\n'
     '\t/*\n'
     '\t * ptrauth version 0 is a preview ABI.'),

    # b4/b5: around vm_map_exec
    ('\tvm_map_exec(map, task, load_result.is_64bit_addr,\n'
     '\t    (void *)p->p_fd.fd_rdir, cputype, cpu_subtype, reslide,\n'
     '\t    (imgp->ip_flags & IMGPF_DRIVER) != 0,\n'
     '\t    rsr_version);\n',
     mark('v342 b4 vmexec call') +
     '\tvm_map_exec(map, task, load_result.is_64bit_addr,\n'
     '\t    (void *)p->p_fd.fd_rdir, cputype, cpu_subtype, reslide,\n'
     '\t    (imgp->ip_flags & IMGPF_DRIVER) != 0,\n'
     '\t    rsr_version);\n' +
     mark('v342 b5 vmexec ok')),

    # b6: fd sweep done
    ('\tfdt_exec(p, psa != NULL ? psa->psa_flags : 0, imgp->ip_new_thread, exec);\n',
     '\tfdt_exec(p, psa != NULL ? psa->psa_flags : 0, imgp->ip_new_thread, exec);\n' +
     mark('v342 b6 fdt ok')),

    # b7: about to swap the task map
    ('\told_map = swap_task_map(task, thread, map);\n',
     mark('v342 b7 pre swapmap') +
     '\told_map = swap_task_map(task, thread, map);\n'),
]

for old, new in edits:
    assert s.count(old) == 1, (old.split('\n')[0][:50], s.count(old))
    s = s.replace(old, new, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v342: b2..b7 breadcrumbs installed')
