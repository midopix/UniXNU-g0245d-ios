#!/usr/bin/env python3
"""g0245d v298 -- replace the two remaining allocator walls in the buf path.

Evidence (v297 photo 15:27, photos/v297/screen.jpg):
  hb label froze at `v297 bgb enter`; `v297 first` (which dumps
  dp->lh_first BEFORE the lock) never printed.  The only code between the
  two probes is `dp = BUFHASH(vp, blkno)` (pure arithmetic) and the
  dereference `dp->lh_first` inside the tracev argument.  tracev itself is
  proven good (the same tracev printed tbl/bh at bufinit earlier in the
  same boot, and execution reached bread call afterwards).
  => the machine died on the FIRST read of a bufhashtbl bucket.

Root cause (source, kern_subr.c hashinit):
  hashinit allocates via kalloc_type(..., Z_NOWAIT | Z_ZERO) -- the v257
  contract returns NULL instead of sleeping, and bufinit never checks:
      bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, &bufhash);
  NULL bufhashtbl (and/or mask left 0) makes the first BUFHASH dereference
  fault.  Disabling bcleanbuf + buffer_cache_gc in v297 changed nothing =>
  candidate (1) mutex wedge is excluded; the wall was always this read.

v298 (two fixes, both using the proven g0245d permanent pool -- bump
allocator over virgin grabbed pages, zero-filled, never sleeps):
  1. bufinit: allocate bufhashtbl unconditionally from the perm pool
     (hashsize = largest power of two <= nbuf_hashelements, matching
     hashinit's 1 << (fls(elements)-1); element = struct bufhashhdr, one
     pointer).  Zero-filled == empty chains, same as Z_ZERO.  We also set
     bufhash = hashsize-1 ourselves, so kalloc_type is fully bypassed.
     Probe `v298 hi null` records whether hashinit really returned NULL;
     `v298 hs` prints the table size; the existing `v297 tbl` dump now
     shows the final pointer.
  2. add_newbufs: replace zalloc_flags(buf_hdr_zone, Z_WAITOK | Z_NOFAIL)
     with a perm-pool header (struct buf, zero-filled -- bufhdrinit then
     initializes all fields).  buf headers are never zfree'd anywhere in
     the tree (verified in v295 round), so pool ownership is safe.  If the
     pool ever returns NULL we fall back to the original zalloc.  Probe
     `v298 hdr perm` / `v298 hdr zone`.

Next expected walls after these (probes already in place, untouched):
  allocbuf -> grab_memory_for_meta_buf kheap_alloc(Z_WAITOK) (`v295 meta
  zwait`), or nothing at all -- then bread ret / mount ret err (errno!) /
  mr ret ok.

Idempotent.  Run AFTER patch_v297.py:
    XNU_WORK=<xnu-work> python3 patch_v298.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BIO = os.path.join(WORK, "bsd/vfs/vfs_bio.c")
MARK = "g0245d v298"


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


s = read(BIO)
if MARK in s:
    print("vfs_bio.c: already v298")
    sys.exit(0)

# ---- 1. bufinit: perm-pool hash table ---------------------------------------
s = sub(
    s,
    """	bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, &bufhash);
	{ extern void g0245d_tracev(const char *, unsigned long long);
	  g0245d_tracev("v297 tbl", (unsigned long long)(uintptr_t)bufhashtbl); }""",
    """	bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, &bufhash);
	{	/* g0245d v298: hashinit uses kalloc_type(Z_NOWAIT|Z_ZERO); this
		 * early it can return NULL (v257 contract) and bufinit never
		 * checked -- NULL table made the first BUFHASH dereference
		 * (buf_getblk -> dp->lh_first) fault, the exact v297 freeze.
		 * Bypass kalloc entirely: perm pool is a bump allocator over
		 * virgin grabbed pages (zero-filled, never sleeps).
		 */
		extern void *g0245d_perm_pool_alloc(unsigned long);
		extern void g0245d_trace(const char *);
		extern void g0245d_trace_u(const char *, unsigned int);
		unsigned long g0245d_hs = 1;
		if (bufhashtbl == NULL) {
			g0245d_trace("v298 hi null");
		}
		while ((g0245d_hs << 1) <= (unsigned long)nbuf_hashelements) {
			g0245d_hs <<= 1;
		}
		bufhashtbl = g0245d_perm_pool_alloc(
		    g0245d_hs * sizeof(struct bufhashhdr));
		bufhash = g0245d_hs - 1;
		g0245d_trace_u("v298 hs", (unsigned int)g0245d_hs);
	}
	{ extern void g0245d_tracev(const char *, unsigned long long);
	  g0245d_tracev("v297 tbl", (unsigned long long)(uintptr_t)bufhashtbl); }""",
    "v298: perm-pool bufhashtbl",
)

# ---- 2. add_newbufs: perm-pool buf header ------------------------------------
s = sub(
    s,
    """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 hdr zalloc"); }
		bp = zalloc_flags(buf_hdr_zone, Z_WAITOK | Z_NOFAIL);
		bufhdrinit(bp);""",
    """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 hdr zalloc"); }
		{	/* g0245d v298: zone grow needs a page grab (the kernel_
			 * memory_allocate class that wedged in v291).  Headers
			 * are never zfree'd anywhere, so perm-pool ownership is
			 * safe; pool memory is zero-filled.
			 */
			extern void *g0245d_perm_pool_alloc(unsigned long);
			extern void g0245d_trace(const char *);
			bp = g0245d_perm_pool_alloc(sizeof(struct buf));
			g0245d_trace("v298 hdr perm");
			if (bp == NULL) {
				bp = zalloc_flags(buf_hdr_zone,
				    Z_WAITOK | Z_NOFAIL);
				g0245d_trace("v298 hdr zone");
			}
		}
		bufhdrinit(bp);""",
    "v298: perm-pool buf header in add_newbufs",
)

write(BIO, s)
print("vfs_bio.c: v298 perm-pool hash table + buf header installed")
