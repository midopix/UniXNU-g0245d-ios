#!/usr/bin/env python3
"""g0245d v319 -- trace mockfs lookup branches and the init_programs loop index.

v318 verdict (photo 09:54):
    8633 v318 execve ret 2     <- ENOENT: /usr/appleinternal/sbin/launchd.debug
    8634 v318 execve call      <- second attempt
    8640 v299 fsv enter        <- ... /usr/appleinternal/sbin/launchd.development
    heartbeat: v299 fsv enter

So exec IS running and walking init_programs[]:
    [0] /usr/appleinternal/sbin/launchd.debug        -> ENOENT (expected)
    [1] /usr/appleinternal/sbin/launchd.development  -> ENOENT (expected)
    [2] /sbin/launchd                                -> must succeed
mockfs_lookup() maps "sbin"/"usr"/"lib" to the root node and "launchd" to the
MOCKFS_FILE node, so [2] should resolve -- unless a branch or the ISLASTCN
condition misbehaves.

v319:
  * prints the loop index (`v319 try <i>`);
  * prints which mockfs_lookup branch each component takes
    (v319 lk sbin / lk usr / lk dev / lk dyld / lk probe / lk launchd / lk enoent),
    so the exact component that fails becomes visible.
Idempotent.  Run on the tree that already has v318 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v319.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

MOCK = os.path.join(WORK, "bsd/miscfs/mockfs/mockfs_vnops.c")
EXEC = os.path.join(WORK, "bsd/kern/kern_exec.c")
MARK = "v319 lk sbin"


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


T = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'
TU = '{ extern void g0245d_trace_u(const char *, unsigned int); g0245d_trace_u("%s", (unsigned int)(%s)); }'

s = read(MOCK)
if MARK in s:
    print("mockfs_vnops.c: already v319")
else:
    s = sub(
        s,
        """		if (!strncmp(cnp->cn_nameptr, "sbin", 5) ||
		    !strncmp(cnp->cn_nameptr, "usr", 4) || !strncmp(cnp->cn_nameptr, "lib", 4)) {
			target_fsnode = fsnode;
		} else if (!strncmp(cnp->cn_nameptr, "dev", 4)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_DEV, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "dyld", 5)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_TEST_FILE, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "probe.bin", 10)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_TEST_FILE, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "launchd", 8)) {
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);
		} else {
			rvalue = ENOENT;
		}""",
        """		if (!strncmp(cnp->cn_nameptr, "sbin", 5) ||
		    !strncmp(cnp->cn_nameptr, "usr", 4) || !strncmp(cnp->cn_nameptr, "lib", 4)) {
			""" + (T % "v319 lk sbin") + """
			target_fsnode = fsnode;
		} else if (!strncmp(cnp->cn_nameptr, "dev", 4)) {
			""" + (T % "v319 lk dev") + """
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_DEV, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "dyld", 5)) {
			""" + (T % "v319 lk dyld") + """
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_TEST_FILE, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "probe.bin", 10)) {
			""" + (T % "v319 lk probe") + """
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_TEST_FILE, &target_fsnode);
		} else if (!strncmp(cnp->cn_nameptr, "launchd", 8)) {
			""" + (T % "v319 lk launchd") + """
			mockfs_fsnode_child_by_type(fsnode, MOCKFS_FILE, &target_fsnode);
		} else {
			""" + (T % "v319 lk enoent") + """
			rvalue = ENOENT;
		}""",
        "v319: lookup branch probes",
    )
    write(MOCK, s)
    print("mockfs_vnops.c: v319 lookup branch probes installed")

s = read(EXEC)
if "v319 try" in s:
    print("kern_exec.c: already v319")
else:
    s = sub(
        s,
        '\t\tprintf("load_init_program: attempting to load %s\\n", init_programs[i]);\n',
        "\t\t" + (TU % ("v319 try", "i"))
        + '\n\t\tprintf("load_init_program: attempting to load %s\\n", init_programs[i]);\n',
        "v319: loop index",
    )
    write(EXEC, s)
    print("kern_exec.c: v319 loop index probe installed")

print("v319 patch complete")
