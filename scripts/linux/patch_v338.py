#!/usr/bin/env python3
"""g0245d v338 -- put the diagnostics into the panic message, not the trace ring.

v337 confirmed the ring is not a reliable readout any more: after the debugger
repaints, the screen kept a single trace line, so the v337 values were lost.

The panic text, on the other hand, is expanded and pinned on the status row at
the bottom of the screen, and it survived every previous photo.  So move the
diagnostics there: replace the two LOAD_NOSPACE returns inside the loader with
a panic that carries the numbers.

  1. parse_machfile: kalloc_data() for the load-command buffer returned NULL
       -> panic "v338 kalloc nul"

  2. load_segment: map_segment() failed
       -> panic "v338 mseg ret=<rc> seg=<tag> vm=<a>-<b> f=<c>-<d> ubc=<0|1>"

  3. exec_mach_imgact: any non-zero lret
       -> panic "v338 lret=<n>"  (catches NOSPACE from anywhere else)

`seg` prints the first four segname bytes as hex: 0x41505f5f = "__PA"(__PAGEZERO),
0x45545f5f = "__TE"(__TEXT).  `ubc` says whether ubc_getobject() found a pager.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
ML = os.path.join(W, 'bsd/kern/mach_loader.c')
EX = os.path.join(W, 'bsd/kern/kern_exec.c')

s = open(ML, encoding='utf-8').read()
if 'v338 mseg' in s:
    print('patch_v338: already applied')
    sys.exit(0)

# 1. load-command buffer allocation failed
A1 = ('\taddr = kalloc_data(alloc_size, Z_WAITOK);\n'
      '\tif (addr == NULL) {\n'
      '\t\treturn LOAD_NOSPACE;\n'
      '\t}\n')
B1 = ('\taddr = kalloc_data(alloc_size, Z_WAITOK);\n'
      '\tif (addr == NULL) {\n'
      '\t\tpanic("g0245d v338 kalloc nul size=%u", (unsigned int)alloc_size);\n'
      '\t\treturn LOAD_NOSPACE;\n'
      '\t}\n')
assert s.count(A1) == 1
s = s.replace(A1, B1, 1)

# 2. segment mapping failed
A2 = ('\t\tif (ret) {\n'
      '\t\t\tDEBUG4K_ERROR("LOAD_NOSPACE start 0x%llx end 0x%llx ret 0x%x\\n", '
      '(uint64_t)vm_start, (uint64_t)vm_end, ret);\n'
      '\t\t\treturn LOAD_NOSPACE;\n'
      '\t\t}\n')
B2 = ('\t\tif (ret) {\n'
      '\t\t\tpanic("g0245d v338 mseg ret=%d seg=%x vm=%llx-%llx f=%llx-%llx ubc=%d",\n'
      '\t\t\t    (int)ret,\n'
      '\t\t\t    (unsigned int)(*(const unsigned int *)(const void *)scp->segname),\n'
      '\t\t\t    (uint64_t)vm_start, (uint64_t)vm_end,\n'
      '\t\t\t    (uint64_t)file_start, (uint64_t)file_end,\n'
      '\t\t\t    (int)(control != MEMORY_OBJECT_CONTROL_NULL));\n'
      '\t\t\treturn LOAD_NOSPACE;\n'
      '\t\t}\n')
assert s.count(A2) == 1
s = s.replace(A2, B2, 1)
open(ML, 'w', encoding='utf-8').write(s)

# 3. any other non-zero lret
e = open(EX, encoding='utf-8').read()
A3 = ('\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
      '\t  g0245d_trace_u("v333 lret", (unsigned int)lret); }\n')
B3 = (A3 +
      '\tif (lret != LOAD_SUCCESS) {\n'
      '\t\tpanic("g0245d v338 lret=%d", (int)lret);\n'
      '\t}\n')
assert e.count(A3) == 1
open(EX, 'w', encoding='utf-8').write(e.replace(A3, B3, 1))

print('patch_v338: NOSPACE diagnostics moved into panic messages')
