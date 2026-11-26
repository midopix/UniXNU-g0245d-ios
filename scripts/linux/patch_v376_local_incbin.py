#!/usr/bin/env python3
"""g0245d v376 -- replace the synthetic exit(42) fixture with real 20F66 launchd/dyld.

The injected RAM disk is an N4KROOT v1 two-file container built by
scripts/build_n4kroot_v376.py:
  file 0 (launch_offset) -> /sbin/launchd
  file 1 (test_offset)   -> /usr/lib/dyld

The 1.4 MB image is linked into the kernel via a top-level asm .incbin
(no C byte array -> no 91k-line source bloat).  The C++ side references
it as `extern "C" const unsigned char g0245d_v376_root[]` (Mach-O ARM64
prepends '_', so the asm label is `_g0245d_v376_root`).

Inputs are verified by SHA-256 against the private-repo manifest before
the patch is applied; the script refuses substitutes.  Idempotent.
"""
import hashlib
import os
import struct
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("patch_v376: set XNU_WORK")
IMG = Path(os.environ.get("G0245D_V376_ROOT_IMG",
    "/mnt/d/G0245D/assets/n4kroot-v2.img"))
EXPECT_IMG = "822a15ef9dbb6ae2fb86c037d0336442bc60415d1da50424f5446a41b09731d1"
EXPECT_L = "4c61512d19b9a55a6ddad27e23b88fc5008fbf77d0c0b5e6bdd7c7d90cef3e06"
EXPECT_D = "a453aa234fc9bd440dc4e55bd2e18f9a7eb2bc3fd7ef319d8714a664bc55bf5c"

P = Path(W) / "iokit" / "bsddev" / "IOKitBSDInit.cpp"
s = P.read_text(encoding="utf-8", errors="replace")
if "g0245d_v376_root[]" in s:
    print("patch_v376: already applied -- skip")
    sys.exit(0)

if not IMG.is_file():
    sys.exit(f"patch_v376: missing root image: {IMG}")
image = IMG.read_bytes()
hi = hashlib.sha256(image).hexdigest()
if hi != EXPECT_IMG:
    sys.exit(f"patch_v376: root image sha256 mismatch: {hi}")

# Parse + re-verify the N4KROOT v2 header, path table and embedded Mach-O.
magic, version, count, hdr_size, flags, total = struct.unpack_from("<8sIIIIQ", image, 0)
if magic != b"N4KROOT\0" or version != 2 or count < 1 or hdr_size != 4096 or total != len(image):
    sys.exit(f"patch_v376: bad N4KROOT v2 header (v={version} n={count})")
want = {"/sbin/launchd": EXPECT_L, "/usr/lib/dyld": EXPECT_D}
seen = {}
for i in range(count):
    e = 32 + i * 120
    path = image[e:e+96].split(b"\0", 1)[0].decode()
    off, size, typ, res = struct.unpack_from("<QQII", image, e+96)
    if off < 4096 or off % 4096 or size == 0 or off+size > len(image) or res != 0:
        sys.exit(f"patch_v376: bad v2 entry {path}")
    data = image[off:off+size]
    if path in want:
        if hashlib.sha256(data).hexdigest() != want[path]:
            sys.exit(f"patch_v376: embedded {path} sha256 mismatch")
        if struct.unpack_from("<I", data, 0)[0] != 0xfeedfacf or \
           struct.unpack_from("<II", data, 4) != (0x0100000c, 0):
            sys.exit(f"patch_v376: {path} is not ARM64 All Mach-O")
        seen[path] = True
for path in want:
    if path not in seen:
        sys.exit(f"patch_v376: missing required v2 entry {path}")

root_size = len(image)
pages = (root_size + 4095) // 4096
img_path = str(IMG).replace("\\", "/")

# Top-level asm block: define the symbol, then include the raw image.
inject = f"""/* g0245d v376: real iOS 16.5 / 20F66 launchd + dyld in an N4KROOT v2 root.
 * launchd sha256 {EXPECT_L}
 * dyld    sha256 {EXPECT_D}
 * image   sha256 {hi} ({root_size} bytes, {pages} pages)
 * The 1.4 MB bytes live in a __TEXT section via .incbin; no C array. */
extern "C" const unsigned char g0245d_v376_root[];
asm(
    ".section __TEXT,__g0245root,regular,no_dead_strip\\n"
    ".align 12\\n"
    ".globl _g0245d_v376_root\\n"
    "_g0245d_v376_root:\\n"
    ".incbin \\"{img_path}\\"\\n"
    ".previous\\n"
);
#define G0245D_V376_ROOT_SIZE {root_size}u
#define G0245D_V376_ROOT_PAGES {pages}u

"""

anchor = "/* g0245d v330: minimal but *valid* arm64 Mach-O, entry _start: exit(42)."
if s.count(anchor) != 1:
    sys.exit(f"patch_v376: anchor count={s.count(anchor)} (want 1)")
s = s.replace(anchor, inject + anchor, 1)

old = """\t\t\tg0245d_raw = (vm_offset_t)(uintptr_t)
\t\t\t    g0245d_perm_pool_alloc(0x3000);"""
new = """\t\t\tg0245d_raw = (vm_offset_t)(uintptr_t)
\t\t\t    g0245d_perm_pool_alloc(G0245D_V376_ROOT_SIZE + 0x1000);"""
if s.count(old) != 1:
    sys.exit(f"patch_v376: perm-pool anchor count={s.count(old)} (want 1)")
s = s.replace(old, new, 1)

old = """\t\t\t\tmemcpy((void *)(uintptr_t)g0245d_va,
\t\t\t\t    g0245d_launchd_hdr, G0245D_LAUNCHD_HDR_SIZE);
\t\t\t\tmemcpy((void *)(uintptr_t)(g0245d_va +
\t\t\t\t    G0245D_LAUNCHD_CODE_OFF),
\t\t\t\t    g0245d_launchd_code,
\t\t\t\t    sizeof(g0245d_launchd_code));
\t\t\t\t{
\t\t\t\t\tdev_t g0245d_dev = mdevadd(-1,
\t\t\t\t\t    g0245d_va >> 12, 2, 0);
\t\t\t\t\tg0245d_trace_u("v289 memdisk",
\t\t\t\t\t    (unsigned int)g0245d_dev);
\t\t\t\t}"""
new = """\t\t\t\tmemcpy((void *)(uintptr_t)g0245d_va,
\t\t\t\t    g0245d_v376_root, G0245D_V376_ROOT_SIZE);
\t\t\t\t{
\t\t\t\t\tdev_t g0245d_dev = mdevadd(-1,
\t\t\t\t\t    g0245d_va >> 12,
\t\t\t\t\t    G0245D_V376_ROOT_PAGES, 0);
\t\t\t\t\tg0245d_trace_u("v376 memdisk",
\t\t\t\t\t    (unsigned int)g0245d_dev);
\t\t\t\t\tg0245d_trace_u("v376 root bytes",
\t\t\t\t\t    G0245D_V376_ROOT_SIZE);
\t\t\t\t}"""
if s.count(old) != 1:
    sys.exit(f"patch_v376: memcpy/mdevadd anchor count={s.count(old)} (want 1)")
s = s.replace(old, new, 1)

P.write_text(s, encoding="utf-8")
print(f"patch_v376: real-root injection installed ({root_size} bytes / {pages} pages, incbin)")
print("patch_v376: done")
