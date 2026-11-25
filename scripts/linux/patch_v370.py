#!/usr/bin/env python3
"""patch_v370 -- bisect the pmap_switch return window (v369 photo evidence).

Evidence (v369 screen, 2026-11-25 14:41:33):
  last trace label = "v356 post"  (hb307 8732/8688)
  last status      = "v362 s9a"
  => pmap_switch_internal() returned and the "v356 post" trace was printed,
     but the very next statement -- g0245d_status("v363 post") -- never wrote.

So the freeze is inside this 3-statement window:
      pmap_switch_internal(pmap);
      tracev("v356 post", ...);
      status("v363 post");          <-- never appeared
      PMAP_TRACE(... DBG_FUNC_END);

v370 brackets the window with two status sentinels (status does not consume
trace seq and does not touch the fixed hb row, so it is the reliable channel
while the trace ring tail is being overwritten):

  v370 a : right after pmap_switch_internal()/pmap_switch_ppl() returns,
           BEFORE the "v356 post" trace
  v370 b : at the top of pmap_set_pmap, right after pmap_switch() returns,
           BEFORE the "v356 sdone" trace

Reading rules:
  last status still "v362 s9a"  -> died inside pmap_switch_internal()'s own
                                   return (epilogue/ret), i.e. the return path
                                   after the TTBR switch is broken
  last status "v370 a"          -> internal returned, died inside the
                                   "v356 post" console write (framebuffer
                                   access right after TTBR switch)
  last status "v363 post"       -> got past the old freeze; died in v370 b or
                                   in the "v356 sdone" console write
  last status "v370 b"          -> died inside the "v356 sdone" console write
                                   (pmap_set_pmap's first trace)

Additive only, no behaviour change. CUMULATIVE + IDEMPOTENT over v369.
"""

import os
import sys

W = os.environ.get("XNU_WORK") or sys.exit("patch_v370: set XNU_WORK")
P = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
s = open(P, encoding="utf-8", errors="replace").read()

if "v370 a" in s:
    print("patch_v370: already applied -- skip")
    raise SystemExit(0)

ST = '\t{ extern void g0245d_status(const char *);\n\t  g0245d_status("%s"); }\n'


def once(text, anchor, ins, label):
    c = text.count(anchor)
    if c != 1:
        sys.exit("patch_v370: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(anchor, anchor + ins, 1)


# --- v370 a: after the internal/ppl switch returns, before "v356 post" ------
A1 = """#if XNU_MONITOR
\tpmap_switch_ppl(pmap);
#else
\tpmap_switch_internal(pmap);
#endif
"""
s = once(s, A1, ST % "v370 a", "a")

# --- v370 b: top of pmap_set_pmap, right after pmap_switch() returns --------
A2 = """\t{ extern void g0245d_tracev(const char *, unsigned long long);
\t  g0245d_tracev("v356 spmap", (unsigned long long)(uintptr_t)pmap); }
\tpmap_switch(pmap);
"""
s = once(s, A2, ST % "v370 b", "b")

open(P, "w", encoding="utf-8").write(s)
print("patch_v370: v370 a + v370 b status sentinels added")
print("patch_v370: done")
