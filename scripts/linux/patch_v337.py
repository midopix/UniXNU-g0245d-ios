#!/usr/bin/env python3
"""g0245d v337 -- who returns LOAD_NOSPACE inside parse_machfile?

v336's __PAGEZERO fix worked (type ncmds 131075 = (MH_EXECUTE<<16)|3,
sizeofcmds 432) but load_machfile now returns 5, i.e. LOAD_NOSPACE, and
`v335 parse ok` never printed -- so parse_machfile itself failed.

Inside parse_machfile the LOAD_NOSPACE exits are:
  * kalloc_data(alloc_size, Z_WAITOK) == NULL for the load-command buffer
  * load_segment() -> map_segment() -> vm_map_enter* failure

map_segment's behaviour depends on `control` from ubc_getobject(vp): with a
NULL control it cannot map from the file at all.  mockfs's vnode may well have
no UBC object attached, which would explain a mapping failure.

Probes:
    v337 ubc       1 == ubc_getobject() returned an object, 0 == NULL
    v337 seg <tag> first four segname bytes of the segment about to be mapped
    v337 ls rc <n> load_segment()'s return value for that segment

So the screen shows, per segment, what it was and what came back.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'bsd/kern/mach_loader.c')

s = open(PATH, encoding='utf-8').read()
if 'v337 ubc' in s:
    print('patch_v337: already applied')
    sys.exit(0)

# 1. did ubc_getobject() find a pager?
A1 = '\tcontrol = ubc_getobject(vp, UBC_FLAGS_NONE);\n'
B1 = (A1 +
      '\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
      '\t  g0245d_trace_u("v337 ubc", (unsigned int)(control != MEMORY_OBJECT_CONTROL_NULL)); }\n')
assert s.count(A1) == 1
s = s.replace(A1, B1, 1)

# 2/3. per 64-bit segment: segname tag + load_segment result
A2 = ('\t\t\t\tif (ret == LOAD_SUCCESS && scp64->fileoff == 0 && scp64->filesize > 0) {\n')
B2 = ('\t\t\t\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
      '\t\t\t\t  g0245d_trace_u("v337 seg",\n'
      '\t\t\t\t      (unsigned int)(*(const unsigned int *)(const void *)scp64->segname));\n'
      '\t\t\t\t  g0245d_trace_u("v337 ls rc", (unsigned int)ret); }\n' + A2)
assert s.count(A2) == 1
s = s.replace(A2, B2, 1)

open(PATH, 'w', encoding='utf-8').write(s)
print('patch_v337: ubc / segname / load_segment rc probes installed')
