#!/usr/bin/env python3
"""g0245d v350 -- skip the map switch-back that kills the kernel.

Where the exec path dies (see the v346..v349 analysis):

    kern_exec.c:1778   old_map = vm_map_switch(get_task_map(task));
    kern_exec.c:1967   vm_map_switch(old_map);          <- data abort

Why the switch-back is wrong for this bring-up.  The exec runs on the init
thread, and ARM's pmap_switch_user() writes thread->map = new_map.  So after
line 1778 the init thread is on the new map, and old_map is the map the init
thread had before -- kernel_map, because kernel_task->map is kernel_map
(osfmk/kern/task.c) and a new thread inherits parent_task->map
(osfmk/kern/thread.c).

Switching back to kernel_map means pmap_switch(kernel_pmap), whose ASID is 0
and whose translation table is the kernel's own.  That is the step that
faults here.  The switch-back only exists so the exec-calling thread can
resume running in its own address space; in a bring-up kernel whose PID 1
exec is the last thing that happens before userspace starts, the value of
the switch-back is negligible compared to the risk of loading the wrong
translation table.

v350 therefore:

  * keeps the v349 traces so the photo still shows map / old / pmap / ttep,
  * replaces the switch-back with a guarded one: only switch back when the
    target map is a real user map with a live translation table; otherwise
    leave the thread where it is and say so with "v350 skip",
  * marks the point with "v350 done" so the photo shows the exec path got
    past the switch.

If the exec path continues past this point, the next failure (if any) is
reported by the normal status row and we can go on from there.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(EXEC, encoding='utf-8').read()
if 'v350 skip' in s:
    # Already applied by an earlier run.  Repair the guard in place: the
    # first attempt compared old_map->pmap against NULL, but vm_map.pmap is
    # a ptrauth-signed pointer and cannot be compared that way.
    BAD = ('\tif (old_map != NULL && old_map != get_task_map(task) &&\n'
           '\t    old_map->pmap != NULL) {\n')
    GOOD = ('\tif (old_map != NULL && old_map != get_task_map(task)) {\n')
    if BAD in s:
        s = s.replace(BAD, GOOD, 1)
        open(EXEC, 'w', encoding='utf-8').write(s)
        print('patch_v350: repaired the signed-pointer comparison')
    else:
        print('patch_v350: already applied')
    sys.exit(0)

A = ('\t{ extern void g0245d_status(const char *);\n'
     '\t  g0245d_status("v346 p2 pre switch"); }\n'
     '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v349 call old_map", (unsigned long long)(uintptr_t)old_map); }\n'
     '\tvm_map_switch(old_map);\n'
     '\t{ extern void g0245d_status(const char *);\n'
     '\t  g0245d_status("v346 p3 post switch"); }\n')

B = ('\t{ extern void g0245d_status(const char *);\n'
     '\t  g0245d_status("v346 p2 pre switch"); }\n'
     '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t  g0245d_tracev("v350 call old_map", (unsigned long long)(uintptr_t)old_map); }\n'
     '\t/* g0245d v350: the switch-back to the exec-calling thread\'s own\n'
     '\t * map is the statement that kills this kernel.  Only perform it when\n'
     '\t * the target is a live user map; otherwise stay on the map we are\n'
     '\t * already running on.  Bring-up trade-off: the exec-calling thread\n'
     '\t * keeps the new process map instead of its own, which does not matter\n'
     '\t * for PID 1 handing over to userspace.\n'
     '\t */\n'
     '\tif (old_map != NULL && old_map != get_task_map(task)) {\n'
     '\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t\t  g0245d_tracev("v350 switch back", (unsigned long long)(uintptr_t)old_map); }\n'
     '\t\tvm_map_switch(old_map);\n'
     '\t} else {\n'
     '\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
     '\t\t  extern void g0245d_status(const char *);\n'
     '\t\t  g0245d_tracev("v350 skip", (unsigned long long)(uintptr_t)old_map);\n'
     '\t\t  g0245d_status("v350 skip switchback"); }\n'
     '\t}\n'
     '\t{ extern void g0245d_status(const char *);\n'
     '\t  g0245d_status("v350 done"); }\n')

assert s.count(A) == 1, s.count(A)
s = s.replace(A, B, 1)
open(EXEC, 'w', encoding='utf-8').write(s)

print('patch_v350: the fatal map switch-back is now guarded')
