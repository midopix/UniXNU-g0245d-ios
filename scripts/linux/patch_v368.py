#!/usr/bin/env python3
"""g0245d v368: make first-fault capture non-recursive.

v367 reached invalid-stack panic before its status row was readable. The
synchronous handler was doing five trace calls plus framebuffer status on every
DABORT, while the old v328 block added two more calls. Keep only one raw first
fault record and remove all high-frequency exception output.
"""
import os, sys
W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
SLEH = os.path.join(W, "osfmk", "arm64", "sleh.c")
if not os.path.isfile(SLEH):
    sys.exit("required file not found: " + SLEH)
s = open(SLEH, encoding="utf-8", errors="replace").read()
if '"v368 far"' not in s:
    anchor = '\t/* g0245d v328: v327\'s panic hook never fired, so log the exception\n'
    if s.count(anchor) != 1:
        sys.exit("v368: v328 anchor count != 1")
    block = '''\t/* g0245d v368: capture only the first synchronous fault. */
\t{ extern void g0245d_tracev(const char *, unsigned long long);
\t  static unsigned int v368_once;
\t  if (!v368_once++) {
\t    g0245d_tracev("v368 esr", (unsigned long long)esr);
\t    g0245d_tracev("v368 far", (unsigned long long)(uintptr_t)far);
\t    g0245d_tracev("v368 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state));
\t    g0245d_tracev("v368 x0", (unsigned long long)get_saved_state_reg(state, 0));
\t    g0245d_tracev("v368 x1", (unsigned long long)get_saved_state_reg(state, 1));
\t  }
\t}
'''
    s = s.replace(anchor, block + anchor, 1)
    print("v368: first-fault-only register trace installed")
else:
    print("v368: first-fault trace already present")
# Remove the v358 status formatter entirely; it consumes stack and does cache
# maintenance on every exception even when the trace is one-shot.
start = s.find("\t/* g0245d v358: print the fault on the STATUS row")
end = s.find("\t/* g0245d v328:", start)
if start >= 0 and end > start:
    s = s[:start] + s[end:]
    print("v368: v358 status formatter removed")
elif start < 0:
    print("v368: v358 status formatter already removed")
else:
    sys.exit("v368: v358 status block bounds invalid")
# Disable legacy high-frequency exception output.
old_guard = 'static int g0245d_sync_left = 12;'
new_guard = 'static int g0245d_sync_left = 0; /* g0245d v368: no recursive flood */'
if old_guard in s:
    s = s.replace(old_guard, new_guard, 1)
    print("v368: v328 exception flood disabled")
elif 'v368: no recursive flood' in s:
    print("v368: v328 exception flood already disabled")
else:
    sys.exit("v368: v328 counter anchor not found")
open(SLEH, "w", encoding="utf-8").write(s)
