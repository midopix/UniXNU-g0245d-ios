#!/usr/bin/env python3
"""g0245d v296 -- make the mountroot retry loop self-reporting.

Evidence (v295 photo, 2026-11-23 14:11): heartbeat `hb 8581/8458 v295 getblk
call`.  base->label delta = 123, while the same position in v294 was 43 and a
single pass to the first `getblk call` should be ~48.  ~75 extra traces can
only come from repeated mountroot cycles:

  bsd_init.c:1007  `while (TRUE) { ... vfs_mountroot() ... }`  -- mountroot
  FAILS and bsd_init retries forever (classic X behaviour).  Each retry cycle
  is ~20 traces, so 2-3 cycles completed before the current one, i.e. the
  v294 "bread hang" is NOT a deterministic wall: buf_meta_bread now returns.
  The current label `getblk call` means we are either mid-cycle (spinning
  retry loop) or hung again inside buf_getblk on cycle ~4.

Failure exits inside mockfs_mountroot(): bread error / header-check EINVAL /
fsnode_create ENOMEM / fsnode_adopt error.  The errno is already printed by
v293/v294 probes, but the heartbeat line only shows the last probe's STRING,
so a photo cannot tell us the number.

v296 (probe build, one deliberate behaviour change):
  - bsd_init.c: cycle counter "v296 cyc <n>" at each retry; on failure
    "v296 mre e<errno>" formatted into the label string, then IOSleep(3000)
    so the heartbeat rests on the errno for 3 s per cycle (photo always wins).
  - mockfs_vfsops.c: after the superblock memcpy print magic/version/count
    ("v296 mg ...") and offsets ("v296 hd ..."); label every failure exit
    ("v296 brderr e<n>" / "v296 imgbad" / "v296 nodesbad" / "v296 ad1/2/3 e<n>").

Idempotent.  Run AFTER patch_v295.py:
    XNU_WORK=<xnu-work> python3 patch_v296.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "bsd/kern/bsd_init.c")
VFSOPS = os.path.join(WORK, "bsd/miscfs/mockfs/mockfs_vfsops.c")
MARK = "g0245d v296"


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


# ---- bsd/kern/bsd_init.c: retry-loop counter + errno label + 3s rest -------
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """		boot_progress_stage("vfs_mountroot enter");
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 mr call"); }""",
        """		boot_progress_stage("vfs_mountroot enter");
		{ extern void g0245d_trace(const char *);
		  static int g0245d_v296_cyc = 0;
		  static char g0245d_v296_cb[40];
		  g0245d_v296_cyc++;
		  snprintf(g0245d_v296_cb, sizeof(g0245d_v296_cb),
		      "v296 cyc %d", g0245d_v296_cyc);
		  g0245d_trace(g0245d_v296_cb); }
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v293 mr call"); }""",
        "v296: retry cycle counter",
    )
    s = sub(
        s,
        """		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v293 mr ret err", (unsigned int)err); }
		rootdevice[0] = '\\0';""",
        """		{ extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v293 mr ret err", (unsigned int)err); }
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_eb[40];
		  snprintf(g0245d_v296_eb, sizeof(g0245d_v296_eb),
		      "v296 mre e%d", err);
		  g0245d_trace(g0245d_v296_eb);
		  IOSleep(3000); }
		rootdevice[0] = '\\0';""",
        "v296: errno label + 3s rest",
    )
    write(BSDINIT, s)
    print("bsd_init.c: v296 retry-loop probes installed")
else:
    print("bsd_init.c: already v296")

# ---- mockfs_vfsops.c: header dump + every failure exit labelled ------------
s = read(VFSOPS)
if MARK not in s:
    # superblock dump (magic/version/count + offsets)
    s = sub(
        s,
        """	if (!rvalue) {
		memcpy(&header, (void *)buf_dataptr(header_buf), sizeof(header));
	}""",
        """	if (!rvalue) {
		memcpy(&header, (void *)buf_dataptr(header_buf), sizeof(header));
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_mb[80];
		  snprintf(g0245d_v296_mb, sizeof(g0245d_v296_mb),
		      "v296 mg %.8s v%u c%u",
		      (const char *)header.magic,
		      (unsigned int)header.version,
		      (unsigned int)header.count);
		  g0245d_trace(g0245d_v296_mb); }
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_hb[96];
		  snprintf(g0245d_v296_hb, sizeof(g0245d_v296_hb),
		      "v296 hd lo%llu ls%llu to%llu ts%llu",
		      (unsigned long long)header.launch_offset,
		      (unsigned long long)header.launch_size,
		      (unsigned long long)header.test_offset,
		      (unsigned long long)header.test_size);
		  g0245d_trace(g0245d_v296_hb); }
	}""",
        "v296: superblock dump",
    )
    # bread failure exit
    s = sub(
        s,
        """	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v294 bread ret", (unsigned int)rvalue); }""",
        """	{ extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v294 bread ret", (unsigned int)rvalue); }
	if (rvalue) {
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_bb[40];
		  snprintf(g0245d_v296_bb, sizeof(g0245d_v296_bb),
		      "v296 brderr e%d", rvalue);
		  g0245d_trace(g0245d_v296_bb); }
	}""",
        "v296: bread failure exit",
    )
    # fsnode_create ENOMEM exit
    s = sub(
        s,
        """	if (!root_fsnode || !dev_fsnode || !file_fsnode) {
		rvalue = ENOMEM;
		goto done;
	}""",
        """	if (!root_fsnode || !dev_fsnode || !file_fsnode) {
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v296 nodesbad"); }
		rvalue = ENOMEM;
		goto done;
	}""",
        "v296: fsnode ENOMEM exit",
    )
    # header-check EINVAL exit
    s = sub(
        s,
        """		    header.test_size > bytes - header.test_offset) {
			rvalue = EINVAL;
			goto done;
		}""",
        """		    header.test_size > bytes - header.test_offset) {
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v296 imgbad"); }
			rvalue = EINVAL;
			goto done;
		}""",
        "v296: header-check EINVAL exit",
    )
    # adopt failure exits (1=dev, 2=file, 3=test)
    s = sub(
        s,
        """	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, dev_fsnode))) {
		goto done;
	}""",
        """	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, dev_fsnode))) {
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_a1[40];
		  snprintf(g0245d_v296_a1, sizeof(g0245d_v296_a1),
		      "v296 ad1 e%d", rvalue);
		  g0245d_trace(g0245d_v296_a1); }
		goto done;
	}""",
        "v296: adopt dev exit",
    )
    s = sub(
        s,
        """	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, file_fsnode))) {
		goto done;
	}""",
        """	if ((rvalue = mockfs_fsnode_adopt(root_fsnode, file_fsnode))) {
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_a2[40];
		  snprintf(g0245d_v296_a2, sizeof(g0245d_v296_a2),
		      "v296 ad2 e%d", rvalue);
		  g0245d_trace(g0245d_v296_a2); }
		goto done;
	}""",
        "v296: adopt file exit",
    )
    s = sub(
        s,
        """	if (test_image && (rvalue = mockfs_fsnode_adopt(root_fsnode, test_fsnode))) {
		goto done;
	}""",
        """	if (test_image && (rvalue = mockfs_fsnode_adopt(root_fsnode, test_fsnode))) {
		{ extern void g0245d_trace(const char *);
		  static char g0245d_v296_a3[40];
		  snprintf(g0245d_v296_a3, sizeof(g0245d_v296_a3),
		      "v296 ad3 e%d", rvalue);
		  g0245d_trace(g0245d_v296_a3); }
		goto done;
	}""",
        "v296: adopt test exit",
    )
    write(VFSOPS, s)
    print("mockfs_vfsops.c: v296 failure-exit probes installed")
else:
    print("mockfs_vfsops.c: already v296")

print("v296 done (formatted probes; one IOSleep(3000) in the retry path)")
