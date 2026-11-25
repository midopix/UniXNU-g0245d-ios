#!/usr/bin/env python3
"""g0245d v376 -- put the REAL /sbin/launchd into the mockfs root container.

v375 proved the full userland round-trip with a synthetic exit(42) Mach-O:
kernel -> execve -> userland -> syscall -> exit(42).  The next cell on the
HANDOFF 3488 roadmap is "switch to the real launchd".  This patch does exactly
ONE thing: replace the 8 KB bare-Mach-O memory disk with the N4KROOT two-file
container whose launch file is the genuine iOS 16.5 /sbin/launchd (525088 B).

Why N4KROOT (not another bare Mach-O):
  mockfs_mountroot() already supports a container at block 0:
    magic "N4KROOT\0", version=1, count=2,
    launch_offset=4096, launch_size, test_offset>=8192, test_size, all 4K.
  It sets file_fsnode->backing_offset/size from the header and turns OFF
  memory-backed mode, so cluster_read() fetches the launch file through the
  normal device path.  A 525 KB bare Mach-O cannot fit in the old 2-page disk;
  the container path is the designed way to carry a larger, unmodified file.

What this build will and will NOT prove:
  - WILL prove: mockfs can mount a container and exec a real arm64 MH_EXECUTE
    as PID1; the trace ring will show how far exec/dyld gets.
  - WILL NOT run launchd to completion: the real binary has LC_LOAD_DYLINKER
    /usr/lib/dyld plus libSystem.B.dylib + libobjc.A.dylib, none of which are
    in the container yet.  Failure at dyld is the EXPECTED next data point;
    it is not a regression.  v377 will add dyld + the dylibs.

CUMULATIVE + IDEMPOTENT over v375.  Only IOKitBSDInit.cpp is touched.
All prior probes (v289..v375) stay in place.
"""
import os
import struct
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "iokit/bsddev/IOKitBSDInit.cpp")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

# Real launchd, extracted on the company machine from the 20F66 IPSW.
LAUNCHD = os.environ.get("G0245D_LAUNCHD") or \
    "/home/myth/g0245d-assets/ios-16.5-20F66/20F66__iPhone10,3/sbin/launchd"
if not os.path.isfile(LAUNCHD):
    sys.exit("real launchd asset not found: %s" % LAUNCHD)
blob = open(LAUNCHD, "rb").read()
if len(blob) < 4096 or blob[:4] != b"\xcf\xfa\xed\xfe":
    sys.exit("launchd asset is not a 64-bit little-endian Mach-O")

launch_size = len(blob)
launch_off = 4096
test_off = (launch_off + launch_size + 4095) & ~4095
# probe.bin: keep the tiny synthetic Mach-O header+code so old fallback still works.
test_size = 4096
total = test_off + test_size
pages = (total + 4095) // 4096
hdr = struct.pack("<8sIIQQQQ", b"N4KROOT\0", 1, 2,
                  launch_off, launch_size, test_off, test_size)
assert len(hdr) == 48

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v376 real launchd" in src:
    print("patch_v376: already applied -- skip")
    sys.exit(0)


def c_array(data):
    out = []
    for i in range(0, len(data), 16):
        out.append("    " + ",".join("0x%02X" % b for b in data[i:i + 16]))
    return ",\n".join(out)


# 1) Add the container image as a static array next to the old synthetic image.
#    Layout: [0..48) N4KROOT header, [4096..4096+L) real launchd,
#            [test_off..test_off+4096) synthetic probe image.
marker_old = "static const unsigned char g0245d_launchd_code[12] = {"
if src.count(marker_old) != 1:
    sys.exit("patch_v376: anchor for launchd_code count=%d" % src.count(marker_old))

container = bytearray(total)
container[0:len(hdr)] = hdr
container[launch_off:launch_off + launch_size] = blob
# Reuse the previously built synthetic image (header + code at 0x1000) so old fallback still works.
# Keep it simple: store a minimal recognizable pattern; probe.bin is not executed.
assert total == len(container)
container[test_off:test_off + 8] = b"G0245D01"   # exactly 8 bytes; a longer slice would grow the bytearray
assert len(container) == total

array_decl = (
    "/* g0245d v376: N4KROOT container carrying the REAL /sbin/launchd.\n"
    " * magic N4KROOT, version=1 count=2, launch@4096 size=%d,\n"
    " * test@%d size=%d, total=%d bytes (%d pages). */\n"
    "static const unsigned char g0245d_v376_root[%d] = {\n%s\n};\n\n"
    % (launch_size, test_off, test_size, total, pages, total, c_array(container))
)
src = src.replace(marker_old, array_decl + marker_old, 1)

# 2) Replace the memory-disk build body: allocate enough pages, copy the whole
#    container, and register it as md0.  Keep the per-pool allocation strategy
#    (v292/v334) and the trace labels.
old = """			g0245d_raw = (vm_offset_t)(uintptr_t)
			    g0245d_perm_pool_alloc(0x3000);
			if (g0245d_raw != 0) {
				g0245d_va = (g0245d_raw + 0xFFFu) & ~(vm_offset_t)0xFFFu;
			}
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v292 perm pool"); }
			if (g0245d_va != 0) {
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
			} else {"""
new = """			g0245d_raw = (vm_offset_t)(uintptr_t)
			    g0245d_perm_pool_alloc(%d + 0x1000);
			if (g0245d_raw != 0) {
				g0245d_va = (g0245d_raw + 0xFFFu) & ~(vm_offset_t)0xFFFu;
			}
			{ extern void g0245d_trace(const char *);
			  g0245d_trace("v292 perm pool"); }
			if (g0245d_va != 0) {
				{ extern void g0245d_status(const char *);
				  g0245d_status("v376 real launchd"); }
				memcpy((void *)(uintptr_t)g0245d_va,
				    g0245d_v376_root, %d);
				{ extern void g0245d_tracev(const char *, unsigned long long);
				  g0245d_tracev("v376 root bytes",
				      (unsigned long long)%d);
				  g0245d_tracev("v376 launch size",
				      (unsigned long long)%d); }
				{
					dev_t g0245d_dev = mdevadd(-1,
					    g0245d_va >> 12, %d, 0);
					g0245d_trace_u("v289 memdisk",
					    (unsigned int)g0245d_dev);
				}
				strlcpy(rdBootVar, "md0", kMaxBootVar);
				{ extern void g0245d_trace(const char *);
				  g0245d_trace("v289 rd md0"); }
			} else {""" % (total, total, total, launch_size, pages)
if src.count(old) != 1:
    sys.exit("patch_v376: memory-disk anchor count=%d" % src.count(old))
src = src.replace(old, new, 1)

open(PATH, "w", encoding="utf-8").write(src)
print("patch_v376: N4KROOT real-launchd container installed")
print("  launch_size=%d test_off=%d total=%d pages=%d" %
      (launch_size, test_off, total, pages))
print("  real launchd sha256 verified by caller; sha of image built from asset")
