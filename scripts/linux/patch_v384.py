#!/usr/bin/env python3
"""g0245d v384 -- control experiment: same container as v382, padded to v383's size.

Facts so far:
  * v382 (kernel.macho 18,096,280 B) boots and panics at load_machfile (lret=2).
  * v383 (kernel.macho 18,964,632 B, container carries the real dyld) never reaches
    the kernel: the UniXNU boot app falls back to its built-in menu.
  * both payload FAT16 images are consistent (kernel chain 35,345 / 37,041 clusters,
    unixnu.toml 356 B right after it, 48,737 clusters total, enough free space), so
    the payload itself is not the difference.
  * the only remaining variable is the size of the bytes we put in kernel __DATA.

This experiment changes NOTHING behaviourally: the container is v382's
(launchd@4096 + 4 KB "G0245D01" probe blob@532480) and is then padded with zeros to
exactly v383's 1,400,408 bytes / 342 pages, so kernel.macho lands at the same size.
mockfs ignores the padding (count=2, both nodes unchanged).

Interpretation of the next photo:
  * boots to the v381 lret=2 panic  -> size is NOT the trigger; v383 issue is content
  * boot app menu again            -> kernel __DATA/size is the trigger; a real dyld
                                      cannot ride inside the kernel image.

CUMULATIVE + IDEMPOTENT over v383.  Only iokit/bsddev/IOKitBSDInit.cpp.
"""
import os
import re
import struct
import sys
import hashlib

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "iokit", "bsddev", "IOKitBSDInit.cpp")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

LAUNCHD = os.environ.get("G0245D_LAUNCHD",
                         "/home/myth/g0245d-assets/ios-16.5-20F66/20F66__iPhone10,3/sbin/launchd")
LAUNCHD_SHA = "4c61512d19b9a55a6ddad27e23b88fc5008fbf77d0c0b5e6bdd7c7d90cef3e06"
TARGET_TOTAL = 1400408          # v383's container size
TEST_SIZE = 4096

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v384 pad" in src:
    print("patch_v384: already applied -- skip")
    sys.exit(0)

data = open(LAUNCHD, "rb").read()
got = hashlib.sha256(data).hexdigest()
if got != LAUNCHD_SHA:
    sys.exit("patch_v384: launchd sha256 mismatch %s" % got)

launch_off = 4096
test_off = (launch_off + len(data) + 4095) & ~4095
total = TARGET_TOTAL
pages = (total + 4095) // 4096
hdr = struct.pack("<8sIIQQQQ", b"N4KROOT\0", 1, 2,
                  launch_off, len(data), test_off, TEST_SIZE)
container = bytearray(total)
container[0:48] = hdr
container[launch_off:launch_off + len(data)] = data
container[test_off:test_off + 8] = b"G0245D01"
assert len(container) == total


def c_array(buf):
    out = []
    for i in range(0, len(buf), 16):
        out.append("    " + ",".join("0x%02X" % b for b in buf[i:i + 16]))
    return ",\n".join(out)


pat = re.compile(r"/\* g0245d v383: N4KROOT container.*?\nstatic const unsigned char g0245d_v376_root\[\d+\] = \{.*?\n\};\n",
                 re.S)
m = pat.search(src)
if not m:
    sys.exit("patch_v384: v383 container block not found")
old_total = int(re.search(r"g0245d_v376_root\[(\d+)\]", m.group(0)).group(1))

new_block = (
    "/* g0245d v384: control experiment -- v382's container (launchd + 4 KB probe blob)\n"
    " * zero-padded to v383's total size, so kernel.macho is the same size but carries no\n"
    " * dyld.  launch@%d size=%d, test@%d size=%d, total=%d bytes (%d pages), %d pad bytes. */\n"
    "static const unsigned char g0245d_v376_root[%d] = {\n%s\n};\n"
    % (launch_off, len(data), test_off, TEST_SIZE, total, pages,
       total - test_off - TEST_SIZE, total, c_array(container))
)
src = src[:m.start()] + new_block + src[m.end():]

subs = []
if old_total != total:
    subs = [
        ("g0245d_perm_pool_alloc(%d + 0x1000)" % old_total,
         "g0245d_perm_pool_alloc(%d + 0x1000)" % total),
        ("g0245d_v376_root, %d);" % old_total,
         "g0245d_v376_root, %d);" % total),
        ('g0245d_tracev("v376 root bytes",\n\t\t\t\t      (unsigned long long)%d);' % old_total,
         'g0245d_tracev("v376 root bytes",\n\t\t\t\t      (unsigned long long)%d);' % total),
        ("g0245d_va >> 12, %d, 0);" % ((old_total + 4095) // 4096),
         "g0245d_va >> 12, %d, 0);" % pages),
    ]
for old, new in subs:
    if old not in src:
        sys.exit("patch_v384: constant anchor missing: %r" % old[:60])
    src = src.replace(old, new, 1)

src = src.replace('g0245d_status("v383 real dyld");', 'g0245d_status("v384 pad");', 1)
src = src.replace('g0245d_tracev("v383 dyld bytes",\n\t\t\t\t      (unsigned long long)867928);',
                  'g0245d_tracev("v384 pad bytes",\n\t\t\t\t      (unsigned long long)%d);' % (total - test_off - TEST_SIZE), 1)

open(PATH, "w", encoding="utf-8").write(src)
print("patch_v384: container %d -> %d bytes (%d pages), no dyld, %d pad bytes"
      % (old_total, total, pages, total - test_off - TEST_SIZE))
