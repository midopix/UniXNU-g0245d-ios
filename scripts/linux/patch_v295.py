#!/usr/bin/env python3
"""g0245d v295 -- probe the buffer-cache allocation path (pure probes).

Evidence (v294 photo, 2026-11-23 13:57): seq 8491-8496 show `v294 mmr enter` /
`kalloc done` (obscured) / `ioctl ok` / `v294 bread call`, heartbeat
`hb 8496/8453 v294 bread call`, and NO `v294 bread ret`.  So inside
mockfs_mountroot(): kalloc_type(Z_WAITOK) did NOT sleep, fsnode_create did not
sleep, the DKIOCGETMEMDEVINFO ioctl returned 0 -- and the machine is stuck in
buf_meta_bread(rvp, 0, 4096, ...) (vfs_bio.c:2331).

buf_meta_bread -> bio_doread -> buf_getblk -> (new buf) getnewbuf ->
  [grow path] zalloc_flags(buf_hdr_zone, Z_WAITOK|Z_NOFAIL)   <- suspect A
  buf_getblk(new buf) -> allocbuf -> grab_memory_for_meta_buf ->
      kheap_alloc(KHEAP_VFS_BIO, 4096, Z_NOPAGEWAIT)          <- suspect B1
      recycle_buf_from_pool
      kheap_alloc(KHEAP_VFS_BIO, 4096, Z_WAITOK)              <- suspect B2
then VNOP_STRATEGY -> spec_strategy -> bdevsw[].d_strategy = mdevstrategy
(synchronous bcopy + buf_biodone, so buf_biowait cannot sleep).

Related facts (source-verified):
  - bufinit() pre-allocates max_nbuf_headers headers from the STATIC array
    buf_headers[] into BQ_EMPTY.  buf_headers comes from bsd_startupearly()'s
    kmem_alloc on bufferhdr_map (KMA_NOFAIL -- fails silently!).  If that
    mapping is broken, every pre-allocated header is garbage and getnewbuf
    falls into the grow path -> suspect A.
  - max_nbuf_headers = sane_size/50 (2% of RAM) clipped at 16384.
  - buf headers are NEVER freed back to buf_hdr_zone (no zfree in the tree).
  - Z_WAITOK allocation walls seen so far: v257 kalloc_type, v279 kmem_zalloc.
    Suspects A/B2 are the same wall in different clothes.

v295 adds probes (no behavior change):
  bsd/dev/unix_startup.c : v295 sue suballoc / sue done (kmem_alloc ret)
  bsd/vfs/vfs_bio.c      : v295 bufinit enter / bufinit done <nbuf_headers>
                           v295 getblk call/ret, strat call/ret (bio_doread)
                           v295 allocbuf c1/r1 (incore branch)
                           v295 allocbuf c2/r2 (new-buf branch)
                           v295 gnb enter, gnb grow, hdr zalloc (getnewbuf)
                           v295 meta try1, meta zwait (grab_memory_for_meta_buf)
  bsd/dev/memdev.c       : v295 mdev strat (strategy entry)

Idempotent.  Run AFTER patch_v294.py:
    XNU_WORK=<xnu-work> python3 patch_v295.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BIO = os.path.join(WORK, "bsd/vfs/vfs_bio.c")
STARTUP = os.path.join(WORK, "bsd/dev/unix_startup.c")
MEMDEV = os.path.join(WORK, "bsd/dev/memdev.c")
MARK = "g0245d v295"


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


# ---- bsd/dev/unix_startup.c: bufferhdr mapping probes ----------------------
s = read(STARTUP)
if MARK not in s:
    s = sub(
        s,
        """	bufferhdr_map = kmem_suballoc(kernel_map,""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 sue suballoc"); }
	bufferhdr_map = kmem_suballoc(kernel_map,""",
        "v295: sue suballoc",
    )
    s = sub(
        s,
        """	buf_headers = (struct buf *)bufferhdr_range.min_address;""",
        """	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v295 sue done", (unsigned int)size); }
	buf_headers = (struct buf *)bufferhdr_range.min_address;""",
        "v295: sue done",
    )
    write(STARTUP, s)
    print("unix_startup.c: v295 bufferhdr probes installed")
else:
    print("unix_startup.c: already v295")

# ---- bsd/vfs/vfs_bio.c: buffer-cache ladder --------------------------------
s = read(BIO)
if MARK not in s:
    # bufinit entry / done
    s = sub(
        s,
        """	nbuf_headers = 0;
	/* Initialize the buffer queues ('freelists') and the hash table */""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 bufinit enter"); }
	nbuf_headers = 0;
	/* Initialize the buffer queues ('freelists') and the hash table */""",
        "v295: bufinit enter",
    )
    s = sub(
        s,
        """	boot_nbuf_headers = nbuf_headers;

	TAILQ_INIT(&iobufqueue);""",
        """	boot_nbuf_headers = nbuf_headers;
	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v295 bufinit done", (unsigned int)nbuf_headers); }

	TAILQ_INIT(&iobufqueue);""",
        "v295: bufinit done",
    )
    # bio_doread: getblk call/ret
    s = sub(
        s,
        """	bp = buf_getblk(vp, blkno, size, 0, 0, queuetype);

	/*
	 * If buffer does not have data valid, start a read.""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 getblk call"); }
	bp = buf_getblk(vp, blkno, size, 0, 0, queuetype);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 getblk ret"); }

	/*
	 * If buffer does not have data valid, start a read.""",
        "v295: bio_doread getblk call/ret",
    )
    # bio_doread: strat call/ret
    s = sub(
        s,
        """		VNOP_STRATEGY(bp);

		trace(TR_BREADMISS, pack(vp, size), blkno);""",
        """		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 strat call"); }
		VNOP_STRATEGY(bp);
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 strat ret"); }

		trace(TR_BREADMISS, pack(vp, size), blkno);""",
        "v295: bio_doread strat call/ret",
    )
    # buf_getblk incore branch: allocbuf
    s = sub(
        s,
        """				if (bp->b_bufsize != (uint32_t)size) {
					allocbuf(bp, size);
				}""",
        """				if (bp->b_bufsize != (uint32_t)size) {
					{ extern void g0245d_trace(const char *);
					  g0245d_trace("v295 allocbuf c1"); }
					allocbuf(bp, size);
					{ extern void g0245d_trace(const char *);
					  g0245d_trace("v295 allocbuf r1"); }
				}""",
        "v295: allocbuf incore branch",
    )
    # buf_getblk new-buf branch: allocbuf
    s = sub(
        s,
        """		bgetvp_locked(vp, bp);

		lck_mtx_unlock(&buf_mtx);

		allocbuf(bp, size);""",
        """		bgetvp_locked(vp, bp);

		lck_mtx_unlock(&buf_mtx);

		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 allocbuf c2"); }
		allocbuf(bp, size);
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 allocbuf r2"); }""",
        "v295: allocbuf new-buf branch",
    )
    # getnewbuf: entry
    s = sub(
        s,
        """getnewbuf(int slpflag, int slptimeo, int * queue)
{
	buf_t   bp;
	buf_t   lru_bp;""",
        """getnewbuf(int slpflag, int slptimeo, int * queue)
{
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 gnb enter"); }
	buf_t   bp;
	buf_t   lru_bp;""",
        "v295: getnewbuf entry",
    )
    # getnewbuf: grow branch
    s = sub(
        s,
        """		 * That avoids over commits
		 */
		nbuf_headers++;
		goto add_newbufs;""",
        """		 * That avoids over commits
		 */
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 gnb grow"); }
		nbuf_headers++;
		goto add_newbufs;""",
        "v295: getnewbuf grow",
    )
    # getnewbuf: header zalloc
    s = sub(
        s,
        """		/* Create a new temporary buffer header */
		bp = zalloc_flags(buf_hdr_zone, Z_WAITOK | Z_NOFAIL);""",
        """		/* Create a new temporary buffer header */
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v295 hdr zalloc"); }
		bp = zalloc_flags(buf_hdr_zone, Z_WAITOK | Z_NOFAIL);""",
        "v295: header zalloc",
    )
    # grab_memory_for_meta_buf: first try + Z_WAITOK fallback
    s = sub(
        s,
        """	ptr = kheap_alloc(KHEAP_VFS_BIO, nsize, Z_NOPAGEWAIT);""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 meta try1"); }
	ptr = kheap_alloc(KHEAP_VFS_BIO, nsize, Z_NOPAGEWAIT);""",
        "v295: meta first try",
    )
    s = sub(
        s,
        """			ptr = kheap_alloc(KHEAP_VFS_BIO, nsize, Z_WAITOK);""",
        """			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v295 meta zwait"); }
			ptr = kheap_alloc(KHEAP_VFS_BIO, nsize, Z_WAITOK);""",
        "v295: meta Z_WAITOK fallback",
    )
    write(BIO, s)
    print("vfs_bio.c: v295 buffer-cache probes installed")
else:
    print("vfs_bio.c: already v295")

# ---- bsd/dev/memdev.c: strategy entry --------------------------------------
s = read(MEMDEV)
if MARK not in s:
    s = sub(
        s,
        """mdevstrategy(struct buf *bp)
{
	unsigned int left, lop, csize;""",
        """mdevstrategy(struct buf *bp)
{
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v295 mdev strat"); }
	unsigned int left, lop, csize;""",
        "v295: mdevstrategy entry",
    )
    write(MEMDEV, s)
    print("memdev.c: v295 strategy probe installed")
else:
    print("memdev.c: already v295")

print("v295 done (pure probes; no behavior change)")
