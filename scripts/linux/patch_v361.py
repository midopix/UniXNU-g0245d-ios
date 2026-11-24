#!/usr/bin/env python3
"""g0245d v361 -- pinpoint the execve() early-stage freeze on the STATUS row.

v360 photo (21:27): status = `v360 call` -- execve() WAS called (v360 path was
overwritten by v360 call), but NONE of v360 parse/halt/eret appeared.  So the
current run is stuck INSIDE execve(), early: __mac_execve's namei() / file read
/ image-activator selection, BEFORE exec_mach_imgact's vm_map_exec (which would
have written v342 b4/b5 status).  The pmap_switch traces in the ring are from
earlier rounds (heisenbug); status is authoritative.

v361: add status-row checkpoints around __mac_execve's namei() and at the
exec_mach_imgact entry:
  1. v361 mentry   -- __mac_execve entered
  2. v361 prenamei -- right before namei(ndp)
  3. v361 namei e=%u -- right after namei(), with errno
  4. v361 imgact   -- exec_mach_imgact entry (v333 area)
Last visible status = how far execve() got.  Additive only, no behavior change.

CUMULATIVE + IDEMPOTENT over v360.  Anchors are stable in both bring-up lines.
No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
KE = os.path.join(W, "bsd", "kern", "kern_exec.c")
if not os.path.isfile(KE):
    sys.exit("required file not found: %s" % KE)
MARK = "v361 prenamei"
s = open(KE, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v361: already applied -- skip")
    sys.exit(0)

# 1. __mac_execve entry: anchor on its function signature line
A1 = ('__mac_execve(proc_t p, struct __mac_execve_args *uap, '
      'int32_t *retval __unused)\n{\n')
if s.count(A1) != 1:
    sys.exit("patch_v361: need 1 __mac_execve signature, found %d" % s.count(A1))
INS1 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  g0245d_status("v361 mentry"); }\n')
s = s.replace(A1, A1 + INS1, 1)
print("patch_v361 STEP1: __mac_execve entry status")

# 2. pre-namei: insert before `again:` label
A2 = 'again:\n\terror = namei(ndp);\n'
if s.count(A2) != 1:
    sys.exit("patch_v361: need 1 namei block, found %d" % s.count(A2))
INS2 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  g0245d_status("v361 prenamei"); }\n')
s = s.replace(A2, INS2 + A2, 1)
print("patch_v361 STEP2: pre-namei status")

# 3. after namei error check, before assigning ip_ndp
A3 = '\timgp->ip_ndp = ndp;     /* successful namei(); call nameidone() later */'
if s.count(A3) != 1:
    sys.exit("patch_v361: ip_ndp anchor failed %d" % s.count(A3))
B3 = ('\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v361 namei ok"); }\n')
s = s.replace(A3, B3 + A3, 1)
print("patch_v361 STEP3: post-namei status")

# 4. exec_mach_imgact entry
A4 = ('exec_mach_imgact(struct image_params *imgp)\n{\n')
if s.count(A4) != 1:
    sys.exit("patch_v361: need 1 exec_mach_imgact signature, found %d" % s.count(A4))
INS4 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  g0245d_status("v361 imgact"); }\n')
s = s.replace(A4, A4 + INS4, 1)
print("patch_v361 STEP4: exec_mach_imgact entry status")

open(KE, "w", encoding="utf-8").write(s)
print("patch_v361: wrote %s" % KE)
print("patch_v361: done")
