#!/usr/bin/env python3
"""g0245d v364 -- narrow the freeze: pmap_switch s1->s2 gap + execve prep area.

v363 photo (21:53): status=`v363 post` and heartbeat label `v357 s1` -- the
latest trace of THIS round is a fresh pmap_switch's s1 with NO s2/s3/s9 after it,
and the `v332 co path ok` trace (8735) must be a leftover of an earlier round
(because the very next statement writes `v360 path` status, which did NOT
appear).  So this round freezes between s1 and s2 in pmap_switch_internal() --
that gap contains only simple statements plus pmap_get_pt_attr() and an ASID==0
panic branch.  A fault inside pmap_get_pt_attr (corrupt pmap metadata) that
takes down sleh itself would look exactly like this.

v364: add status checkpoints to bisect BOTH suspect areas:
  pmap.c  s1 area:  v364 s1a (after pmap_get_pt_attr),
                    v364 s1b (after do_shared_region_flush computed)
  exec.c  prep:     v364 argv (after argv copyout),
                    v364 sstpre/v364 sstpost (around set_security_token)
Last visible status tells which statement is the last executed.  Additive only.

CUMULATIVE + IDEMPOTENT over v363.  Anchors unique.  No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
KE = os.path.join(W, "bsd", "kern", "kern_exec.c")
for f in (PMAPC, KE):
    if not os.path.isfile(f):
        sys.exit("required file not found: %s" % f)
MARK = "v364 s1a"
s = open(PMAPC, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v364: already applied -- skip")
    sys.exit(0)

def st(label):
    return ('\t{ extern void g0245d_status(const char *);\n'
            '\t  g0245d_status("%s"); }\n' % label)

def after_once(text, anchor, ins, label):
    c = text.count(anchor)
    if c != 1:
        sys.exit("patch_v364: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(anchor, anchor + ins, 1)

# ---- pmap.c: bisect s1 -> s2 ----
# s1a: after the pt_attr fetch (the suspect call); anchor includes the s1 trace
#      block so we only match the one inside pmap_switch_internal.
A1 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v357 s1", (unsigned long long)(uintptr_t)pmap); }\n'
      '\t__unused const pt_attr_t * const pt_attr = pmap_get_pt_attr(pmap);\n')
s = after_once(s, A1, st("v364 s1a"), "s1a")
# s1b: after the do_shared_region_flush computation
A2 = ('\tbool break_before_make = do_shared_region_flush;\n')
s = after_once(s, A2, st("v364 s1b"), "s1b")
open(PMAPC, "w", encoding="utf-8").write(s)
print("patch_v364: pmap.c s1a/s1b added")

# ---- kern_exec.c: bisect execve prep area ----
t = open(KE, encoding="utf-8", errors="replace").read()
# argv: after the 64-bit argv copyout (the branch launchd takes)
A3 = ('\t\t{ extern void g0245d_trace(const char *);\n'
      '\t\t  if (error == 0) { g0245d_trace("v332 co argv ok"); } }\n')
if t.count(A3) != 1:
    sys.exit("patch_v364: co argv anchor count=%d" % t.count(A3))
t = t.replace(A3, A3 + st("v364 argv"), 1)
# set_security_token: before and after
A4 = '\tset_security_token(p);\n'
if t.count(A4) != 1:
    sys.exit("patch_v364: set_security_token anchor count=%d" % t.count(A4))
t = t.replace(A4, st("v364 sstpre") + A4 + st("v364 sstpost"), 1)
open(KE, "w", encoding="utf-8").write(t)
print("patch_v364: kern_exec.c argv/sstpre/sstpost added")
print("patch_v364: done")
