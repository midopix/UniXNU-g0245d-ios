#!/usr/bin/env python3
"""g0245d v380 -- let mockfs resolve the DEVELOPMENT init path.

v379 photo (2026-11-26 10:57) ring 8680-8733, read after cropping:

    8722 v319 try 0 / v318 execve call      (overprinted row)
    8723 v256 hi elements 100
    8724 v256 hi size 64
    8725 v256 hi alloc enter
    8726 v274 hi caller 128116232
    8727 v256 hi alloc ret 0xfffffff40a7a2000
    8728 v319 lk sbin
    8729 v299 fsv enter
    8730 v299 fsv lock ok
    8731 v299 fsv done 0
    8732 v319 lk enoent
    8733 v371 lr 0xfffffff00748f23c        (_machine_switch_context + 0x58)
    -> panic: "Synchronous exception taken while SP1 selected at pc 0x..."

`strncmp(name, "sbin", 5) || strncmp(name, "usr", 4) || strncmp(name, "lib", 4)`
all print the SAME label, so "lk sbin" here is the **"usr"** component.  The build
is DEVELOPMENT, so kern_exec.c's init_programs[] starts with

    "/usr/appleinternal/sbin/launchd.development"

i.e. lookup sequence = usr (hit, maps to root) -> appleinternal (no such branch)
-> "v319 lk enoent".  mockfs can only serve sbin/usr/lib/dev/dyld/probe.bin/launchd,
so attempt 0 can never succeed, and the exec-failure unwind is what dies afterwards
(synchronous exception at EL1, ESR class never printed: the v369 sp1 probes are
`static ... once` and were already consumed earlier in this boot).

ONE嫌疑点: mockfs cannot resolve the first init candidate path; teach it the two
extra components so attempt 0 reaches the real launchd (the same N4KROOT MOCKFS_FILE
node that "/sbin/launchd" resolves to).

  "appleinternal"        -> root (same mapping as usr/sbin/lib)
  "launchd.development"  -> MOCKFS_FILE (same node as "launchd")

Safety net (diagnostic, no behaviour change): re-arm the SP1 synchronous-exception
probes as v380 sp1 esr/far/pc/ec, bounded to 6 hits.  The old v369 ones are
once-only and already spent, which is why this panic arrived without an ESR.

CUMULATIVE + IDEMPOTENT over v379.  Touches bsd/miscfs/mockfs/mockfs_vnops.c and
osfmk/arm64/sleh.c only.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")

VNOPS = os.path.join(W, "bsd/miscfs/mockfs/mockfs_vnops.c")
SLEH = os.path.join(W, "osfmk/arm64/sleh.c")
for p in (VNOPS, SLEH):
    if not os.path.isfile(p):
        sys.exit("required file not found: %s" % p)

src = open(VNOPS, encoding="utf-8", errors="replace").read()
if "v380 lk appint" in src:
    print("patch_v380: already applied -- skip")
    sys.exit(0)

# --- 1. mockfs: two extra components of the DEVELOPMENT init path -----------
old = ('\t\t} else if (!strncmp(cnp->cn_nameptr, "launchd", 8)) {\n'
       '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v319 lk launchd"); }\n'
       '\t\t\tmockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);\n'
       '\t\t} else {\n')
new = ('\t\t} else if (!strncmp(cnp->cn_nameptr, "launchd", 8)) {\n'
       '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v319 lk launchd"); }\n'
       '\t\t\tmockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);\n'
       '\t\t/* g0245d v380: DEVELOPMENT builds try\n'
       '\t\t * /usr/appleinternal/sbin/launchd.development before /sbin/launchd.\n'
       '\t\t * mockfs has one executable node, so resolve that path to the same\n'
       '\t\t * node instead of dying with ENOENT mid-exec. */\n'
       '\t\t} else if (!strncmp(cnp->cn_nameptr, "appleinternal", 14)) {\n'
       '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v380 lk appint"); }\n'
       '\t\t\ttarget_fsnode = fsnode;\n'
       '\t\t} else if (!strncmp(cnp->cn_nameptr, "launchd.development", 20)) {\n'
       '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v380 lk ldev"); }\n'
       '\t\t\tmockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);\n'
       '\t\t} else {\n')
n = src.count(old)
if n != 1:
    sys.exit("patch_v380: mockfs anchor count=%d (want 1)" % n)
src = src.replace(old, new, 1)
open(VNOPS, "w", encoding="utf-8").write(src)
print("patch_v380: mockfs resolves appleinternal + launchd.development")

# --- 2. sleh: re-arm the SP1 synchronous-exception probes -------------------
src = open(SLEH, encoding="utf-8", errors="replace").read()
old2 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
        '\t  static unsigned int v369_once;\n'
        '\t  if (!v369_once++) {\n'
        '\t    g0245d_tracev("v369 sp1 esr", (unsigned long long)esr);\n'
        '\t    g0245d_tracev("v369 sp1 far", (unsigned long long)(uintptr_t)far);\n'
        '\t    g0245d_tracev("v369 sp1 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state));\n'
        '\t  } }\n')
new2 = old2 + ('\t/* g0245d v380: the v369 probes above are once-only and were already\n'
               '\t * spent earlier in this boot, so the ENOENT unwind panic arrived with\n'
               '\t * no ESR at all.  Keep a small bounded budget instead. */\n'
               '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
               '\t  static unsigned int v380_sp1;\n'
               '\t  if (v380_sp1 < 6) {\n'
               '\t    v380_sp1++;\n'
               '\t    g0245d_tracev("v380 sp1 esr", (unsigned long long)esr);\n'
               '\t    g0245d_tracev("v380 sp1 far", (unsigned long long)(uintptr_t)far);\n'
               '\t    g0245d_tracev("v380 sp1 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state));\n'
               '\t    g0245d_tracev("v380 sp1 ec", (unsigned long long)((esr >> 26) & 0x3fu));\n'
               '\t  } }\n')
n = src.count(old2)
if n != 1:
    sys.exit("patch_v380: sleh anchor count=%d (want 1)" % n)
src = src.replace(old2, new2, 1)
open(SLEH, "w", encoding="utf-8").write(src)
print("patch_v380: SP1 exception probes re-armed (v380 sp1 esr/far/pc/ec)")
