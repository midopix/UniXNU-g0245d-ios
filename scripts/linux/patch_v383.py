#!/usr/bin/env python3
"""g0245d v383 -- put the REAL /usr/lib/dyld into the N4KROOT container.

v382 photo (2026-11-26 14:31) finally shows the loader verdict:

    v381 lret=2 @kern_exec.c:1336      -> LOAD_BADMACHO
    v378 pm0  v381 lret=2 @kern_exec.c

LOAD_BADMACHO (bsd/kern/mach_loader.h:116).  The main binary is fine: /sbin/launchd
resolved through mockfs and its cs_blob went through (v379 guard).  What is NOT a
Mach-O is the interpreter: launchd's LC_LOAD_DYLINKER is "/usr/lib/dyld", and
mockfs's "dyld" name maps to MOCKFS_TEST_FILE -- the 4 KB synthetic blob whose
first bytes are "G0245D01".

Real dyld obtained WITHOUT the truncated IPSW: the 20F66 dyld shared cache carries
/usr/lib/dyld as image #236 (ipsw dyld info --dylibs), and

    ipsw dyld extract dyld_shared_cache_arm64 /usr/lib/dyld -o usr-lib

produces an 867,928-byte Mach-O: magic feedfacf, cputype 0x100000c, filetype 7
(MH_DYLINKER), segments __TEXT/__DATA_CONST/__DATA/__DATA_DIRTY/__LINKEDIT at the
cache addresses.

ONE嫌疑点: the container's second node must BE that dyld instead of the 4 KB probe
blob.  Node layout (N4KROOT, count=2):

    launch@4096   525088 bytes   real /sbin/launchd   (unchanged)
    test@532480   867928 bytes   real /usr/lib/dyld   (was 4096 bytes "G0245D01")
    total 1,400,408 bytes = 342 pages, from the 8 MB permanent pool

mockfs_blockmap adds fsnode->backing_offset, so the MOCKFS_TEST_FILE node reads the
dyld straight out of the md0 container; no mockfs code change needed.

CUMULATIVE + IDEMPOTENT over v382.  Only iokit/bsddev/IOKitBSDInit.cpp is touched
(the embedded container array and its four numeric constants).
"""
import os
import re
import struct
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "iokit", "bsddev", "IOKitBSDInit.cpp")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

DYLD = os.environ.get("G0245D_DYLD",
                      "/home/myth/g0245d-assets/ios-16.5-20F66/usr-lib/dyld")
DYLD_SHA = "82c650c5cabfa430aaa69495e260ccc07996f88ad56065d958952c3c4acfd931"
LAUNCHD = os.environ.get("G0245D_LAUNCHD",
                         "/home/myth/g0245d-assets/ios-16.5-20F66/20F66__iPhone10,3/sbin/launchd")
LAUNCHD_SHA = "4c61512d19b9a55a6ddad27e23b88fc5008fbf77d0c0b5e6bdd7c7d90cef3e06"

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v383 real dyld" in src:
    print("patch_v383: already applied -- skip")
    sys.exit(0)

import hashlib


def load(path, expect, what):
    if not os.path.isfile(path):
        sys.exit("patch_v383: %s not found: %s" % (what, path))
    data = open(path, "rb").read()
    got = hashlib.sha256(data).hexdigest()
    if got != expect:
        sys.exit("patch_v383: %s sha256 mismatch %s" % (what, got))
    return data


launchd = load(LAUNCHD, LAUNCHD_SHA, "launchd")
dyld = load(DYLD, DYLD_SHA, "dyld")
if dyld[:4] != b"\xcf\xfa\xed\xfe":
    sys.exit("patch_v383: dyld is not a 64-bit Mach-O")

launch_off = 4096
test_off = (launch_off + len(launchd) + 4095) & ~4095
total = test_off + len(dyld)
pages = (total + 4095) // 4096
hdr = struct.pack("<8sIIQQQQ", b"N4KROOT\0", 1, 2,
                  launch_off, len(launchd), test_off, len(dyld))
assert len(hdr) == 48

container = bytearray(total)
container[0:48] = hdr
container[launch_off:launch_off + len(launchd)] = launchd
container[test_off:test_off + len(dyld)] = dyld
assert len(container) == total


def c_array(data):
    out = []
    for i in range(0, len(data), 16):
        out.append("    " + ",".join("0x%02X" % b for b in data[i:i + 16]))
    return ",\n".join(out)


# --- 1. replace the embedded container -------------------------------------
pat = re.compile(r"/\* g0245d v376: N4KROOT container.*?\nstatic const unsigned char g0245d_v376_root\[\d+\] = \{.*?\n\};\n",
                 re.S)
m = pat.search(src)
if not m:
    sys.exit("patch_v383: container array not found")
old_block = m.group(0)
old_total = int(re.search(r"g0245d_v376_root\[(\d+)\]", old_block).group(1))

new_block = (
    "/* g0245d v383: N4KROOT container carrying the REAL /sbin/launchd and the\n"
    " * REAL /usr/lib/dyld (extracted from the 20F66 dyld shared cache, image 236;\n"
    " * filetype 7 MH_DYLINKER, 867928 bytes).  magic N4KROOT, version=1 count=2,\n"
    " * launch@%d size=%d, test@%d size=%d, total=%d bytes (%d pages). */\n"
    "static const unsigned char g0245d_v376_root[%d] = {\n%s\n};\n"
    % (launch_off, len(launchd), test_off, len(dyld), total, pages,
       total, c_array(container))
)
src = src[:m.start()] + new_block + src[m.end():]
print("patch_v383: container rebuilt %d -> %d bytes (%d pages), dyld %d bytes"
      % (old_total, total, pages, len(dyld)))

# --- 2. numeric constants at the call site ---------------------------------
subs = [
    ("g0245d_perm_pool_alloc(%d + 0x1000)" % old_total,
     "g0245d_perm_pool_alloc(%d + 0x1000)" % total),
    ("g0245d_v376_root, %d);" % old_total,
     "g0245d_v376_root, %d);" % total),
    ('g0245d_tracev("v376 root bytes",\n\t\t\t\t      (unsigned long long)%d);' % old_total,
     'g0245d_tracev("v376 root bytes",\n\t\t\t\t      (unsigned long long)%d);' % total),
    ("g0245d_va >> 12, %d, 0);" % (old_total // 4096),
     "g0245d_va >> 12, %d, 0);" % pages),
]
for old, new in subs:
    if old not in src:
        sys.exit("patch_v383: constant anchor missing: %r" % old[:60])
    src = src.replace(old, new, 1)

# --- 3. probes: say which container went in --------------------------------
old_probe = ('\t\t\t\t{ extern void g0245d_status(const char *);\n'
             '\t\t\t\t  g0245d_status("v376 real launchd"); }\n')
if old_probe not in src:
    sys.exit("patch_v383: status anchor missing")
new_probe = ('\t\t\t\t{ extern void g0245d_status(const char *);\n'
             '\t\t\t\t  g0245d_status("v383 real dyld"); }\n'
             '\t\t\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
             '\t\t\t\t  g0245d_tracev("v383 dyld bytes",\n'
             '\t\t\t\t      (unsigned long long)%d); }\n' % len(dyld))
src = src.replace(old_probe, new_probe, 1)

open(PATH, "w", encoding="utf-8").write(src)
print("patch_v383: launcher container now serves launchd + real dyld")
