#!/usr/bin/env python3
"""g0245d v289 -- mockfs memory root: exec /sbin/launchd = userland!

With timed waits working (v288 EOI fix), the boot parks in IOFindBSDRoot's
IOMedia wait -- but no storage driver exists.  This version takes the
shortest path to userland instead:

  * XNU carries a complete memory filesystem designed for EXACTLY this:
    bsd/miscfs/mockfs.  Its lookup maps /sbin and /usr/lib to the root,
    /dev to the devfs mountpoint, "launchd" to the executable file, and
    mockfs_mountroot has a legacy path where THE WHOLE ROOT DEVICE is the
    /sbin/launchd Mach-O image (mockfs_test_header magic "N4KROOT" not
    required).  vfs_conf.c registers it as the LAST mountroot candidate.

  * HOW mockfs IS ENABLED (official switch, do NOT hand-edit sources):
    CONFIG_XNU_SOURCE_MOCKFS=y in the device defconfig (g0245d_defconfig
    line 15) -> unixnu runs archive-07-build-mockfs-fixture.py producing
    build/mockfs-fixture/libmockfs_fixture.a -> build-xnu-4k-baseline.sh
    adds -Wl,-force_load,<that .a> to the kernel link, and compiles
    vfs_conf.o with -DMOCKFS=1 (EXTRA_MAKE_ARGS).  That is the whole chain.
    The equivalent key must be present in the generated work/.config
    (defconfig merges: os profile ios.config has "# ... is not set", the
    device defconfig applies LAST with =y, so parse_config ends on True).
    DO NOT edit bsd/conf/files or #if MOCKFS by hand: XNU's config parser
    requires exactly two tokens per files line ("path standard" /
    "path optional <opt>"); a trailing comment is a syntax error, and a
    second compiled copy of mockfs would collide with the -force_load
    archive anyway.

  * IOFindBSDRoot: replace the DT-RAMDisk block.  Allocate 2 pages
    (KMA_ZERO), copy a hand-crafted minimal arm64 Mach-O (LC_SEGMENT_64
    __TEXT @0x100000 + LC_UNIXTHREAD entry 0x101000; code = exit(42)),
    mdevadd it (virtual, same call shape as the DT RAMDisk path), then
    rdBootVar = "md0" so the existing `md?` branch roots on it.

  * Expected boot path: setconf -> BSD root: md0 -> vfs_mountroot tries
    every FS -> mockfs_mountroot mounts the memory image -> VFS_ROOT ->
    root vnode -> bsd_init tail -> PID1 execs /sbin/launchd -> exit(42)
    -> kernel panics ABOUT the exit -> 42 ON THE SCREEN = userland
    round-trip proven.
"""
import os
import struct
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")

MARK = "g0245d v289"


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


# --- build the launchd image ---------------------------------------------
code = bytes.fromhex("4005 8052 2000 80d2 010010d4".replace(" ", ""))
seg = struct.pack("<II", 0x19, 72) + b"__TEXT".ljust(16, b"\0")
seg += struct.pack("<QQQQIIII", 0x100000, 0x2000, 0, 0x2000, 7, 5, 0, 0)
unix = struct.pack("<IIII", 0x5, 8 + 66 * 4, 6, 66)
regs = [0] * 33
regs[31] = 0x102000            # sp
regs[32] = 0x101000            # pc
unix += b"".join(struct.pack("<Q", v) for v in regs)
hdr = struct.pack("<IIIIIII", 0xFEEDFACF, 0x0100000C, 2, 2,
                  len(seg) + len(unix), 0x1, 0)
assert len(hdr) == 28 and len(seg) == 72 and len(unix) == 280

hdr_hex = ",\n    ".join(
    ",".join("0x%02X" % b for b in hdr[i:i + 16])
    for i in range(0, len(hdr), 16))
code_hex = ",".join("0x%02X" % b for b in code)

# --- IOKitBSDInit.cpp: memory root ---------------------------------------
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """extern "C" unsigned int g0245d_rb_cntfrq;

kern_return_t

IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        """extern "C" unsigned int g0245d_rb_cntfrq;

/* g0245d v289: minimal arm64 Mach-O, entry _start: exit(42).
 * __TEXT @0x100000 (vmsize 0x2000), LC_UNIXTHREAD pc=0x101000, sp=0x102000.
 * Code (12 bytes @ file offset 0x1000): mov w0,#42; mov x16,#1; svc #0x80.
 * Copied into a KMA_ZERO memory disk by IOFindBSDRoot below. */
static const unsigned char g0245d_launchd_hdr[28] = {
    """ + hdr_hex + """
};
static const unsigned char g0245d_launchd_code[12] = { """ + code_hex + """ };
#define G0245D_LAUNCHD_HDR_SIZE 28u
#define G0245D_LAUNCHD_CODE_OFF 0x1000u

kern_return_t

IOFindBSDRoot( char * rootName, unsigned int rootNameSize,""",
        "fbr: launchd image",
    )
    s = sub(
        s,
        """	if (!didRam) {                                                                                           /* Have we already build this ram disk? */
		didRam = 1;                                                                                             /* Remember we did this */
		if ((regEntry = IORegistryEntry::fromPath( "/chosen/memory-map", gIODTPlane ))) {        /* Find the map node */
			data = (OSData *)regEntry->getProperty("RAMDisk");      /* Find the ram disk, if there */
			if (data) {                                                                                      /* We found one */
				uintptr_t *ramdParms;
				ramdParms = (uintptr_t *)data->getBytesNoCopy();        /* Point to the ram disk base and size */
#if __LP64__
#define MAX_PHYS_RAM    (((uint64_t)UINT_MAX) << 12)
				if (ramdParms[1] > MAX_PHYS_RAM) {
					panic("ramdisk params");
				}
#endif /* __LP64__ */
				(void)mdevadd(-1, ml_static_ptovirt(ramdParms[0]) >> 12, (unsigned int) (ramdParms[1] >> 12), 0);        /* Initialize it and pass back the device number */
			}
			regEntry->release();                                                            /* Toss the entry */
		}
	}""",
        """	if (!didRam) {
		didRam = 1;
		/* g0245d v289: build a memory disk holding a minimal arm64
		 * Mach-O (exit(42)) and root on it as md0.  mockfs (last
		 * mountroot candidate) treats the whole root device as
		 * /sbin/launchd, so PID1 execs our image.  No storage
		 * driver needed. */
		{
			kern_return_t g0245d_kr;
			vm_offset_t g0245d_va = 0;
			g0245d_kr = kernel_memory_allocate(kernel_map,
			    &g0245d_va, 0x2000, 0,
			    KMA_KOBJECT | KMA_ZERO | KMA_NOPAGEWAIT,
			    VM_KERN_MEMORY_OSFMK);
			if (g0245d_kr == KERN_SUCCESS) {
				memcpy((void *)(uintptr_t)g0245d_va,
				    g0245d_launchd_hdr, G0245D_LAUNCHD_HDR_SIZE);
				memcpy((void *)(uintptr_t)(g0245d_va +
				    G0245D_LAUNCHD_CODE_OFF),
				    g0245d_launchd_code,
				    sizeof(g0245d_launchd_code));
				{
					dev_t g0245d_dev = mdevadd(-1,
					    g0245d_va >> 12, 2, 0);
					g0245d_trace_u("v289 memdisk",
					    (unsigned int)g0245d_dev);
				}
				strlcpy(rdBootVar, "md0", kMaxBootVar);
				{ extern void g0245d_trace(const char *);
				  g0245d_trace("v289 rd md0"); }
			} else {
				{ extern void g0245d_trace_u(const char *,
				    unsigned int);
				  g0245d_trace_u("v289 memdisk FAIL",
				      (unsigned int)g0245d_kr); }
			}
		}
	}""",
        "fbr: memory root",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: memory root added")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v289 done (mockfs enabled by CONFIG_XNU_SOURCE_MOCKFS=y, not by this script)")
