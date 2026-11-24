#!/usr/bin/env python3
"""g0245d v363 -- trace the pmap_switch() RETURN path on the status row.

v362 photo (21:44): status=`v362 s9a` (last probe inside pmap_switch_internal,
after the TTBR switch).  The existing `v356 post` (pmap_switch), `v346 vs done`
(vm_map_switch) status/trace points did NOT appear this round => the freeze is
somewhere on the RETURN path from s9a back to vm_map_exec:
  pmap_switch_internal (s9a) -> pmap_switch (v356 post) ->
  pmap_set_pmap (v356 sdone) -> pmap_switch_user -> vm_map_switch (v346 vs done)
  -> vm_map_exec (v342 b5 vmexec ok)

v363: add status checkpoints on each return layer (additive, no behavior change):
  v363 sdone -- after pmap_switch() returns inside pmap_set_pmap
  v363 su    -- after pmap_set_pmap() returns inside pmap_switch_user
  v363 vmsw  -- after PMAP_SWITCH_USER inside vm_map_switch (next to v346 vs done)
Plus mirror v356 post trace to status inside pmap_switch.
Last visible status = the deepest return layer reached.

NOTE heisenbug: each boot round freezes at a different stage; use the MODE of
several photos, not a single one.  This build makes every return layer visible.

CUMULATIVE + IDEMPOTENT over v362.  Anchors unique.  No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
VMMAPC = os.path.join(W, "osfmk", "vm", "vm_map.c")
for f in (PMAPC, VMMAPC):
    if not os.path.isfile(f):
        sys.exit("required file not found: %s" % f)
MARK = "v363 sdone"
s = open(PMAPC, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v363: already applied -- skip")
    sys.exit(0)

def st(label):
    return ('\t{ extern void g0245d_status(const char *);\n'
            '\t  g0245d_status("%s"); }\n' % label)

def after_once(text, anchor, ins, label):
    c = text.count(anchor)
    if c != 1:
        sys.exit("patch_v363: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(anchor, anchor + ins, 1)

# 1. v363 post: after v356 post trace inside pmap_switch
A1 = '\t  g0245d_tracev("v356 post", (unsigned long long)(uintptr_t)pmap); }'
s = after_once(s, A1, st("v363 post"), "post")
# 2. v363 sdone: after v356 sdone trace inside pmap_set_pmap
A2 = '\t  g0245d_tracev("v356 sdone", (unsigned long long)(uintptr_t)pmap); }'
s = after_once(s, A2, st("v363 sdone"), "sdone")
# 3. v363 su: after pmap_set_pmap(new_pmap, thread); inside pmap_switch_user
A3 = '\tpmap_set_pmap(new_pmap, thread);'
s = after_once(s, A3, st("v363 su"), "su")
open(PMAPC, "w", encoding="utf-8").write(s)
print("patch_v363: pmap.c post/sdone/su status probes added")

# 4. v363 vmsw: after PMAP_SWITCH_USER inside vm_map_switch
t = open(VMMAPC, encoding="utf-8", errors="replace").read()
A4 = '\tPMAP_SWITCH_USER(thread, map, cpu_number());'
if t.count(A4) != 1:
    sys.exit("patch_v363: PMAP_SWITCH_USER anchor count=%d" % t.count(A4))
t = t.replace(A4, A4 + st("v363 vmsw"), 1)
open(VMMAPC, "w", encoding="utf-8").write(t)
print("patch_v363: vm_map.c vmsw status probe added")
print("patch_v363: done")
