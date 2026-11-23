#!/usr/bin/env python3
"""g0245d v294 -- probe mockfs_mountroot() end to end (pure probes, no behavior).

Evidence (v293 photo, 2026-11-23 11:13): seq 8483-8486 show
`v293 mr call` / `v293 mr enter` / `v293 bdevvp done` / `v293 fs loop`, and the
heartbeat reads `hb 8486/8445 v293 mount call`.  No `v293 mount ret`.
So: bdevvp passed on the first try, the vfsconf loop entered (the FS tried is
mockfs -- vfs_conf.c:205 `.vfc_mountroot = mockfs_mountroot`), and
vfs_rootmountalloc_internal() did NOT sleep (mount call is a newer label than
alloc done).  The machine is stuck between `mount call` and `mount ret`,
i.e. inside mockfs_mountroot() (bsd/miscfs/mockfs/mockfs_vfsops.c:76).

Suspects in execution order (verified against source):
  1. kalloc_type(struct mockfs_mount, Z_WAITOK|Z_ZERO)      (v257-style wall)
  2. mockfs_fsnode_create() x3 -> kalloc_type(Z_WAITOK|Z_NOFAIL) (fsnode.c:89)
  3. VNOP_IOCTL(DKIOCGETMEMDEVINFO)                          (low probability)
  4. buf_meta_bread(rvp, 0, 4096, ...)  -- synchronous block read on md0;
     waits for VNOP_STRATEGY/biodone completion.  If the memdev I/O
     completion chain is incomplete this sleeps forever.  Top suspect.
  5. mockfs_fsnode_adopt() x2-3                              (low probability)

v294 adds probes at each step (plus a first-line probe inside the ioctl
success branch).  Nothing else changes.

Idempotent.  Run AFTER patch_v293.py:
    XNU_WORK=<xnu-work> python3 patch_v294.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

VFSOPS = os.path.join(WORK, "bsd/miscfs/mockfs/mockfs_vfsops.c")
VFSSUBR = os.path.join(WORK, "bsd/vfs/vfs_subr.c")
MARK = "g0245d v294"


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


# ---- bsd/miscfs/mockfs/mockfs_vfsops.c: mockfs_mountroot ladder ------------
s = read(VFSOPS)
if MARK not in s:
    # 1. entry + kalloc_type(mockfs_mount)
    s = sub(
        s,
        """	mockfs_mount_data = kalloc_type(struct mockfs_mount, Z_WAITOK | Z_ZERO);
	mockfs_fsnode_create(mp, MOCKFS_ROOT, &root_fsnode);""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 mmr enter"); }
	mockfs_mount_data = kalloc_type(struct mockfs_mount, Z_WAITOK | Z_ZERO);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 kalloc done"); }
	mockfs_fsnode_create(mp, MOCKFS_ROOT, &root_fsnode);""",
        "v294: entry + kalloc_type",
    )
    # 2. nodes created
    s = sub(
        s,
        """	if (!root_fsnode || !dev_fsnode || !file_fsnode) {""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 nodes done"); }
	if (!root_fsnode || !dev_fsnode || !file_fsnode) {""",
        "v294: nodes done",
    )
    # 3. ioctl call / ioctl ok
    s = sub(
        s,
        """	if (!VNOP_IOCTL(rvp, DKIOCGETMEMDEVINFO, (caddr_t)&memdev_info, 0, NULL)) {""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 ioctl call"); }
	if (!VNOP_IOCTL(rvp, DKIOCGETMEMDEVINFO, (caddr_t)&memdev_info, 0, NULL)) {
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v294 ioctl ok"); }""",
        "v294: ioctl call/ok",
    )
    # 4. buf_meta_bread call / ret
    s = sub(
        s,
        """	rvalue = buf_meta_bread(rvp, 0, 4096, vfs_context_ucred(ctx), &header_buf);
	if (!rvalue) {""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 bread call"); }
	rvalue = buf_meta_bread(rvp, 0, 4096, vfs_context_ucred(ctx), &header_buf);
	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v294 bread ret", (unsigned int)rvalue); }
	if (!rvalue) {""",
        "v294: bread call/ret",
    )
    # 5. test-image branch
    s = sub(
        s,
        """		rvalue = mockfs_fsnode_create(mp, MOCKFS_TEST_FILE, &test_fsnode);""",
        """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v294 testimg"); }
		rvalue = mockfs_fsnode_create(mp, MOCKFS_TEST_FILE, &test_fsnode);""",
        "v294: testimg branch",
    )
    # 6. adopt call
    s = sub(
        s,
        """	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, dev_fsnode))) {""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 adopt call"); }
	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, dev_fsnode))) {""",
        "v294: adopt call",
    )
    # 7. success tail
    s = sub(
        s,
        """	mockfs_mount_data->mockfs_root = root_fsnode;""",
        """	mockfs_mount_data->mockfs_root = root_fsnode;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v294 mmr done"); }""",
        "v294: mmr done",
    )
    write(VFSOPS, s)
    print("mockfs_vfsops.c: v294 mountroot ladder installed")
else:
    print("mockfs_vfsops.c: already v294")

# ---- bsd/vfs/vfs_subr.c: split the v293 mount call into two paths ----------
s = read(VFSSUBR)
if MARK not in s:
    s = sub(
        s,
        """		if (vfsp->vfc_mountroot) {
			error = (*vfsp->vfc_mountroot)(mp, rootvp, ctx);
		} else {
			error = VFS_MOUNT(mp, rootvp, 0, ctx);
		}""",
        """		if (vfsp->vfc_mountroot) {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v294 mrt path"); }
			error = (*vfsp->vfc_mountroot)(mp, rootvp, ctx);
		} else {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v294 vfsmnt path"); }
			error = VFS_MOUNT(mp, rootvp, 0, ctx);
		}""",
        "v294: split mount call paths",
    )
    write(VFSSUBR, s)
    print("vfs_subr.c: v294 path split probes installed")
else:
    print("vfs_subr.c: already v294")

print("v294 done (pure probes; no behavior change)")
