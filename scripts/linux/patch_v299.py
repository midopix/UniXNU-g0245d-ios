#!/usr/bin/env python3
"""g0245d v299 -- dissect the VFS_ROOT freeze and pre-empt the rootauth trap.

Evidence (v298 photo 16:19, clipboard-2026-11-23T08-19-58-626Z-85fcde07.jpg):
  v298's two perm-pool fixes worked -- mockfs vfs_mountroot() succeeded
  (`v294 bread ret 0`, `v293 mr ret ok`, then XNU-native
  `bsd_init_kprintf("calling VFS_ROOT")` at bsd_init.c:1062).
  Heartbeat froze at `hb 8527/8484 bsd calling VFS_ROOT`: alive, but the
  label never advanced past the VFS_ROOT() call at bsd_init.c:1064.
  => the new wall is inside VFS_ROOT() -> mockfs_root() ->
     mockfs_fsnode_vnode().  No panic => stuck in a lock / alloc, not the
     `cannot find root vnode` panic path.

v299 (diagnostic probes + one pre-emptive fix):
  1. bsd_init.c: probes immediately before and after VFS_ROOT().
     `v299 vr call` / `v299 vr ret ok` / `v299 vr ret err<e>`.
  2. mockfs_vfsops.c mockfs_root(): entry + return-with-errno probes.
     `v299 mroot enter` / `v299 mroot ret<r>`.
  3. mockfs_fsnode.c mockfs_fsnode_vnode(): entry, post-mutex,
     before/after vnode_create (the prime suspect: vnode_create -> zalloc,
     the same kernel_memory_allocate page-grab class that wedged in v291).
     `v299 fsv enter` / `v299 fsv lock ok` / `v299 fsv vcreate call` /
     `v299 fsv vcreate ret<r>` / `v299 fsv done<r>`.
  4. PRE-EMPTIVE FIX: mockfs has no seal; VNOP_IOCTL(FSIOC_KERNEL_ROOTAUTH)
     will fail and trigger `panic("rootvp not authenticated after mounting")`
     at bsd_init.c:1117 once VFS_ROOT returns.  Force require_rootauth=FALSE
     so we don't burn a whole build cycle just to hit that known trap.
     Probe `v299 rootauth skip` marks the bypass.

All probes are label-only (no behavior change) except (4).  Idempotent.
Run on the tree that already has v298 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v299.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

INIT = os.path.join(WORK, "bsd/kern/bsd_init.c")
VFSOP = os.path.join(WORK, "bsd/miscfs/mockfs/mockfs_vfsops.c")
FSNODE = os.path.join(WORK, "bsd/miscfs/mockfs/mockfs_fsnode.c")
MARK = "g0245d v299"


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


# ---- bsd_init.c : VFS_ROOT probes + rootauth bypass ------------------------
s = read(INIT)
if MARK in s:
    print("bsd_init.c: already v299")
else:
    s = sub(
        s,
        """	bsd_init_kprintf("calling VFS_ROOT\\n");
	/* Get the vnode for '/'.  Set fdp->fd_fd.fd_cdir to reference it. */
	if (VFS_ROOT(mountlist.tqh_first, &init_rootvnode, vfs_context_kernel())) {
		panic("bsd_init: cannot find root vnode: %s", PE_boot_args());
	}""",
        """	bsd_init_kprintf("calling VFS_ROOT\\n");
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v299 vr call"); }
	/* Get the vnode for '/'.  Set fdp->fd_fd.fd_cdir to reference it. */
	{ int g0245d_v299_vrerr;
	  g0245d_v299_vrerr = VFS_ROOT(mountlist.tqh_first, &init_rootvnode, vfs_context_kernel());
	  { extern void g0245d_trace(const char *);
	    if (!g0245d_v299_vrerr) {
	      g0245d_trace("v299 vr ret ok");
	    } else {
	      extern void g0245d_trace_u(const char *, unsigned int);
	      g0245d_trace_u("v299 vr ret e", (unsigned int)g0245d_v299_vrerr);
	    } }
	  if (g0245d_v299_vrerr) {
		panic("bsd_init: cannot find root vnode: %s", PE_boot_args());
	  }
	}""",
        "v299: VFS_ROOT probes",
    )
    s = sub(
        s,
        """		require_rootauth = TRUE;
#endif // XNU_TARGET_OS_OSX && defined(__arm64__)""",
        """		require_rootauth = FALSE;  /* g0245d v299: mockfs has no seal */
#endif // XNU_TARGET_OS_OSX && defined(__arm64__)""",
        "v299: force require_rootauth FALSE",
    )
    s = sub(
        s,
        """		if (require_rootauth) {
			/* enforce sealedness */""",
        """		if (require_rootauth) {
			/* enforce sealedness */
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v299 rootauth Engaged"); }""",
        "v299: rootauth-engaged marker",
    )
    s = sub(
        s,
        """			if (autherr && !owner_authorized) {
				panic("rootvp not authenticated after mounting");
			}""",
        """			if (autherr && !owner_authorized) {
				{ extern void g0245d_trace_u(const char *, unsigned int);
				  g0245d_trace_u("v299 auth fail e", (unsigned int)autherr); }
				panic("rootvp not authenticated after mounting");
			}""",
        "v299: rootauth errno marker before panic",
    )
    write(INIT, s)
    print("bsd_init.c: v299 VFS_ROOT probes + rootauth bypass installed")

# ---- mockfs_vfsops.c : mockfs_root probes ----------------------------------
s = read(VFSOP)
if MARK in s:
    print("mockfs_vfsops.c: already v299")
else:
    s = sub(
        s,
        """	int rvalue;

	rvalue = mockfs_fsnode_vnode(((mockfs_mount_t) mp->mnt_data)->mockfs_root, vpp);
	return rvalue;
}""",
        """	int rvalue;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v299 mroot enter"); }

	rvalue = mockfs_fsnode_vnode(((mockfs_mount_t) mp->mnt_data)->mockfs_root, vpp);
	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v299 mroot ret", (unsigned int)rvalue); }
	return rvalue;
}""",
        "v299: mockfs_root probes",
    )
    write(VFSOP, s)
    print("mockfs_vfsops.c: v299 mockfs_root probes installed")

# ---- mockfs_fsnode.c : mockfs_fsnode_vnode probes --------------------------
s = read(FSNODE)
if MARK in s:
    print("mockfs_fsnode.c: already v299")
else:
    s = sub(
        s,
        """	int rvalue;
	memory_object_control_t ubc_mem_object;
	mockfs_mount_t mockfs_mnt;
	struct vnode_fsparam vnfs_param;

	if ((!fsnp) || (!vpp)) {""",
        """	int rvalue;
	memory_object_control_t ubc_mem_object;
	mockfs_mount_t mockfs_mnt;
	struct vnode_fsparam vnfs_param;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v299 fsv enter"); }

	if ((!fsnp) || (!vpp)) {""",
        "v299: mockfs_fsnode_vnode entry probe",
    )
    s = sub(
        s,
        """	mockfs_mnt = ((mockfs_mount_t) fsnp->mnt->mnt_data);
	lck_mtx_lock(&mockfs_mnt->mockfs_mnt_mtx);

	if (fsnp->vp) {""",
        """	mockfs_mnt = ((mockfs_mount_t) fsnp->mnt->mnt_data);
	lck_mtx_lock(&mockfs_mnt->mockfs_mnt_mtx);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v299 fsv lock ok"); }

	if (fsnp->vp) {""",
        "v299: post-mutex probe",
    )
    s = sub(
        s,
        """		vnfs_param.vnfs_flags = VNFS_CANTCACHE | VNFS_NOCACHE;
		rvalue = vnode_create(VNCREATE_FLAVOR, VCREATESIZE, &vnfs_param, &fsnp->vp);""",
        """		vnfs_param.vnfs_flags = VNFS_CANTCACHE | VNFS_NOCACHE;
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v299 fsv vcreate call"); }
		rvalue = vnode_create(VNCREATE_FLAVOR, VCREATESIZE, &vnfs_param, &fsnp->vp);
		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v299 fsv vcreate ret", (unsigned int)rvalue); }""",
        "v299: vnode_create probes",
    )
    s = sub(
        s,
        """	lck_mtx_unlock(&mockfs_mnt->mockfs_mnt_mtx);

done:
	return rvalue;
}""",
        """	lck_mtx_unlock(&mockfs_mnt->mockfs_mnt_mtx);
	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v299 fsv done", (unsigned int)rvalue); }

done:
	return rvalue;
}""",
        "v299: fsnode done probe",
    )
    write(FSNODE, s)
    print("mockfs_fsnode.c: v299 fsnode probes installed")

print("v299 patch complete")
