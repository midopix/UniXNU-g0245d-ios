#!/usr/bin/env python3
"""g0245d v309 -- bypass VM_KERNEL_ADDRHASH in devfs_mount (salt==0 assert).

v308 verdict (photo 09:01): heartbeat `hb307 8569/8526 v308 mnt_data ok`.
8569/8526 = 8567/8524 + 2, exactly the two new probes that passed.  Freeze is
the statement right after `mp->mnt_data = devfs_mp_p`:

    mp->mnt_vfsstat.f_fsid.val[0] = (int32_t)VM_KERNEL_ADDRHASH(devfs_mp_p);

VM_KERNEL_ADDRHASH is NOT an integer macro: vm_param.h:377 defines it as
vm_kernel_addrhash(), and vm_kern.c:4024 vm_kernel_addrhash_internal() starts
with `assert(salt != 0)`, then runs SHA-256.  The salts are only set in
kernel_bootstrap_thread() (startup.c:725) from early_random(); on this
BootShim path early_random() can return 0, and `assert(salt != 0)` then dies
before any panic text reaches the framebuffer -- which is exactly the
"silent" freeze.

v309:
  1. print the actual salt (low 32 bits) so the hypothesis is measurable;
  2. use the raw pointer as f_fsid.val[0] instead of the hash.  fsid is only
     an opaque token, so the raw address is functionally fine, and this also
     unblocks every later VM_KERNEL_ADDRHASH call if they share the salt.
Idempotent.  Run on the tree that already has v308 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v309.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/miscfs/devfs/devfs_vfsops.c")
MARK = "v309 salt"


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


s = read(F)
if MARK in s:
    print("devfs_vfsops.c: already v309")
else:
    old = (
        '\tmp->mnt_vfsstat.f_fsid.val[0] = (int32_t)VM_KERNEL_ADDRHASH(devfs_mp_p);\n'
        '\t{ extern void g0245d_trace(const char *); g0245d_trace("v308 hash ok"); }\n'
    )
    new = (
        '\t{ extern uint64_t vm_kernel_addrhash_salt; extern void g0245d_trace_u(const char *, unsigned int);\n'
        '\t  g0245d_trace_u("v309 salt", (unsigned int)vm_kernel_addrhash_salt); }\n'
        '\t/* g0245d v309: was VM_KERNEL_ADDRHASH(devfs_mp_p), whose assert(salt != 0) kills us */\n'
        '\tmp->mnt_vfsstat.f_fsid.val[0] = (int32_t)(uintptr_t)devfs_mp_p;\n'
        '\t{ extern void g0245d_trace(const char *); g0245d_trace("v308 hash ok"); }\n'
    )
    s = sub(s, old, new, "v309: bypass addrhash")
    write(F, s)
    print("devfs_vfsops.c: v309 salt probe + hash bypass installed")

print("v309 patch complete")
