#!/usr/bin/env python3
"""g0245d v264 -- back off the mem_size clamp, only lift sane_size.

v263 forced args->memSize up to 1536 MB and the boot went BACKWARDS: the panel
now shows seq 1635 with status ">locks", while v262 reached 8200+ inside
mbinit().  The printed inputs explain it:

    1628 v263 boot memSize MB 56
    1629 v263 gPhysBase 0x95804000        <- kernel sits at 2.3 GB
    1630 v263 memSize forced MB 1536      <- physmap pushed to ~3.8 GB

mem_size drives the bootstrap physmap and its page tables; pushing it from
56 MB to 1536 MB makes early VM setup fail before it ever reaches the stages
that used to work.  The clamp was too aggressive.

v264 keeps mem_size at whatever the shim reported (so the physmap covers only
memory we know exists) and instead lifts sane_size, which is only an
accounting value used to derive defaults -- pgz slots, desiredvnodes, mbuf
cluster counts.  It also gives nmbclusters a floor, since NMBCLUSTERS on this
configuration is 128, which makes maxslabgrp round to zero.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AVM = os.path.join(WORK, "osfmk/arm64/arm_vm_init.c")
MBUF = os.path.join(WORK, "bsd/kern/uipc_mbuf.c")

MARK = "g0245d v264"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what):
    n = src.count(old)
    if n != 1:
        sys.exit("%s: anchor found %d times" % (what, n))
    return src.replace(old, new)


# ------------------------------------------------------------ arm_vm_init.c
s = read(AVM)
if MARK not in s:
    s = sub(
        s,
        """	if (mem_size < (256ULL * 1024 * 1024)) {
		uint64_t forced = 0x100000000ULL - (uint64_t)gPhysBase;
		if (forced > (1536ULL * 1024 * 1024)) {
			forced = 1536ULL * 1024 * 1024;
		}
		if (forced < (512ULL * 1024 * 1024)) {
			forced = 512ULL * 1024 * 1024;
		}
		g0245d_trace_u("v263 memSize forced MB", (unsigned int)(forced >> 20));
		mem_size = forced;
		gPhysSize = forced;
		args->memSize = forced;
		args->memSizeActual = forced;
	}""",
        """	/* g0245d v264: v263 forced mem_size up to 1536 MB and the boot moved
	 * BACKWARDS (seq 1635, status >locks, versus 8200+ before), because
	 * mem_size sizes the bootstrap physmap and its page tables -- and the
	 * kernel itself sits at gPhysBase 0x95804000 (2.3 GB).  Do not touch
	 * mem_size.  sane_size alone drives the derived defaults.
	 */
	g0245d_trace_u("v264 memSize kept MB", (unsigned int)(mem_size >> 20));""",
        "arm_vm_init: revert mem clamp",
    )

    s = sub(
        s,
        """	sane_size = mem_size - (avail_start - gPhysBase);
	max_mem = mem_size;""",
        """	sane_size = mem_size - (avail_start - gPhysBase);
	if (sane_size < (512ULL * 1024 * 1024)) {
		/* Only the accounting value: pgz slots, desiredvnodes and the
		 * mbuf cluster count scale from this.  Leaving it at 38 MB made
		 * every one of them collapse while the physmap stayed small.
		 */
		g0245d_trace_u("v264 sane_size raised MB", 512);
		sane_size = 512ULL * 1024 * 1024;
	}
	max_mem = mem_size;""",
        "arm_vm_init: raise sane_size",
    )
    write(AVM, s)
    print("arm_vm_init: v264 changes applied")
else:
    print("arm_vm_init: already patched")

# ------------------------------------------------------------- uipc_mbuf.c
s = read(MBUF)
if MARK not in s:
    s = sub(
        s,
        """	if (nmbclusters == 0) {
		nmbclusters = NMBCLUSTERS;
	}""",
        """	if (nmbclusters == 0) {
		nmbclusters = NMBCLUSTERS;
	}
	/* g0245d v264: NMBCLUSTERS is 128 on this configuration, which makes
	 * maxslabgrp round to zero.  Give it a floor; clusters are allocated
	 * lazily per slab, so this only reserves the accounting structure.
	 */
	if (nmbclusters < 1024) {
		g0245d_trace_u("v264 nmbclusters floor from", nmbclusters);
		nmbclusters = 1024;
	}""",
        "uipc_mbuf: cluster floor",
    )
    write(MBUF, s)
    print("uipc_mbuf: v264 changes applied")
else:
    print("uipc_mbuf: already patched")

print("v264 patch applied")
