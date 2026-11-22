#!/usr/bin/env python3
"""Emit a host program that replays the kernel's startup-entry sort.

The kernel calls qsort(startup_entries, n, ..., startup_entry_cmp) once, so the
runtime order of the startup routines is fully determined by (a) the on-disk
order of __init_entry_set, (b) the comparator, and (c) bsd/kern/qsort.c.  We
have all three, so we can reproduce the order exactly and turn a boot index
printed by v242 back into a function name without touching the device.
"""
import bisect
import os
import struct
import subprocess
import sys

KERNEL = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/kernel/kernel.macho")
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ent.c"

d = open(KERNEL, "rb").read()
ncmds = struct.unpack("<I", d[16:20])[0]
off = 32
sections = []
for _ in range(ncmds):
    cmd, sz = struct.unpack("<II", d[off:off + 8])
    if cmd == 0x19:
        seg = d[off + 8:off + 24].rstrip(b"\0").decode()
        nsects = struct.unpack("<I", d[off + 64:off + 68])[0]
        so = off + 72
        for _j in range(nsects):
            sn = d[so:so + 16].rstrip(b"\0").decode()
            addr, size = struct.unpack("<QQ", d[so + 32:so + 48])
            fo = struct.unpack("<I", d[so + 48:so + 52])[0]
            sections.append((seg, sn, addr, size, fo))
            so += 80
    off += sz

sec = [s for s in sections if s[1] == "__init_entry_set"][0]
_foo, _bar, _base, size, fo = sec
n = size // 24

entries = []
for i in range(n):
    o = fo + i * 24
    sub, rank = struct.unpack("<II", d[o:o + 8])
    func, arg = struct.unpack("<QQ", d[o + 8:o + 24])
    entries.append((sub, rank, func, arg))

nm = subprocess.run(["llvm-nm", "-n", KERNEL], capture_output=True, text=True).stdout
syms = []
for line in nm.splitlines():
    q = line.split()
    if len(q) == 3:
        try:
            a = int(q[0], 16)
        except ValueError:
            continue
        syms.append((a, q[2]))
syms.sort()
addrs = [s[0] for s in syms]


def name(a):
    i = bisect.bisect_right(addrs, a) - 1
    if i < 0:
        return "?"
    if syms[i][0] == a:
        return syms[i][1]
    return "%s+0x%x" % (syms[i][1], a - syms[i][0])


lines = []
lines.append("#include <stdio.h>")
lines.append("struct startup_entry { unsigned int subsystem; unsigned int rank;"
             " unsigned long long func; unsigned long long arg; int orig; };")
lines.append("extern void bsd_qsort(void *, unsigned long, unsigned long,"
             " int (*)(const void *, const void *));")
lines.append("static const char *names[%d] = {" % n)
for e in entries:
    lines.append('  "%s",' % name(e[2]).replace('"', ""))
lines.append("};")
lines.append("static struct startup_entry tab[%d] = {" % n)
for i, (sub, rank, func, arg) in enumerate(entries):
    lines.append("  {%d, %du, 0x%xULL, 0x%xULL, %d}," % (sub, rank, func, arg, i))
lines.append("};")
lines.append("""static int cmp(const void *a, const void *b)
{
	const struct startup_entry *x = a, *y = b;
	if (x->subsystem == y->subsystem) {
		if (x->rank == y->rank) {
			return 0;
		}
		return x->rank > y->rank ? 1 : -1;
	}
	return x->subsystem > y->subsystem ? 1 : -1;
}
int main(void)
{
	int i, k = 0;
	bsd_qsort(tab, NN, sizeof tab[0], cmp);
	for (i = 0; i < NN; i++) {
		if (tab[i].subsystem != 16) {
			continue;
		}
		printf("%2d %016llx rank=%u %s\\n", ++k, tab[i].func,
		    tab[i].rank, names[tab[i].orig]);
	}
	return 0;
}""".replace("NN", str(n)))

with open(OUT, "w") as f:
    f.write("\n".join(lines) + "\n")
print("wrote %s with %d entries" % (OUT, n))
