#!/usr/bin/env python3
"""g0245d v346 -- catch the crash inside vm_map_switch(old_map).

v345 cleared exec_prefault_data: the status row ended on `v345 p prefault ok`,
so vm_fault() on the entry point page returned KERN_SUCCESS -- the __TEXT code
page really was paged in.  And `v345 q execsigs call` never appeared.

Between those two breadcrumbs there is exactly one statement:

    vm_map_switch(old_map);

which on arm64 does PMAP_SWITCH_USER() -- a hardware MMU switch to old_map's
pmap.  If old_map is stale (its pmap gone, or the thread no longer owns it)
that is exactly the kind of thing that produces a data abort with no panic.

Marks:
    v346 p2 pre switch / v346 p3 post switch   in kern_exec.c
    v346 vs enter / v346 vs pmap / v346 vs done inside vm_map_switch()
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')


def mark(label, indent='\t'):
    return ('%s{ extern void g0245d_status(const char *);\n'
            '%s  g0245d_status("%s"); }\n' % (indent, indent, label))


s = open(EXEC, encoding='utf-8').read()
if 'v346 p2 pre switch' in s:
    print('patch_v346: already applied')
    sys.exit(0)

A1 = '\tvm_map_switch(old_map);\n\n\t/*\n\t * Reset signal state.\n\t */\n'
B1 = (mark('v346 p2 pre switch') +
      '\tvm_map_switch(old_map);\n' +
      mark('v346 p3 post switch') +
      '\n\t/*\n\t * Reset signal state.\n\t */\n')
assert s.count(A1) == 1, s.count(A1)
s = s.replace(A1, B1, 1)
open(EXEC, 'w', encoding='utf-8').write(s)

v = open(VMAP, encoding='utf-8').read()
A2 = ('\tmp_disable_preemption();\n'
      '\tPMAP_SWITCH_USER(thread, map, cpu_number());\n'
      '\tmp_enable_preemption();\n')
B2 = (mark('v346 vs pmap', '\t') +
      '\tmp_disable_preemption();\n'
      '\tPMAP_SWITCH_USER(thread, map, cpu_number());\n' +
      mark('v346 vs done', '\t') +
      '\tmp_enable_preemption();\n')
assert v.count(A2) == 1, v.count(A2)
v = v.replace(A2, B2, 1)

A3 = ('\tvm_map_t        oldmap = thread->map;\n')
B3 = ('\tvm_map_t        oldmap = thread->map;\n' + mark('v346 vs enter', '\t'))
assert v.count(A3) == 1, v.count(A3)
v = v.replace(A3, B3, 1)

open(VMAP, 'w', encoding='utf-8').write(v)
print('patch_v346: vm_map_switch instrumented (enter / pmap / done) + call site marks')
