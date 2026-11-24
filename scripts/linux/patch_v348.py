#!/usr/bin/env python3
"""g0245d v348 -- make the fatal map switch readable from a photo.

v347 printed the two map pointers with g0245d_status(), but that writes one
fixed row: the following "v346 vs pmap" overwrites it, so a photo of v347
looks exactly like a photo of v346.  v348 therefore

  * prints the pointers into the scrolling trace ring (g0245d_tracev), so
    they survive until the ring wraps,
  * keeps the fixed status row for the last state reached, and
  * additionally prints the pmap pointer of the target map, because
    pmap_switch_user() dereferences new_map->pmap without a NULL check.

The decisive value is the pmap pointer of the map we switch *to*: if it is
garbage (or the map was already freed) the fault is a dangling map; if it is
a sane value the fault is inside the ARM pmap switch itself.

    v348 vs map=<arg> old=<thread->map> pmap=<arg->pmap>
    v348 call old_map=<value passed from kern_exec.c>
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')

s = open(EXEC, encoding='utf-8').read()
if 'v348 call old_map' in s:
    print('patch_v348: already applied')
    sys.exit(0)

# ---- kern_exec.c: trace the map we are about to switch to.
A1 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  static char v347buf[80];\n'
      '\t  snprintf(v347buf, sizeof(v347buf), "v347 call old_map=%p", (void *)old_map);\n'
      '\t  g0245d_status(v347buf); }\n')
B1 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v348 call old_map", (unsigned long long)(uintptr_t)old_map); }\n')
assert s.count(A1) == 1, s.count(A1)
s = s.replace(A1, B1, 1)
open(EXEC, 'w', encoding='utf-8').write(s)

# ---- vm_map.c: trace the argument, the map we leave and the target pmap.
v = open(VMAP, encoding='utf-8').read()
A2 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  static char v347vbuf[80];\n'
      '\t  snprintf(v347vbuf, sizeof(v347vbuf), "v347 vs map=%p old=%p",\n'
      '\t      (void *)map, (void *)oldmap);\n'
      '\t  g0245d_status(v347vbuf); }\n')
B2 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v348 vs map", (unsigned long long)(uintptr_t)map);\n'
      '\t  g0245d_tracev("v348 vs old", (unsigned long long)(uintptr_t)oldmap);\n'
      '\t  g0245d_tracev("v348 vs pmap", (unsigned long long)(uintptr_t)map->pmap); }\n')
assert v.count(A2) == 1, v.count(A2)
v = v.replace(A2, B2, 1)

# The status row must name the last state reached, so keep it but make it
# unambiguous that it is the pmap switch that faults.
A3 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v346 vs pmap"); }\n')
B3 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v348 vs pmap FAULT"); }\n')
assert v.count(A3) == 1, v.count(A3)
v = v.replace(A3, B3, 1)
open(VMAP, 'w', encoding='utf-8').write(v)

print('patch_v348: map/old/pmap pointers now go to the trace ring')
