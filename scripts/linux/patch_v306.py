#!/usr/bin/env python3
"""g0245d v306 -- boot-version sentinel to settle 'which kernel is running'.

Background:
  v305's boot.img/payload/kernel are 100% verified correct and contain all
  v305 probes, and flashing reported OK.  Yet the screen never showed ANY
  v305 trace and stayed at v304's `8566/8523 v304 dm kalloc ok`.  Since
  g0245d_trace() clears/enables the console on its first call (arm_init.c:1106),
  a genuine v305 boot would have shown the earliest traces from the top.  It
  did not -> the running kernel appears to be stale / not the freshly flashed
  boot (bootloader-layer issue, not a patch issue).

v306 (single early sentinel, label-only):
  startup.c kernel_bootstrap(): emit `v306 BOOT SENTINEL` right after the
  local declarations, before printf(version).  If after flashing v306 the
  screen shows this sentinel, the new kernel IS running (and we can resume
  the devfs_mount diagnosis).  If it does NOT appear, the bootloader is
  loading a stale/cached kernel -- a boot-layer problem to solve separately.

Idempotent.  Run on the tree that already has v305 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v306.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

STARTUP = os.path.join(WORK, "osfmk/kern/startup.c")
MARK = "g0245d v306"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what, count=1):
    n = src.count(old)
    if n != count:
        sys.exit("%s: anchor found %d times (expected %d)" % (what, n, count))
    return src.replace(old, new)


s = read(STARTUP)
if MARK in s:
    print("startup.c: already v306")
else:
    s = sub(
        s,
        """	g0245d_trace("v230 kernel_bootstrap entered");
	kern_return_t   result;
	thread_t        thread;
	char            namep[16];

	printf("%s\\n", version); /* log kernel version */""",
        """	g0245d_trace("v230 kernel_bootstrap entered");
	kern_return_t   result;
	thread_t        thread;
	char            namep[16];
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v306 BOOT SENTINEL"); }

	printf("%s\\n", version); /* log kernel version */""",
        "v306: boot sentinel",
    )
    write(STARTUP, s)
    print("startup.c: v306 boot sentinel installed")

print("v306 patch complete")
