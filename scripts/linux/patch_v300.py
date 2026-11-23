#!/usr/bin/env python3
"""g0245d v300 -- dissect the devfs_kernel_mount freeze.

Evidence (v299 photo 16:32:50, clipboard-2026-11-23T08-33-39-772Z-72c73c42.jpg):
  VFS_ROOT succeeded (`v299 vr ret ok` @8537), devfs_kernel_mount entered
  (@8538 `bsd calling devfs_kernel_mount`), a SECOND mockfs_fsnode_vnode ran
  (@8539-8543 fsv enter/lock ok/vcreate call/ret 0/done), then the heartbeat
  froze at `hb 8543/8500 v299 fsv done`.  No `bsd calling siginit` trace
  (bsd_init.c:1238) => stuck inside devfs_kernel_mount's kernel_mount()
  return path, between the namei-triggered fsnode and siginit.
  CONFIG_BASESYSTEMROOT = 0 (no BaseSystem string in kernel), so that block
  is compiled out -- devfs goes straight to siginit.

v300 (label-only diagnostic probes, no behavior change):
  1. devfs_vfsops.c devfs_kernel_mount(): entry, before/after kernel_mount().
     `v300 dkm enter` / `v300 dkm km call` / `v300 dkm km ret<r>`.
  2. vfs_syscalls.c kernel_mount(): namei before/after, mount_common
     before/after, after cleanup.  This splits the exact wall:
     `v300 km enter` / `v300 km namei call` / `v300 km namei ret<r>` /
     `v300 km mc call` / `v300 km mc ret<r>` / `v300 km done<r>`.
  3. bsd_init.c: after the DEVFS block, around siginit, around
     bsd_utaskbootstrap (cloneproc -> zalloc, the next likely wall):
     `v300 post devfs` / `v300 siginit call` / `v300 siginit done` /
     `v300 ubt call` / `v300 ubt done`.

Idempotent.  Run on the tree that already has v299 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v300.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

INIT = os.path.join(WORK, "bsd/kern/bsd_init.c")
VFSOP = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
SYSCALL = os.path.join(WORK, "bsd/vfs/vfs_syscalls.c")
MARK = "g0245d v300"


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


TRACE = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'
TRACEU = ('{ extern void g0245d_trace_u(const char *, unsigned int); '
          'g0245d_trace_u("%s", (unsigned int)(%s)); }')


# ---- devfs_vfsops.c : devfs_kernel_mount probes ---------------------------
s = read(VFSOP)
if MARK in s:
    print("devfs_vfsops.c: already v300")
else:
    s = sub(
        s,
        """	int error;
	vfs_context_t ctx = vfs_context_kernel();
	char fsname[] = "devfs";

	error = kernel_mount(fsname, NULLVP, NULLVP, mntname, NULL, 0, MNT_DONTBROWSE, KERNEL_MOUNT_NOAUTH | KERNEL_MOUNT_DEVFS, ctx);
	if (error) {""",
        """	int error;
	vfs_context_t ctx = vfs_context_kernel();
	char fsname[] = "devfs";
	""" + TRACE % "v300 dkm enter" + """

	""" + TRACE % "v300 dkm km call" + """
	error = kernel_mount(fsname, NULLVP, NULLVP, mntname, NULL, 0, MNT_DONTBROWSE, KERNEL_MOUNT_NOAUTH | KERNEL_MOUNT_DEVFS, ctx);
	""" + TRACEU % ("v300 dkm km ret", "error") + """
	if (error) {""",
        "v300: devfs_kernel_mount probes",
    )
    write(VFSOP, s)
    print("devfs_vfsops.c: v300 devfs_kernel_mount probes installed")

# ---- vfs_syscalls.c : kernel_mount probes ---------------------------------
s = read(SYSCALL)
if MARK in s:
    print("vfs_syscalls.c: already v300")
else:
    # entry
    s = sub(
        s,
        """	struct nameidata nd;
	boolean_t did_namei;
	int error;

	NDINIT(&nd, LOOKUP, OP_MOUNT, FOLLOW | AUDITVNPATH1 | WANTPARENT,
	    UIO_SYSSPACE, CAST_USER_ADDR_T(path), ctx);""",
        """	struct nameidata nd;
	boolean_t did_namei;
	int error;
	""" + TRACE % "v300 km enter" + """

	NDINIT(&nd, LOOKUP, OP_MOUNT, FOLLOW | AUDITVNPATH1 | WANTPARENT,
	    UIO_SYSSPACE, CAST_USER_ADDR_T(path), ctx);""",
        "v300: kernel_mount entry",
    )
    # namei call (anchored by the `if (vp == NULLVP)` immediately before it)
    s = sub(
        s,
        """	if (vp == NULLVP) {
		error = namei(&nd);
		if (error) {""",
        """	if (vp == NULLVP) {
		""" + TRACE % "v300 km namei call" + """
		error = namei(&nd);
		""" + TRACEU % ("v300 km namei ret", "error") + """
		if (error) {""",
        "v300: kernel_mount namei probes",
    )
    # mount_common call
    s = sub(
        s,
        """	kern_flags |= KERNEL_MOUNT_KMOUNT;
	error = mount_common(fstype, pvp, vp, &nd.ni_cnd, CAST_USER_ADDR_T(data),
	    syscall_flags, kern_flags, NULL, ctx);

	if (did_namei) {""",
        """	kern_flags |= KERNEL_MOUNT_KMOUNT;
	""" + TRACE % "v300 km mc call" + """
	error = mount_common(fstype, pvp, vp, &nd.ni_cnd, CAST_USER_ADDR_T(data),
	    syscall_flags, kern_flags, NULL, ctx);
	""" + TRACEU % ("v300 km mc ret", "error") + """

	if (did_namei) {""",
        "v300: kernel_mount mount_common probes",
    )
    # after cleanup, before return
    s = sub(
        s,
        """	if (did_namei) {
		vnode_put(vp);
		vnode_put(pvp);
		nameidone(&nd);
	}

	return error;
}""",
        """	if (did_namei) {
		vnode_put(vp);
		vnode_put(pvp);
		nameidone(&nd);
	}
	""" + TRACEU % ("v300 km done", "error") + """

	return error;
}""",
        "v300: kernel_mount done probe",
    )
    write(SYSCALL, s)
    print("vfs_syscalls.c: v300 kernel_mount probes installed")

# ---- bsd_init.c : post-devfs / siginit / utaskbootstrap probes ------------
s = read(INIT)
if MARK in s:
    print("bsd_init.c: already v300")
else:
    # after devfs_kernel_mount block (anchor the closing brace + CONFIG_BASESYSTEMROOT)
    s = sub(
        s,
        """		bsd_init_kprintf("calling devfs_kernel_mount\\n");
		devfs_kernel_mount(mounthere);
	}
#endif /* DEVFS */""",
        """		bsd_init_kprintf("calling devfs_kernel_mount\\n");
		devfs_kernel_mount(mounthere);
		""" + TRACE % "v300 post devfs" + """
	}
#endif /* DEVFS */""",
        "v300: post-devfs probe",
    )
    # around siginit
    s = sub(
        s,
        """	/* Initialize signal state for process 0. */
	bsd_init_kprintf("calling siginit\\n");
	siginit(kernproc);

	bsd_init_kprintf("calling bsd_utaskbootstrap\\n");
	bsd_utaskbootstrap();""",
        """	/* Initialize signal state for process 0. */
	""" + TRACE % "v300 siginit call" + """
	bsd_init_kprintf("calling siginit\\n");
	siginit(kernproc);
	""" + TRACE % "v300 siginit done" + """

	""" + TRACE % "v300 ubt call" + """
	bsd_init_kprintf("calling bsd_utaskbootstrap\\n");
	bsd_utaskbootstrap();
	""" + TRACE % "v300 ubt done" + """ """,
        "v300: siginit/utaskbootstrap probes",
    )
    write(INIT, s)
    print("bsd_init.c: v300 post-devfs/siginit/utaskbootstrap probes installed")

print("v300 patch complete")
