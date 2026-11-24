#!/usr/bin/env python3
"""g0245d v311 -- make vm_kernel_addrhash_internal SHA-256-free.

v310 verdict (photo 09:10): heartbeat `hb307 8583/8540 v310 statfs call` and
the ring shows `8579 v304 dm dup ret 0` (dev_dup_plane succeeded), then
unlock ok / err 0 / bzero ok -- freeze is inside devfs_statfs(), whose line 328
calls VM_KERNEL_ADDRHASH again.

That confirms the root cause is not salt and not the caller: the SHA-256
implementation used by this build traps on this BootShim path (ARMv8 crypto /
FP-SIMD not enabled yet, and the synchronous-exception handler is not ready),
so ANY VM_KERNEL_ADDRHASH call is fatal early in boot.  bsd/ contains 10 call
sites (f_fsid, st_ino, pipe handles, vsock, devfs_vnops, routefs), so patching
call sites one by one is not viable.

v311 replaces the SHA-256 block inside vm_kernel_addrhash_internal() with a
cheap 64-bit integer mix.  Callers only need an opaque, address-dependent
token, so behaviour is preserved without touching any of the 10 call sites.
It also adds enter/ret probes around devfs_statfs() so the next photo can
prove the whole devfs_mount path completes.

Idempotent.  Run on the tree that already has v310 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v311.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

VM_KERN = os.path.join(WORK, "osfmk/vm/vm_kern.c")
DEVFS = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "g0245d v311"


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


s = read(VM_KERN)
if MARK in s:
    print("vm_kern.c: already v311")
else:
    old = """	vm_offset_t sha_digest[SHA256_DIGEST_LENGTH / sizeof(vm_offset_t)];
	SHA256_CTX sha_ctx;

	SHA256_Init(&sha_ctx);
	SHA256_Update(&sha_ctx, &salt, sizeof(salt));
	SHA256_Update(&sha_ctx, &addr, sizeof(addr));
	SHA256_Final(sha_digest, &sha_ctx);

	return sha_digest[0];"""
    new = """	/* g0245d v311: SHA-256 traps on this BootShim path while FP/SIMD is
	 * still disabled (and the sync-exception handler is not ready), and
	 * bsd/ calls VM_KERNEL_ADDRHASH in 10 places.  Callers only need an
	 * opaque address-dependent token, so mix with plain integer ops. */
	uint64_t h = (uint64_t)addr ^ (salt * 0x9E3779B97F4A7C15ull);
	h ^= h >> 33;
	h *= 0xff51afd7ed558ccdull;
	h ^= h >> 33;
	h *= 0xc4ceb9fe1a85ec53ull;
	h ^= h >> 33;

	return (vm_offset_t)h;"""
    s = sub(s, old, new, "v311: sha256 -> integer mix")
    write(VM_KERN, s)
    print("vm_kern.c: v311 integer-mix hash installed")

s = read(DEVFS)
if "v311 statfs enter" in s:
    print("devfs_vfsops.c: already v311")
else:
    s = sub(
        s,
        "devfs_statfs( struct mount *mp, struct vfsstatfs *sbp, __unused vfs_context_t ctx)\n{\n\tstruct devfsmount *devfs_mp_p = (struct devfsmount *)mp->mnt_data;",
        "devfs_statfs( struct mount *mp, struct vfsstatfs *sbp, __unused vfs_context_t ctx)\n{\n\tstruct devfsmount *devfs_mp_p = (struct devfsmount *)mp->mnt_data;\n\t{ extern void g0245d_trace(const char *); g0245d_trace(\"v311 statfs enter\"); }",
        "v311: statfs enter probe",
    )
    s = sub(
        s,
        "\tsbp->f_fsid.val[1] = vfs_typenum(mp);\n\n\treturn 0;",
        "\tsbp->f_fsid.val[1] = vfs_typenum(mp);\n\n\t{ extern void g0245d_trace(const char *); g0245d_trace(\"v311 statfs ret\"); }\n\treturn 0;",
        "v311: statfs ret probe",
    )
    write(DEVFS, s)
    print("devfs_vfsops.c: v311 statfs probes installed")

print("v311 patch complete")
