#!/usr/bin/env python3
"""g0245d v349 -- guard the fatal pmap switch on arm64.

v348 traced the map / old / pmap pointers of the switch that kills the
kernel, into the console trace ring so a photo can show them.

Where it dies:

    vm_map_switch(old_map)            <- osfmk/vm/vm_map.c
      PMAP_SWITCH_USER(thread, map, cpu_number())
        pmap_switch_user(thread, new_map)      <- osfmk/arm/pmap/pmap.c
          pmap_t new_pmap = new_map->pmap;      <- no NULL check
          thread->map = new_map;
          pmap_set_pmap(new_pmap, thread);
            pmap_switch(pmap)
              pmap_switch_internal(pmap)
                pmap_switch_user_ttb(pmap, ...)
                  set_mmu_ttb((pmap->ttep & TTBR_BADDR_MASK) | asid)

pmap_destroy() zeroes pmap->ttep when it tears a pmap down.  Switching to
such a pmap loads TTB = 0 into the MMU and every following user access
data-aborts with no panic -- exactly the silent death we see.

v349 therefore guards the switch inside pmap_switch_user(), where the pmap
struct lives and where the ARM-specific fields (ttep, hw_asid) are visible:

  * if the target map or its pmap is missing, or the pmap's translation
    table has already been torn down (ttep == 0), the switch is refused and
    the thread stays on the map it already runs on,
  * otherwise the upstream switch happens unchanged.

The refusal is traced as "v349 skip" so the photo states which branch ran,
and the pmap's ttep / asid are traced as well so a healthy-looking map with
a bad ttep is distinguishable from a freed map.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')
VMAP = os.path.join(W, 'osfmk/vm/vm_map.c')
PMAPC = os.path.join(W, 'osfmk/arm/pmap/pmap.c')

s = open(EXEC, encoding='utf-8').read()
if 'v349 call old_map' in s:
    print('patch_v349: already applied')
    sys.exit(0)

# ---- kern_exec.c: keep the trace of the map we switch back to.
A0 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v348 call old_map", (unsigned long long)(uintptr_t)old_map); }\n')
B0 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v349 call old_map", (unsigned long long)(uintptr_t)old_map); }\n')
assert s.count(A0) == 1, s.count(A0)
s = s.replace(A0, B0, 1)
open(EXEC, 'w', encoding='utf-8').write(s)

# ---- vm_map.c: keep the trace of the argument and the map we leave.
v = open(VMAP, encoding='utf-8').read()
A1 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v348 vs map", (unsigned long long)(uintptr_t)map);\n'
      '\t  g0245d_tracev("v348 vs old", (unsigned long long)(uintptr_t)oldmap);\n'
      '\t  g0245d_tracev("v348 vs pmap", (unsigned long long)(uintptr_t)map->pmap); }\n')
B1 = ('\tvm_map_t        oldmap = thread->map;\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v349 vs map", (unsigned long long)(uintptr_t)map);\n'
      '\t  g0245d_tracev("v349 vs old", (unsigned long long)(uintptr_t)oldmap); }\n')
assert v.count(A1) == 1, v.count(A1)
v = v.replace(A1, B1, 1)

A2 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v348 vs pmap FAULT"); }\n')
B2 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v349 vs pmap"); }\n')
assert v.count(A2) == 1, v.count(A2)
v = v.replace(A2, B2, 1)
open(VMAP, 'w', encoding='utf-8').write(v)

# ---- arm/pmap/pmap.c: the real guard.
p = open(PMAPC, encoding='utf-8').read()
A3 = ('void\n'
      'pmap_switch_user(thread_t thread, vm_map_t new_map)\n'
      '{\n'
      '\tpmap_t new_pmap = new_map->pmap;\n'
      '\n'
      '\n'
      '\tthread->map = new_map;\n'
      '\tpmap_set_pmap(new_pmap, thread);\n'
      '\n'
      '}\n')
B3 = ('void\n'
      'pmap_switch_user(thread_t thread, vm_map_t new_map)\n'
      '{\n'
      '\tpmap_t new_pmap = new_map->pmap;\n'
      '\n'
      '\t/* g0245d v349: refuse to activate a pmap whose translation table\n'
      '\t * has already been torn down.  pmap_destroy() zeroes pmap->ttep,\n'
      '\t * and pmap_switch_user_ttb() would then load TTB = 0 into the MMU,\n'
      '\t * turning the next user access into a silent data abort.  During\n'
      '\t * bring-up it is far better to stay on the current map than to\n'
      '\t * load a null page table.\n'
      '\t */\n'
      '\tif (new_map == NULL || new_pmap == NULL || new_pmap->ttep == 0) {\n'
      '\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t\t  extern void g0245d_status(const char *);\n'
      '\t\t  g0245d_tracev("v349 skip map", (unsigned long long)(uintptr_t)new_map);\n'
      '\t\t  g0245d_tracev("v349 skip pmap", (unsigned long long)(uintptr_t)new_pmap);\n'
      '\t\t  g0245d_tracev("v349 skip ttep",\n'
      '\t\t      (unsigned long long)(uintptr_t)(new_pmap ? new_pmap->ttep : 0));\n'
      '\t\t  g0245d_status("v349 skip switch"); }\n'
      '\t\treturn;\n'
      '\t}\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v349 pmap ttep", (unsigned long long)(uintptr_t)new_pmap->ttep);\n'
      '\t  g0245d_tracev("v349 pmap asid", (unsigned long long)(uintptr_t)new_pmap->hw_asid); }\n'
      '\n'
      '\tthread->map = new_map;\n'
      '\tpmap_set_pmap(new_pmap, thread);\n'
      '\n'
      '}\n')
assert p.count(A3) == 1, p.count(A3)
p = p.replace(A3, B3, 1)
open(PMAPC, 'w', encoding='utf-8').write(p)

print('patch_v349: pmap_switch_user guards against a torn-down pmap')
