#!/usr/bin/env python3
"""dump the kernel's __mod_init_func structor list, index -> symbol name

usage: structor_map.py <kernel.macho>
The v234 console probe prints the structor index, so this table turns that
index into the static constructor that was running when the machine stopped.
"""
import bisect
import struct
import subprocess
import sys

path = sys.argv[1]

# llvm-nm -n <macho>  -> "addr type name"
nm = subprocess.run(["llvm-nm", "-n", path], capture_output=True, text=True).stdout
syms = []
for line in nm.splitlines():
    q = line.split()
    if len(q) == 3:
        try:
            syms.append((int(q[0], 16), q[2]))
        except ValueError:
            pass
syms.sort()
addrs = [s[0] for s in syms]

d = open(path, "rb").read()
ncmds = struct.unpack("<I", d[16:20])[0]
off = 32
secs = []
for _ in range(ncmds):
    cmd, cmdsize = struct.unpack("<II", d[off:off + 8])
    if cmd == 0x19:  # LC_SEGMENT_64
        nsects = struct.unpack("<I", d[off + 64:off + 68])[0]
        so = off + 72
        for _j in range(nsects):
            sn = d[so:so + 16].rstrip(b"\0").decode()
            sg = d[so + 16:so + 32].rstrip(b"\0").decode()
            addr, size = struct.unpack("<QQ", d[so + 32:so + 48])
            fo = struct.unpack("<I", d[so + 48:so + 52])[0]
            secs.append((sg, sn, addr, size, fo))
            so += 80
    off += cmdsize

for sg, sn, addr, size, fo in secs:
    if sn != "__mod_init_func" or size < 8:
        continue
    n = size // 8
    print("== %s __mod_init_func  n=%d  base=0x%x" % (sg, n, addr))
    for i in range(n):
        v = struct.unpack("<Q", d[fo + i * 8:fo + i * 8 + 8])[0]
        k = bisect.bisect_right(addrs, v) - 1
        name = syms[k][1] if k >= 0 else "?"
        print("  %3d  0x%016x  %s" % (i, v, name))
