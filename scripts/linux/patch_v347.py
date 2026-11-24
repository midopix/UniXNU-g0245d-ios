#!/usr/bin/env python3
"""g0245d v347 -- print the map pointers involved in the fatal map switch.

v346 pinned the crash to PMAP_SWITCH_USER() inside vm_map_switch(old_map).

The two candidate maps:
  * old_map from swap_task_map()  -- the task's previous map, which
    exec_mach_imgact frees with vm_map_deallocate(old_map) a few lines later
  * old_map from vm_map_switch(get_task_map(task)) -- whatever the current
    thread had before it was switched onto the new task map

If the exec'ing thread is the init thread, those can be the very same map,
i.e. the switch-back targets a map that was already deallocated and whose pmap
is gone.  Print both pointers so the next photo settles it:

    v347 vs map=<arg> old=<thread->map before the switch>
    v347 call old_map=<value passed to vm_map_switch in kern_exec.c>
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')

s = open(EXEC, encoding='utf-8').read()
if 'v347 call old_map' in s:
    print('patch_v347: already applied')
    sys.exit(0)

# ---- kern_exec.c: what are we switching to?
A1 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v346 p2 pre switch"); }\n'
      '\tvm_map_switch(old_map);\n')
B1 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v346 p2 pre switch"); }\n'
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  static char v347buf[80];\n'
      '\t  snprintf(v347buf, sizeof(v347buf), "v347 call old_map=%p", (void *)old_map);\n'
      '\t  g0245d_status(v347buf); }\n'
      '\tvm_map_switch(old_map);\n')
assert s.count(A1) == 1, s.count(A1)
s = s.replace(A1, B1, 1)
open(EXEC, 'w', encoding='utf-8').write(s)

# ---- vm_map.c: the argument and the map we are leaving
v = open(VMAP, encoding='utf-8').read()
A2 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v346 vs enter"); }\n')
B2 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  static char v347vbuf[80];\n'
      '\t  snprintf(v347vbuf, sizeof(v347vbuf), "v347 vs map=%p old=%p",\n'
      '\t      (void *)map, (void *)oldmap);\n'
      '\t  g0245d_status(v347vbuf); }\n')
assert v.count(A2) == 1, v.count(A2)
v = v.replace(A2, B2, 1)
open(VMAP, 'w', encoding='utf-8').write(v)

print('patch_v347: map pointers printed at both ends of the switch')
