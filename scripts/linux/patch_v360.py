#!/usr/bin/env python3
"""g0245d v360 -- mirror execve-internal milestones onto the STATUS row.

v359 photos: status stays at `v359 try i=0 err=2` (i=0 = launchd.development is
a designed-in ENOENT fallback), but the trace ring shows pmap_switch returning
twice (`v356 post`) and `v256 hi alloc ret <non-null>` -- i.e. i=1 (/sbin/launchd)
is deep inside execve/Mach-O loading.  The status row only gets written when
load_init_program_at_path() RETURNS, so it can't tell us how far i=1 got.

v360: mirror five read-only milestones onto the status row (which never
scrolls):
  1. path copied        (v332 co path ok)   -> "v360 path"
  2. execve() called    (v318 execve call)  -> "v360 call"
  3. Mach-O parsed      (v335 parse ok)     -> "v360 parse"
  4. load_machfile done (v335 halt ok)      -> "v360 halt"
  5. execve returned    (v359 exret)        -> "v360 eret err=%u"
The LAST visible status is therefore the deepest stage i=1 reached.  All are
additive to (do not remove) the existing traces.  No behavior change.

CUMULATIVE + IDEMPOTENT over v359.  Anchors come from common early patches and
exist on BOTH bring-up lines.  No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
KE = os.path.join(W, "bsd", "kern", "kern_exec.c")
ML = os.path.join(W, "bsd", "kern", "mach_loader.c")
for f in (KE, ML):
    if not os.path.isfile(f):
        sys.exit("required file not found: %s" % f)
MARK = "v360 path"
s = open(KE, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v360: already applied -- skip")
    sys.exit(0)

def mirror_after(text, anchor, label, expected=1):
    c = text.count(anchor)
    if c != expected:
        sys.exit("patch_v360: anchor %r count=%d (want %d)" % (anchor[:50], c, expected))
    ins = ('\t{ extern void g0245d_status(const char *);\n'
           '\t  g0245d_status("%s"); }\n' % label)
    return text.replace(anchor, anchor + ins, 1)

# 1. path copied (inside load_init_program_at_path)
A1 = ('\t  if (error == 0) { g0245d_trace("v332 co path ok"); } }\n')
s = mirror_after(s, A1, "v360 path")
# 2. execve() about to be called
A2 = ('\t{ extern void g0245d_trace(const char *); g0245d_trace("v318 execve call"); }\n')
s = mirror_after(s, A2, "v360 call")

open(KE, "w", encoding="utf-8").write(s)
print("patch_v360: kern_exec.c path/call status mirrors added")

# 3/4. mach_loader.c milestones
t = open(ML, encoding="utf-8", errors="replace").read()
A3 = ('\t  g0245d_trace("v335 parse ok"); }\n')
t = mirror_after(t, A3, "v360 parse")
A4 = ('\t  g0245d_trace("v335 halt ok"); }\n')
t = mirror_after(t, A4, "v360 halt")
open(ML, "w", encoding="utf-8").write(t)
print("patch_v360: mach_loader.c parse/halt status mirrors added")

# 5. execve returned errno -- extend the v359 exret status
#    (v359 writes `v359 exret err=%u`; add a second status line after it)
s = open(KE, encoding="utf-8", errors="replace").read()
A5 = ('\t  g0245d_status(v359buf); }\n')
if s.count(A5) != 1:
    sys.exit("patch_v360: v359 exret status block count=%d" % s.count(A5))
INS5 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  static char v360ebuf[96];\n'
        '\t  snprintf(v360ebuf, sizeof(v360ebuf), "v360 eret err=%u",\n'
        '\t      (unsigned int)(error));\n'
        '\t  g0245d_status(v360ebuf); }\n')
s = s.replace(A5, A5 + INS5, 1)
open(KE, "w", encoding="utf-8").write(s)
print("patch_v360: execve-return errno status added")
print("patch_v360: done")
