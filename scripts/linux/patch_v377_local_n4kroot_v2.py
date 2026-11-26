#!/usr/bin/env python3
"""g0245d v377 -- teach mockfs to parse N4KROOT v2 (N named files).

N4KROOT v1 only had two fixed slots.  v2 carries a path table so the root
can serve arbitrary paths (/sbin/launchd, /usr/lib/dyld, ...).  This patch:

  * mockfs_fsnode.h : add fsnode->name[] and fsnode->next_sibling
  * mockfs.h        : add mount->v2_files chain + v2_count
  * mockfs_vfsops.c : parse v2 header/table, build VREG nodes into a private
                      chain (v1 child_a/b/c layout untouched)
  * mockfs_vnops.c  : in v2 mode, resolve names against the v2 chain
  * mockfs_unmount  : release the v2 chain

Additive + idempotent; v1 / synthetic-root behaviour is preserved because
every new field is zero-initialised and every new branch is gated on
mount->v2_files or header.version==2.
"""
import os
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("patch_v377: set XNU_WORK")
W = Path(W)
M = W / "bsd/miscfs/mockfs"

# Global idempotence: next_sibling is only introduced by this patch.
_probe = W / "bsd/miscfs/mockfs/mockfs_fsnode.h"
if _probe.read_text(encoding="utf-8", errors="replace").find("next_sibling") >= 0:
    print("patch_v377: already applied -- skip")
    sys.exit(0)


def edit(rel, replacements):
    p = W / rel
    s = p.read_text(encoding="utf-8", errors="replace")
    for old, new, tag in replacements:
        if tag in s:
            continue  # idempotent: this hunk already applied
        c = s.count(old)
        if c != 1:
            sys.exit(f"patch_v377: [{rel}] anchor for {tag} count={c} (want 1)")
        s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print(f"patch_v377: {rel} ok")


# ---------------------------------------------------------------- fsnode.h
edit("bsd/miscfs/mockfs/mockfs_fsnode.h", [(
"""\tstruct mockfs_fsnode * child_c; /* Offline test input. */
};""",
"""\tstruct mockfs_fsnode * child_c; /* Offline test input. */
\t/* g0245d v377: N4KROOT v2 named-file support */
\tstruct mockfs_fsnode * next_sibling; /* v2: next file in mount->v2_files */
\tchar name[64];                       /* v2: basename key for lookup */
};""",
"v377 fsnode fields")])

# ------------------------------------------------------------------- mockfs.h
edit("bsd/miscfs/mockfs/mockfs.h", [(
"""\tuint64_t        mockfs_memdev_size;     /* Size of the backing store (valid if memory backed) */
};""",
"""\tuint64_t        mockfs_memdev_size;     /* Size of the backing store (valid if memory backed) */
\t/* g0245d v377: N4KROOT v2 path table */
\tmockfs_fsnode_t v2_files;               /* chain of VREG nodes parsed from v2 table */
\tuint32_t        v2_count;               /* number of v2 files */
};""",
"v377 mount fields")])

# ----------------------------------------------------------------- vfsops.c
V2_STRUCTS = r"""
/* g0245d v377: N4KROOT v2 on-disk format (all little-endian). */
struct n4kroot_v2_hdr {
	char     magic[8];       /* "N4KROOT\0" */
	uint32_t version;        /* 2 */
	uint32_t count;          /* number of entries, <= 32 */
	uint32_t hdr_size;       /* 4096 */
	uint32_t flags;          /* 0 */
	uint64_t image_size;     /* total image bytes */
};
struct n4kroot_v2_ent {
	char     path[96];
	uint64_t offset;
	uint64_t size;
	uint32_t type;
	uint32_t reserved;
};
#define N4K_V2_MAX 32u
#define N4K_V2_ENT_SIZE 120u
"""

edit("bsd/miscfs/mockfs/mockfs_vfsops.c", [
(
"""\tuint64_t launch_offset, launch_size, test_offset, test_size;
};""",
"""\tuint64_t launch_offset, launch_size, test_offset, test_size;
};
""" + V2_STRUCTS,
"v377 structs"),
(
"""\tstruct mockfs_test_header header = {0};
\tbuf_t header_buf = NULL;""",
"""\tstruct mockfs_test_header header = {0};
\tuint8_t * v377_raw = NULL;      /* v377: full 4K header block for v2 table */
\tbuf_t header_buf = NULL;""",
"v377 raw decl"),
(
"""\t\tmemcpy(&header, (void *)buf_dataptr(header_buf), sizeof(header));""",
"""\t\tmemcpy(&header, (void *)buf_dataptr(header_buf), sizeof(header));
\t\tv377_raw = kalloc_data(4096, Z_WAITOK | Z_ZERO);
\t\tmemcpy(v377_raw, (void *)buf_dataptr(header_buf), 4096);""",
"v377 raw copy"),
(
"""\tif (!memcmp(header.magic, "N4KROOT", 8)) {
\t\tuint64_t bytes = rvp->v_specinfo->si_devsize;""",
"""\tif (!memcmp(header.magic, "N4KROOT", 8) && header.version == 1) {
\t\tuint64_t bytes = rvp->v_specinfo->si_devsize;""",
"v377 v1 guard"),
(
"""\t\tmockfs_mount_data->mockfs_memory_backed = FALSE;
\t\ttest_image = TRUE;
\t}
""",
"""\t\tmockfs_mount_data->mockfs_memory_backed = FALSE;
\t\ttest_image = TRUE;
\t} else if (!memcmp(header.magic, "N4KROOT", 8) && header.version == 2) {
\t\t/* g0245d v377: generic N-file path table.  Build VREG nodes into a
\t\t * private chain; do NOT touch child_a/b/c so v1 layout stays intact. */
\t\tstruct n4kroot_v2_hdr * vh = (struct n4kroot_v2_hdr *)v377_raw;
\t\tuint64_t bytes = rvp->v_specinfo->si_devsize;
\t\tuint32_t i, n = vh->count;
\t\t{ extern void g0245d_trace_u(const char *, unsigned int);
\t\t  g0245d_trace_u("v377 cnt", n); }
\t\tif (!v377_raw || n == 0 || n > N4K_V2_MAX ||
\t\t    vh->hdr_size != 4096 || vh->flags != 0 ||
\t\t    vh->image_size == 0 || vh->image_size > bytes) {
\t\t\t{ extern void g0245d_trace(const char *);
\t\t\t  g0245d_trace("v377 badhdr"); }
\t\t\trvalue = EINVAL;
\t\t\tgoto done;
\t\t}
\t\tmockfs_mount_data->mockfs_memory_backed = FALSE;
\t\tmockfs_mount_data->v2_count = n;
\t\tfor (i = 0; i < n; i++) {
\t\t\tstruct n4kroot_v2_ent * e = (struct n4kroot_v2_ent *)
\t\t\t    (v377_raw + 32 + (uint32_t)i * N4K_V2_ENT_SIZE);
\t\t\tmockfs_fsnode_t fn = NULL;
\t\t\tconst char * base;
\t\t\tuint64_t off = e->offset, sz = e->size;
\t\t\tif (off < 4096 || (off & 4095) || sz == 0 || off + sz > bytes) {
\t\t\t\trvalue = EINVAL;
\t\t\t\tgoto done;
\t\t\t}
\t\t\te->path[95] = '\0';
\t\t\tbase = strrchr(e->path, '/');
\t\t\tbase = base ? base + 1 : e->path;
\t\t\tif ((rvalue = mockfs_fsnode_create(mp, MOCKFS_FILE, &fn))) {
\t\t\t\tgoto done;
\t\t\t}
\t\t\tfn->backing_offset = off;
\t\t\tfn->size = sz;
\t\t\tfn->parent = root_fsnode;   /* vnode dvp; not adopted into a/b/c */
\t\t\tstrlcpy(fn->name, base, sizeof(fn->name));
\t\t\tfn->next_sibling = mockfs_mount_data->v2_files;
\t\t\tmockfs_mount_data->v2_files = fn;
\t\t}
\t\t{ extern void g0245d_trace_u(const char *, unsigned int);
\t\t  g0245d_trace_u("v377 built", n); }
\t}
""",
"v377 v2 parse"),
(
"""done:
\tif (rvalue) {""",
"""done:
\tif (v377_raw) {
\t\tkfree_data(v377_raw, 4096);
\t\tv377_raw = NULL;
\t}
\tif (rvalue) {""",
"v377 raw free"),
])

# ----------------------------------------------------------------- vnops.c
edit("bsd/miscfs/mockfs/mockfs_vnops.c", [
(
"""\tfsnode = (mockfs_fsnode_t) dvp->v_data;
\ttarget_fsnode = NULL;

\tif ((op == LOOKUP || !(cnp->cn_flags & ISLASTCN)) && (fsnode->type == MOCKFS_ROOT)) {""",
"""\tfsnode = (mockfs_fsnode_t) dvp->v_data;
\ttarget_fsnode = NULL;

\t/* g0245d v377: N4KROOT v2 named-file lookup.  Directory components are
\t * aliased to root (same trick as v1); leaf names match the v2 chain. */
\t{
\t\tmockfs_mount_t v377_mnt = (mockfs_mount_t)dvp->v_mount->mnt_data;
\t\tif (v377_mnt && v377_mnt->v2_files && fsnode->type == MOCKFS_ROOT) {
\t\t\tmockfs_fsnode_t vf;
\t\t\theld_char = cnp->cn_nameptr[cnp->cn_namelen];
\t\t\tcnp->cn_nameptr[cnp->cn_namelen] = '\0';
\t\t\tif (!strcmp(cnp->cn_nameptr, "sbin") || !strcmp(cnp->cn_nameptr, "usr") ||
\t\t\t    !strcmp(cnp->cn_nameptr, "lib")  || !strcmp(cnp->cn_nameptr, "bin") ||
\t\t\t    !strcmp(cnp->cn_nameptr, "System") || !strcmp(cnp->cn_nameptr, "Library") ||
\t\t\t    !strcmp(cnp->cn_nameptr, "Caches") || !strcmp(cnp->cn_nameptr, "com.apple.dyld") ||
\t\t\t    !strcmp(cnp->cn_nameptr, "private") || !strcmp(cnp->cn_nameptr, "var")) {
\t\t\t\ttarget_fsnode = fsnode;
\t\t\t} else if (!strcmp(cnp->cn_nameptr, "dev")) {
\t\t\t\tmockfs_fsnode_child_by_type(fsnode, MOCKFS_DEV, &target_fsnode);
\t\t\t} else {
\t\t\t\tfor (vf = v377_mnt->v2_files; vf; vf = vf->next_sibling) {
\t\t\t\t\tif (!strcmp(vf->name, cnp->cn_nameptr)) {
\t\t\t\t\t\ttarget_fsnode = vf;
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tif (!target_fsnode) {
\t\t\t\t\trvalue = ENOENT;
\t\t\t\t\t{ extern void g0245d_trace(const char *);
\t\t\t\t\t  g0245d_trace("v377 enoent"); }
\t\t\t\t}
\t\t\t}
\t\t\tcnp->cn_nameptr[cnp->cn_namelen] = held_char;
\t\t\tif (target_fsnode) {
\t\t\t\trvalue = mockfs_fsnode_vnode(target_fsnode, vpp);
\t\t\t}
\t\t\treturn rvalue;
\t\t}
\t}

\tif ((op == LOOKUP || !(cnp->cn_flags & ISLASTCN)) && (fsnode->type == MOCKFS_ROOT)) {""",
"v377 lookup"),
])

# ---------------------------------------------------------------- vfsops unmount
p = W / "bsd/miscfs/mockfs/mockfs_vfsops.c"
s = p.read_text(encoding="utf-8", errors="replace")
if "v377 unmount free" not in s:
    old = """\troot_fsnode = mockfs_mnt->mockfs_root;
\tmockfs_mnt->mockfs_root = NULL;
\trvalue = mockfs_fsnode_destroy(root_fsnode);"""
    new = """\t/* g0245d v377: release the private v2 file chain (not in a/b/c). */
\t{
\t\tmockfs_fsnode_t vf = mockfs_mnt->v2_files;
\t\twhile (vf) {
\t\t\tmockfs_fsnode_t nx = vf->next_sibling;
\t\t\tkfree_type(struct mockfs_fsnode, vf);
\t\t\tvf = nx;
\t\t}
\t\tmockfs_mnt->v2_files = NULL;
\t}
\troot_fsnode = mockfs_mnt->mockfs_root;
\tmockfs_mnt->mockfs_root = NULL;
\trvalue = mockfs_fsnode_destroy(root_fsnode);"""
    if s.count(old) != 1:
        sys.exit(f"patch_v377: unmount anchor count={s.count(old)} (want 1)")
    s = s.replace(old, new, 1)
    # marker comment so the idempotence check holds
    s = s.replace("g0245d v377: release the private v2 file chain (not in a/b/c).",
                  "g0245d v377 unmount free: release the private v2 file chain (not in a/b/c).")
    p.write_text(s, encoding="utf-8")
    print("patch_v377: mockfs_vfsops.c unmount ok")

print("patch_v377: done (N4KROOT v2 path-table support)")
