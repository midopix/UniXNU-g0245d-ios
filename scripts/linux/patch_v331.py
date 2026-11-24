#!/usr/bin/env python3
"""g0245d v331: the scratch page in PID1's map is not faulting in.

v330 went further than any earlier build but then produced `v328 far 0x1000`
followed by a storm of `v328 ec 37` (data aborts).  0x1000 is the lowest
address in a user map that only has the PAGEZERO guard, which is exactly what
`mach_vm_allocate_kernel(current_map(), ...)` returns with VM_FLAGS_ANYWHERE.
That call only installs a lazy mapping; the physical page is supposed to
appear on the first fault via pmap_enter.  If PID1's pmap is not usable yet,
every copyout byte faults instead, and without a working recovery path each
fault becomes a kernel data abort.

This patch does two things at once:
  1. logs the allocation result, the address, and the map's pmap pointer, so we
     can tell "wrong map" from "right map, dead pmap";
  2. wires the page immediately (`vm_map_wire_kernel`), which forces
     vm_fault_enter -> pmap_enter up front and returns an error code instead of
     faulting later inside copyout.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/kern_exec.c')

OLD = (
    '\t(void) mach_vm_allocate_kernel(map, &scratch_addr, map_page_size, VM_FLAGS_ANYWHERE, VM_KERN_MEMORY_NONE);\n'
    '\t{ extern void g0245d_trace(const char *); g0245d_trace("v317 scratch ok"); }\n'
)

NEW = (
    '\t{\n'
    '\t\t/* g0245d v331: keep the result, then force the page resident.  The\n'
    '\t\t * allocate call only installs a lazy mapping; with PID1\'s pmap not\n'
    '\t\t * faulting yet, copyout(0x1000) becomes a storm of EL1 data aborts. */\n'
    '\t\textern void g0245d_trace(const char *);\n'
    '\t\textern void g0245d_trace_u(const char *, unsigned int);\n'
    '\t\textern void g0245d_tracev(const char *, unsigned long long);\n'
    '\t\tkern_return_t v331_rc = mach_vm_allocate_kernel(map, &scratch_addr,\n'
    '\t\t    map_page_size, VM_FLAGS_ANYWHERE, VM_KERN_MEMORY_NONE);\n'
    '\t\tg0245d_trace_u("v331 alloc rc", (unsigned int)v331_rc);\n'
    '\t\tg0245d_tracev("v331 scratch", (unsigned long long)scratch_addr);\n'
    '\t\tg0245d_tracev("v331 pmap", (unsigned long long)(uintptr_t)map->pmap);\n'
    '\t\tif (v331_rc == KERN_SUCCESS && scratch_addr != 0) {\n'
    '\t\t\tkern_return_t v331_wire = vm_map_wire_kernel(map,\n'
    '\t\t\t    (vm_map_offset_t)scratch_addr,\n'
    '\t\t\t    (vm_map_offset_t)(scratch_addr + map_page_size),\n'
    '\t\t\t    VM_PROT_READ | VM_PROT_WRITE, VM_KERN_MEMORY_NONE, TRUE);\n'
    '\t\t\tg0245d_trace_u("v331 wire rc", (unsigned int)v331_wire);\n'
    '\t\t}\n'
    '\t}\n'
    '\t{ extern void g0245d_trace(const char *); g0245d_trace("v317 scratch ok"); }\n'
)

text = open(PATH, encoding='utf-8').read()
if 'v331 alloc rc' in text:
    print('  scratch diagnostics: already applied')
else:
    if text.count(OLD) != 1:
        sys.exit(f'anchor count={text.count(OLD)}')
    open(PATH, 'w', encoding='utf-8').write(text.replace(OLD, NEW, 1))
    print('  scratch diagnostics + wire: applied')
