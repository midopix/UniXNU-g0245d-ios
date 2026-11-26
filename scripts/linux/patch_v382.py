#!/usr/bin/env python3
"""g0245d v382 -- try /sbin/launchd first; the long DEVELOPMENT path overflows the
kernel stack.

v381 photo (2026-11-26 14:22) ring:

    8728 v319 lk sbin               (really "usr")
    8729 v299 fsv enter
    8730 v299 fsv lock ok
    8731 v299 fsv done 0
    8732 v380 lk appint             <-- v380's appleinternal branch DID match
    8733 v299 fsv enter             <-- and then nothing from mockfs_fsnode_vnode
    8735 v369 sp1 esr 0x96000145    ESR_EC=0x25 (data abort, same EL), DFSC=0x05
    8736 v380 sp1 esr 0x96000145    (translation fault, level 1), WnR=1 (write)
    ...
    panic: "Invalid kernel stack pointer (probable overflow)."

`sleh_invalid_stack()` (osfmk/arm64/sleh.c:2245) is the guard-page handler and
the "(probable overflow)" wording means the saved SP had fallen into the single
page just below `round_page(thread->machine.kstackptr) - KERNEL_STACK_SIZE`.
So this is a **kernel stack overflow**, not a mockfs logic bug: the four-component
path /usr/appleinternal/sbin/launchd.development (usr -> appleinternal -> sbin ->
launchd.development) pushed the exec/namei/vnop-lookup chain past the 16 KB stack
right inside mockfs_fsnode_vnode's `lck_mtx_lock`.

The two-component path /sbin/launchd worked fine (v376..v378 reached cs_blob).

ONE嫌疑点: the init candidate order.  Put "/sbin/launchd" first -- it is the only
executable mockfs can serve, and it is the short path.  The v380 mockfs branch for
appleinternal/launchd.development is removed again: with the short path first it is
unreachable, and leaving a stack-overflow trap in the tree invites a false trail.

Safety net: sleh_invalid_stack prints `v382 sp` and `v382 ktop` (bounded) so if a
stack overflow happens again we can see how far below the stack bottom we were.

CUMULATIVE + IDEMPOTENT over v381.  Touches bsd/kern/kern_exec.c,
bsd/miscfs/mockfs/mockfs_vnops.c and osfmk/arm64/sleh.c.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")

EXEC = os.path.join(W, "bsd/kern/kern_exec.c")
VNOPS = os.path.join(W, "bsd/miscfs/mockfs/mockfs_vnops.c")
SLEH = os.path.join(W, "osfmk/arm64/sleh.c")
for p in (EXEC, VNOPS, SLEH):
    if not os.path.isfile(p):
        sys.exit("required file not found: %s" % p)

# --- 1. init candidate order -------------------------------------------------
src = open(EXEC, encoding="utf-8", errors="replace").read()
old1 = ('static const char * init_programs[] = {\n'
        '#if DEBUG\n'
        '\t"/usr/appleinternal/sbin/launchd.debug",\n'
        '#endif\n'
        '#if DEVELOPMENT || DEBUG\n'
        '\t"/usr/appleinternal/sbin/launchd.development",\n'
        '#endif\n'
        '\t"/sbin/launchd",\n'
        '};\n')
new1 = ('static const char * init_programs[] = {\n'
        '\t/* g0245d v382: mockfs serves exactly one executable node and it is only\n'
        '\t * reachable as /sbin/launchd.  Trying the DEVELOPMENT-only candidates\n'
        '\t * first sends namei down a four-component path that overflows the 16 KB\n'
        '\t * kernel stack (sleh_invalid_stack, "probable overflow"). */\n'
        '\t"/sbin/launchd",\n'
        '#if DEBUG\n'
        '\t"/usr/appleinternal/sbin/launchd.debug",\n'
        '#endif\n'
        '#if DEVELOPMENT || DEBUG\n'
        '\t"/usr/appleinternal/sbin/launchd.development",\n'
        '#endif\n'
        '};\n')
if "g0245d v382" in src:
    print("patch_v382: init order already patched")
elif src.count(old1) == 1:
    src = src.replace(old1, new1, 1)
    open(EXEC, "w", encoding="utf-8").write(src)
    print("patch_v382: /sbin/launchd is now init_programs[0]")
else:
    sys.exit("patch_v382: init_programs anchor count=%d" % src.count(old1))

# --- 2. drop the v380 mockfs branches (unreachable + overflow trap) ----------
src = open(VNOPS, encoding="utf-8", errors="replace").read()
old2 = ('\t\t/* g0245d v380: DEVELOPMENT builds try\n'
        '\t\t * /usr/appleinternal/sbin/launchd.development before /sbin/launchd.\n'
        '\t\t * mockfs has one executable node, so resolve that path to the same\n'
        '\t\t * node instead of dying with ENOENT mid-exec. */\n'
        '\t\t} else if (!strncmp(cnp->cn_nameptr, "appleinternal", 14)) {\n'
        '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v380 lk appint"); }\n'
        '\t\t\ttarget_fsnode = fsnode;\n'
        '\t\t} else if (!strncmp(cnp->cn_nameptr, "launchd.development", 20)) {\n'
        '\t\t\t{ extern void g0245d_trace(const char *); g0245d_trace("v380 lk ldev"); }\n'
        '\t\t\tmockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);\n')
if "v380 lk appint" in src:
    if src.count(old2) != 1:
        sys.exit("patch_v382: v380 branch anchor count=%d" % src.count(old2))
    src = src.replace(old2, '', 1)
    open(VNOPS, "w", encoding="utf-8").write(src)
    print("patch_v382: v380 appleinternal/launchd.development branches removed")
else:
    print("patch_v382: v380 branches already absent")

# --- 3. stack-overflow diagnostics ------------------------------------------
src = open(SLEH, encoding="utf-8", errors="replace").read()
if "v382 sp" in src:
    print("patch_v382: stack diagnostics already present")
else:
    old3 = ('\tsp = get_saved_state_sp(&context->ss);\n'
            '\tkernel_stack_bottom = round_page(thread->machine.kstackptr) - KERNEL_STACK_SIZE;\n')
    new3 = old3 + ('\t/* g0245d v382: how far below the stack bottom did we land? */\n'
                   '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
                   '\t  static unsigned int v382_n;\n'
                   '\t  if (v382_n < 2) {\n'
                   '\t    v382_n++;\n'
                   '\t    g0245d_tracev("v382 sp", (unsigned long long)sp);\n'
                   '\t    g0245d_tracev("v382 ktop", (unsigned long long)kernel_stack_bottom);\n'
                   '\t  } }\n')
    if src.count(old3) != 1:
        sys.exit("patch_v382: sleh anchor count=%d" % src.count(old3))
    src = src.replace(old3, new3, 1)
    open(SLEH, "w", encoding="utf-8").write(src)
    print("patch_v382: sleh_invalid_stack prints v382 sp / v382 ktop")
