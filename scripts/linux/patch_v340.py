#!/usr/bin/env python3
"""g0245d v340 -- move __TEXT above the 4 GB page zero.

v339 nailed it:

    g0245d v339 b2 kr=1 cur=100000-102000 f=0-2000 pg=12

kr=1 is KERN_INVALID_ADDRESS on the file-backed bulk mapping, and pg=12 says the
map really uses 4 KB pages.  The range itself is perfectly aligned, so the
address is the problem, not the flags: v336's __PAGEZERO segment raised
map->min_offset to 0x100000000, and __TEXT still sat at 0x100000 -- below the
new minimum.  vm_map_enter() correctly rejects anything under min_offset.

That is also how real 64-bit Mach-O executables look: __PAGEZERO covers
0..4 GB and __TEXT starts at 0x100000000.

New layout:
    __PAGEZERO  vmaddr 0            vmsize 0x100000000
    __TEXT      vmaddr 0x100000000  vmsize 0x2000  filesize 0x100c
    pie-free    pc = 0x100001000    sp = 0x100002000
"""
import os
import re
import struct
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'iokit/bsddev/IOKitBSDInit.cpp')

TEXT_VMADDR = 0x100000000          # just past the 4 GB page zero
CODE_OFF = 0x1000
CODE_LEN = 12
IMAGE_SIZE = CODE_OFF + CODE_LEN


def segment(name, vmaddr, vmsize, fileoff, filesize, maxprot, initprot):
    return (struct.pack('<II', 0x19, 72) + name.ljust(16, b'\0') +
            struct.pack('<QQQQIIII', vmaddr, vmsize, fileoff, filesize,
                        maxprot, initprot, 0, 0))


pagezero = segment(b'__PAGEZERO', 0, 0x100000000, 0, 0, 0, 0)
text = segment(b'__TEXT', TEXT_VMADDR, 0x2000, 0, IMAGE_SIZE, 7, 5)

thread = struct.pack('<IIII', 0x5, 8 + 8 + 34 * 8, 6, 68)
regs = [0] * 34
regs[31] = TEXT_VMADDR + 0x2000           # sp
regs[32] = TEXT_VMADDR + CODE_OFF         # pc
regs[33] = 0                              # cpsr: EL0t
thread += b''.join(struct.pack('<Q', v) for v in regs)

sizeofcmds = len(pagezero) + len(text) + len(thread)
hdr = struct.pack('<IIIIIIII', 0xFEEDFACF, 0x0100000C, 0, 2, 3, sizeofcmds, 0, 0)
blob = hdr + pagezero + text + thread
assert len(blob) == 32 + sizeofcmds and sizeofcmds == 432


def c_array(data):
    out = []
    for i in range(0, len(data), 16):
        out.append('    ' + ','.join('0x%02X' % b for b in data[i:i + 16]))
    return ',\n'.join(out)


src = open(PATH, encoding='utf-8').read()
if 'v340' in src:
    print('patch_v340: already applied')
    sys.exit(0)

new_array = ('/* v340: __TEXT moved to 0x100000000 -- __PAGEZERO raised\n'
             ' * map->min_offset to 4 GB, so a segment at 0x100000 got\n'
             ' * KERN_INVALID_ADDRESS from vm_map_enter(). */\n'
             'static const unsigned char g0245d_launchd_hdr[%d] = {\n%s\n};'
             % (len(blob), c_array(blob)))
src, n = re.subn(r'static const unsigned char g0245d_launchd_hdr\[\d+\] = \{.*?\n\};',
                 new_array, src, count=1, flags=re.S)
assert n == 1, n
open(PATH, 'w', encoding='utf-8').write(src)
print('patch_v340: __TEXT at 0x%x, pc=0x%x, sp=0x%x'
      % (TEXT_VMADDR, TEXT_VMADDR + CODE_OFF, TEXT_VMADDR + 0x2000))
