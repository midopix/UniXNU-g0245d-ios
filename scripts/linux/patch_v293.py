#!/usr/bin/env python3
"""g0245d v293 -- probe the whole vfs_mountroot() path (pure probes, no behavior).

Evidence (v292 photo, 2026-11-23 10:53): seq 8479-8481 show
`v292 perm pool` / `v289 memdisk 16777216` / `v289 rd= md0` and the heartbeat
line reads `hb 8482/8439 bsd vfs_mountroot`.  So for the first time:
  - permanent-pool 8 KB allocation succeeded (v291's sleeping
    kernel_memory_allocate() is cured),
  - the 16 MB memory disk was built and rd=md0 was set,
  - bsd_init() reached the "Mount the root file system" stage and the
    heartbeat label is bsd_init_kprintf("vfs_mountroot") at bsd_init.c:1016.
No `launchd`, no panic(42): the machine is stuck at/inside vfs_mountroot().

v293 adds pure g0245d_trace probes over the whole mountroot ladder:
  bsd_init.c          : v293 mr call / v293 mr ret ok / v293 mr ret err
  vfs_subr.c          : v293 mr enter / v293 netboot mr
                        v293 bdevvp done / v293 bdevvp FAIL
                        v293 fs loop / v293 alloc done
                        v293 mount call / v293 mount ret (errno)
                        v293 mounted
Nothing else changes.

Idempotent.  Run AFTER patch_v292.py:
    XNU_WORK=<xnu-work> python3 patch_v293.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "bsd/kern/bsd_init.c")
VFSSUBR = os.path.join(WORK, "bsd/vfs/vfs_subr.c")
MARK = "g0245d v293"


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


# ---- bsd/kern/bsd_init.c: wrap the vfs_mountroot() call --------------------
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """		bsd_init_kprintf("vfs_mountroot\\n");
		boot_progress_stage("vfs_mountroot enter");
		if (0 == (err = vfs_mountroot())) {
			boot_progress_stage("vfs_mountroot mounted; authentication pending");
			break;
		}
		rootdevice[0] = '\\0';""",
        """		bsd_init_kprintf("vfs_mountroot\\n");
		boot_progress_stage("vfs_mountroot enter");
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 mr call"); }
		if (0 == (err = vfs_mountroot())) {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v293 mr ret ok"); }
			boot_progress_stage("vfs_mountroot mounted; authentication pending");
			break;
		}
		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v293 mr ret err", (unsigned int)err); }
		rootdevice[0] = '\\0';""",
        "v293: bsd_init vfs_mountroot call site",
    )
    write(BSDINIT, s)
    print("bsd_init.c: v293 call-site probes installed")
else:
    print("bsd_init.c: already v293")

# ---- bsd/vfs/vfs_subr.c: probes inside vfs_mountroot() ---------------------
s = read(VFSSUBR)
if MARK not in s:
    # 1. function entry
    s = sub(
        s,
        """	KDBG_RELEASE(DBG_MOUNTROOT | DBG_FUNC_START);
	if (mountroot != NULL) {""",
        """	KDBG_RELEASE(DBG_MOUNTROOT | DBG_FUNC_START);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v293 mr enter"); }
	if (mountroot != NULL) {""",
        "v293: vfs_mountroot entry",
    )
    # 2. netboot path
    s = sub(
        s,
        """		 */
		error = (*mountroot)();""",
        """		 */
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 netboot mr"); }
		error = (*mountroot)();""",
        "v293: netboot path",
    )
    # 3. bdevvp failure
    s = sub(
        s,
        """	if ((error = bdevvp(rootdev, &rootvp))) {
		printf("vfs_mountroot: can't setup bdevvp\\n");""",
        """	if ((error = bdevvp(rootdev, &rootvp))) {
		printf("vfs_mountroot: can't setup bdevvp\\n");
		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v293 bdevvp FAIL", (unsigned int)error); }""",
        "v293: bdevvp failure",
    )
    # 4. bdevvp success
    s = sub(
        s,
        """	bdevvp_rootvp = rootvp;""",
        """	bdevvp_rootvp = rootvp;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v293 bdevvp done"); }""",
        "v293: bdevvp success",
    )
    # 5. fs loop + rootmountalloc
    s = sub(
        s,
        """		mp = vfs_rootmountalloc_internal(vfsp, "root_device");
		mp->mnt_devvp = rootvp;""",
        """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 fs loop"); }
		mp = vfs_rootmountalloc_internal(vfsp, "root_device");
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 alloc done"); }
		mp->mnt_devvp = rootvp;""",
        "v293: fs loop / alloc",
    )
    # 6. mount call / return
    s = sub(
        s,
        """		if (vfsp->vfc_mountroot) {
			error = (*vfsp->vfc_mountroot)(mp, rootvp, ctx);
		} else {
			error = VFS_MOUNT(mp, rootvp, 0, ctx);
		}""",
        """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 mount call"); }
		if (vfsp->vfc_mountroot) {
			error = (*vfsp->vfc_mountroot)(mp, rootvp, ctx);
		} else {
			error = VFS_MOUNT(mp, rootvp, 0, ctx);
		}
		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v293 mount ret", (unsigned int)error); }""",
        "v293: mount call/ret",
    )
    # 7. mounted
    s = sub(
        s,
        """		if (!error) {
			if (bdevvp_rootvp != rootvp) {""",
        """		if (!error) {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v293 mounted"); }
			if (bdevvp_rootvp != rootvp) {""",
        "v293: mounted",
    )
    write(VFSSUBR, s)
    print("vfs_subr.c: v293 mountroot probes installed")
else:
    print("vfs_subr.c: already v293")

print("v293 done (pure probes; no behavior change)")
