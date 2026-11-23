#!/usr/bin/env python3
"""g0245d v301 -- dissect the namei() internal freeze.

Evidence (v300 photo 16:43:03):
  `v300 km namei call` entered namei(); a SECOND mockfs_fsnode_vnode ran
  (`v299 fsv enter/lock ok/vcreate call/done`, the lookup("/dev")->VNOP_LOOKUP
  path), then heartbeat froze at `hb 8547/8504 v299 fsv done`.  No
  `km namei ret` => stuck inside namei(), after VNOP_LOOKUP succeeded but
  before namei() returned.  devfs/mount_common/cleanup all ruled out.

v301 (label-only diagnostic probes, no behavior change):
  vfs_lookup.c:
   - lookup(): after VNOP_LOOKUP, before/after lookup_handle_found_vnode.
     `v301 look vnode ret<r>` / `v301 look found call` / `v301 look found ret<r>`
     / `v301 look return<r>`.
   - lookup_handle_found_vnode(): entry, before/after
     lookup_traverse_mountpoints, before name-cache update.
     `v301 lhfv enter` / `v301 lhfv trav call` / `v301 lhfv trav ret<r>` /
     `v301 lhfv cache`.
   - namei(): after `lookup(ndp)` returns, at the success `return 0`,
     at error_out.  `v301 namei lk ret<r>` / `v301 namei exit ok` /
     `v301 namei err`.

Idempotent.  Run on the tree that already has v300 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v301.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

LOOKUP = os.path.join(WORK, "bsd/vfs/vfs_lookup.c")
MARK = "g0245d v301"


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


s = read(LOOKUP)
if MARK in s:
    print("vfs_lookup.c: already v301")
else:
    # 1) lookup_handle_found_vnode(): entry + name-cache + traverse mountpoints
    s = sub(
        s,
        """	vnode_t dp;
	int error;
	char *cp;

	dp = ndp->ni_vp;
	*keep_going = 0;

	if (ndp->ni_vp == NULLVP) {
		panic("NULL ni_vp in %s", __FUNCTION__);
	}""",
        """	vnode_t dp;
	int error;
	char *cp;
	""" + TRACE % "v301 lhfv enter" + """

	dp = ndp->ni_vp;
	*keep_going = 0;

	if (ndp->ni_vp == NULLVP) {
		panic("NULL ni_vp in %s", __FUNCTION__);
	}""",
        "v301: lhfv entry",
    )
    s = sub(
        s,
        """	} else {
		lookup_consider_update_cache(ndp->ni_dvp, dp, cnp, nc_generation);
	}

	/*
	 * Check to see if the vnode has been mounted on...""",
        """	} else {
		""" + TRACE % "v301 lhfv cache" + """
		lookup_consider_update_cache(ndp->ni_dvp, dp, cnp, nc_generation);
	}

	/*
	 * Check to see if the vnode has been mounted on...""",
        "v301: lhfv cache marker",
    )
    s = sub(
        s,
        """	error = lookup_traverse_mountpoints(ndp, cnp, dp, vbusyflags, ctx);
	dp = ndp->ni_vp;
	if (error) {
		goto out;
	}""",
        """	""" + TRACE % "v301 lhfv trav call" + """
	error = lookup_traverse_mountpoints(ndp, cnp, dp, vbusyflags, ctx);
	""" + TRACEU % ("v301 lhfv trav ret", "error") + """
	dp = ndp->ni_vp;
	if (error) {
		goto out;
	}""",
        "v301: lhfv traverse_mountpoints probes",
    )

    # 2) lookup(): after VNOP_LOOKUP, around lookup_handle_found_vnode, at return
    s = sub(
        s,
        """	error = VNOP_LOOKUP(dp, &ndp->ni_vp, cnp, ctx);

	if (error) {
lookup_error:""",
        """	error = VNOP_LOOKUP(dp, &ndp->ni_vp, cnp, ctx);
	""" + TRACEU % ("v301 look vnode ret", "error") + """

	if (error) {
lookup_error:""",
        "v301: lookup VNOP_LOOKUP return probe",
    )
    s = sub(
        s,
        """returned_from_lookup_path:
	/* We'll always have an iocount on ni_vp when this finishes. */
	error = lookup_handle_found_vnode(ndp, cnp, rdonly, vbusyflags, &keep_going, nc_generation, wantparent, atroot, ctx);
	if (error != 0) {
		goto bad2;
	}""",
        """returned_from_lookup_path:
	/* We'll always have an iocount on ni_vp when this finishes. */
	""" + TRACE % "v301 look found call" + """
	error = lookup_handle_found_vnode(ndp, cnp, rdonly, vbusyflags, &keep_going, nc_generation, wantparent, atroot, ctx);
	""" + TRACEU % ("v301 look found ret", "error") + """
	if (error != 0) {
		goto bad2;
	}""",
        "v301: lookup found_vnode probes",
    )
    s = sub(
        s,
        """		last_dp = dp;

		goto dirloop;
	}

	return 0;
bad2:""",
        """		last_dp = dp;

		goto dirloop;
	}

	""" + TRACE % "v301 look return" + """
	return 0;
bad2:""",
        "v301: lookup return probe",
    )

    # 3) namei(): after lookup(ndp) returns, at the success return 0, at error_out
    s = sub(
        s,
        """		if ((error = lookup(ndp))) {
			goto error_out;
		}

		/*
		 * Check for symbolic link
		 */""",
        """		if ((error = lookup(ndp))) {
			""" + TRACEU % ("v301 namei lk ret", "error") + """
			goto error_out;
		}
		""" + TRACE % "v301 namei lk ok" + """

		/*
		 * Check for symbolic link
		 */""",
        "v301: namei lookup-return probes",
    )
    s = sub(
        s,
        """			if (rootdir_with_usecount) {
				lck_rw_lock_shared(&rootvnode_rw_lock);
				if (rootdir_with_usecount == rootvnode) {
					old_count = os_atomic_dec_orig(&rootdir_with_usecount->v_usecount, relaxed);
					if (old_count < 2) {
						/*
						 * There needs to have been at least 1 usecount left on the rootvnode
						 */
						panic("(3) Unexpected pre-decrement value (%d) of usecount for rootvnode %p",
						    old_count, rootdir_with_usecount);
					}
					rootdir_with_usecount = NULLVP;
				}
				lck_rw_unlock_shared(&rootvnode_rw_lock);
				if (rootdir_with_usecount) {
					vnode_rele(rootdir_with_usecount);
					rootdir_with_usecount = NULLVP;
				}
			}

			return 0;""",
        """			if (rootdir_with_usecount) {
				""" + TRACE % "v301 namei rootdec" + """
				lck_rw_lock_shared(&rootvnode_rw_lock);
				if (rootdir_with_usecount == rootvnode) {
					old_count = os_atomic_dec_orig(&rootdir_with_usecount->v_usecount, relaxed);
					if (old_count < 2) {
						/*
						 * There needs to have been at least 1 usecount left on the rootvnode
						 */
						panic("(3) Unexpected pre-decrement value (%d) of usecount for rootvnode %p",
						    old_count, rootdir_with_usecount);
					}
					rootdir_with_usecount = NULLVP;
				}
				lck_rw_unlock_shared(&rootvnode_rw_lock);
				if (rootdir_with_usecount) {
					vnode_rele(rootdir_with_usecount);
					rootdir_with_usecount = NULLVP;
				}
			}

			""" + TRACE % "v301 namei exit ok" + """
			return 0;""",
        "v301: namei rootdec + exit probes",
    )

    write(LOOKUP, s)
    print("vfs_lookup.c: v301 probes installed")

print("v301 patch complete")
