#!/usr/bin/env python3
"""g0245d v297 -- pinpoint the buf_getblk freeze + disable background cleaners.

Evidence (v295 photo 14:11, v296 photo 15:08, both frozen at the same point):
  hb line always shows the CURRENT last label (hb redraws on every trace), so
  the freeze point is exact: last trace = `v295 getblk call`, i.e. inside
  bio_doread() right before buf_getblk(vp, 0, 4096) returns -- and NOTHING
  after: no `gnb enter`, no `allocbuf c1`, no `getblk ret`.
  v296 post-console trace count = v295 + 1 (exactly the `v296 cyc 1` probe),
  and NO `v296 mre` ever => vfs_mountroot NEVER returned: the while(TRUE)
  retry loop never iterated.  All versions freeze on the FIRST
  buf_meta_bread, inside buf_getblk between entry and getnewbuf.

buf_getblk structure (vfs_bio.c:3072):
    dp = BUFHASH(vp, blkno);
start:
    lck_mtx_lock_spin(&buf_mtx);          <- candidate 1: mutex wedge
    if (incore_locked(vp, blkno, dp))     <- candidate 2: garbage hash chain
        ... busy path: msleep(0) + goto start (hot spin)
    else
        getnewbuf(...)                    <- `v295 gnb enter` never printed

Facts: main bufhash starts EMPTY (bufinit only bins pre-allocated headers
into invalhash); buf_mtx is statically declared (not uninitialized).  So the
top suspects are:
  (1) buf_mtx held forever by the bcleanbuf kernel thread started at the END
      of bufinit -- its msleep0(continuation) sleep is exactly the kind of
      sleeper that already misbehaved in this bringup (v291).
  (2) bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, ...) -- a kalloc that
      may have returned broken memory (v257 pattern); incore_locked then
      walks a garbage chain forever.

v297 (probes + two deliberate disables):
  - bufinit: dump bufhashtbl / buf_headers pointers (tracev).
  - buf_getblk: `v297 bgb enter` / dump `dp->lh_first` (`v297 first`) BEFORE
    the lock / `v297 bgb mtx` after lck_mtx_lock_spin / `v297 bgb busy` in
    the busy-msleep branch.
  - incore_locked: `v297 inc <n>` per hash-chain step (static counter).
  - bcleanbuf_thread: `v297 bcb run` / `bcb locked` / `bcb sleep`.
  - DISABLED: kernel_thread_start(bcleanbuf_thread) and the
    vm_set_buffer_cleanup_callout(buffer_cache_gc) registration.  Neither is
    needed at mountroot time.  If the freeze disappears the culprit is named;
    if not, the probes pinpoint the true wall and boot proceeds to the errno.

Idempotent.  Run AFTER patch_v296.py:
    XNU_WORK=<xnu-work> python3 patch_v297.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BIO = os.path.join(WORK, "bsd/vfs/vfs_bio.c")
MARK = "g0245d v297"


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
    print("vfs_bio.c: already v297")
    sys.exit(0)

# ---- bufinit: dump hash table + header array pointers ----------------------
s = sub(
    s,
    """	bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, &bufhash);

	buf_busycount = 0;""",
    """	bufhashtbl = hashinit(nbuf_hashelements, M_CACHE, &bufhash);
	{ extern void g0245d_tracev(const char *, unsigned long long);
	  g0245d_tracev("v297 tbl", (unsigned long long)(uintptr_t)bufhashtbl); }
	{ extern void g0245d_tracev(const char *, unsigned long long);
	  g0245d_tracev("v297 bh", (unsigned long long)(uintptr_t)&buf_headers[0]); }

	buf_busycount = 0;""",
    "v297: bufinit pointer dump",
)

# ---- buf_getblk: entry / hash head / post-lock / busy path ------------------
s = sub(
    s,
    """	ret_only_valid = operation & BLK_ONLYVALID;
	operation &= ~BLK_ONLYVALID;
	dp = BUFHASH(vp, blkno);
start:
	lck_mtx_lock_spin(&buf_mtx);""",
    """	ret_only_valid = operation & BLK_ONLYVALID;
	operation &= ~BLK_ONLYVALID;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v297 bgb enter"); }
	dp = BUFHASH(vp, blkno);
	{ extern void g0245d_tracev(const char *, unsigned long long);
	  g0245d_tracev("v297 first", (unsigned long long)(uintptr_t)dp->lh_first); }
start:
	lck_mtx_lock_spin(&buf_mtx);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v297 bgb mtx"); }""",
    "v297: buf_getblk entry ladder",
)

s = sub(
    s,
    """			case BLK_READ:
			case BLK_WRITE:
			case BLK_META:
				SET(bp->b_lflags, BL_WANTED);""",
    """			case BLK_READ:
			case BLK_WRITE:
			case BLK_META:
				{ extern void g0245d_trace(const char *);
				  g0245d_trace("v297 bgb busy"); }
				SET(bp->b_lflags, BL_WANTED);""",
    "v297: busy-wait branch",
)

# ---- incore_locked: per-step counter ----------------------------------------
s = sub(
    s,
    """	/* Search hash chain */
	for (bp = dp->lh_first; bp != NULL; bp = bp->b_hash.le_next) {
		if (bp->b_lblkno == blkno && bp->b_vp == vp &&""",
    """	/* Search hash chain */
	for (bp = dp->lh_first; bp != NULL; bp = bp->b_hash.le_next) {
		{ extern void g0245d_trace_u(const char *, unsigned int);
		  static unsigned int g0245d_inc_n = 0;
		  g0245d_trace_u("v297 inc", ++g0245d_inc_n); }
		if (bp->b_lblkno == blkno && bp->b_vp == vp &&""",
    "v297: incore walk counter",
)

# ---- bcleanbuf_thread: lifecycle probes -------------------------------------
s = sub(
    s,
    """	struct buf *bp;
	int error = 0;
	int loopcnt = 0;

	for (;;) {
		lck_mtx_lock_spin(&buf_mtx);

		while ((bp = TAILQ_FIRST(&bufqueues[BQ_LAUNDRY])) == NULL) {
			(void)msleep0(&bufqueues[BQ_LAUNDRY], &buf_mtx, PRIBIO | PDROP, "blaundry", 0, (bcleanbufcontinuation)bcleanbuf_thread);""",
    """	struct buf *bp;
	int error = 0;
	int loopcnt = 0;

	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v297 bcb run"); }
	for (;;) {
		lck_mtx_lock_spin(&buf_mtx);
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v297 bcb locked"); }

		while ((bp = TAILQ_FIRST(&bufqueues[BQ_LAUNDRY])) == NULL) {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v297 bcb sleep"); }
			(void)msleep0(&bufqueues[BQ_LAUNDRY], &buf_mtx, PRIBIO | PDROP, "blaundry", 0, (bcleanbufcontinuation)bcleanbuf_thread);""",
    "v297: bcleanbuf thread probes",
)

# ---- DISABLE the bcleanbuf kernel thread ------------------------------------
s = sub(
    s,
    """	/* create worker thread */
	kernel_thread_start((thread_continue_t)bcleanbuf_thread, NULL, &thread);
	thread_deallocate(thread);""",
    """	/* create worker thread */
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v297 bcb disabled"); }
	/* g0245d v297: thread start disabled -- suspected buf_mtx wedge
	 * (its msleep0 continuation sleep is the same sleeper class that
	 * wedged kernel_memory_allocate in v291).
	 */
	/* kernel_thread_start((thread_continue_t)bcleanbuf_thread, NULL, &thread); */
	/* thread_deallocate(thread); */
	(void)thread;""",
    "v297: disable bcleanbuf thread",
)

# ---- DISABLE the buffer_cache_gc callout registration -----------------------
s = sub(
    s,
    """	/* Register a callout for relieving vm pressure */
	if (vm_set_buffer_cleanup_callout(buffer_cache_gc) != KERN_SUCCESS) {
		panic("Couldn't register buffer cache callout for vm pressure!");
	}""",
    """	/* Register a callout for relieving vm pressure */
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v297 gc disabled"); }
	/* g0245d v297: buffer_cache_gc callout disabled (same buf_mtx wedge
	 * suspicion as the bcleanbuf thread).
	 */
	/* if (vm_set_buffer_cleanup_callout(buffer_cache_gc) != KERN_SUCCESS) {
	 *     panic("Couldn't register buffer cache callout for vm pressure!");
	 * }
	 */""",
    "v297: disable buffer_cache_gc callout",
)

write(BIO, s)
print("vfs_bio.c: v297 probes + cleaner disables installed")
