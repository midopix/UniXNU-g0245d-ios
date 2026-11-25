#!/usr/bin/env python3
"""g0245d v366: move v365 status probe out of protected pmap code.

v365 called g0245d_status() from pmap_switch_internal(), which can be PPLTEXT
when XNU_MONITOR=1.  Ordinary framebuffer code is not safe there and may trap
before the workaround becomes visible.  Remove that call and place persistent
status markers in pmap_switch_user(), a normal-text wrapper around pmap_set_pmap.
"""
import os, sys
W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
P = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
s = open(P, encoding="utf-8", errors="replace").read()
mark = "v366 pre switch"
if mark in s:
    print("patch_v366: already applied -- skip")
    raise SystemExit(0)
old = '''\t{ extern void g0245d_status(const char *);\n\t  g0245d_status("v365 noSR"); }\n'''
if s.count(old) != 1:
    sys.exit("patch_v366: expected one v365 status call, found %d" % s.count(old))
s = s.replace(old, "", 1)
anchor = '''\tthread->map = new_map;\n\tpmap_set_pmap(new_pmap, thread);'''
replacement = '''\tthread->map = new_map;\n\t{ extern void g0245d_status(const char *);\n\t  g0245d_status("v366 pre switch"); }\n\tpmap_set_pmap(new_pmap, thread);\n\t{ extern void g0245d_status(const char *);\n\t  g0245d_status("v366 post switch"); }'''
if s.count(anchor) != 1:
    sys.exit("patch_v366: pmap_switch_user anchor not unique")
s = s.replace(anchor, replacement, 1)
open(P, "w", encoding="utf-8").write(s)
print("patch_v366: moved status probes to pmap_switch_user")
