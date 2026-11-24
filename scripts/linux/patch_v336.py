#!/usr/bin/env python3
"""g0245d v336 -- give the fixture the 4 GB hard page zero arm64 requires.

v335 narrowed it down to the last steps of load_machfile:

    v335 pmap ok / map ok / aslr ok / parse ok     parse_machfile succeeded
    v333 lret 2                                    LOAD_BADMACHO

LOAD_BADMACHO is 2 (bsd/kern/mach_loader.h:116), and the only check between
"parse ok" and the in_exec halt block that returns it is:

    if (enforce_hard_pagezero && result->is_64bit_addr &&
        header->cputype == CPU_TYPE_ARM64) {
        if (vm_map_has_hard_pagezero(map, 0x100000000) == FALSE) {
            vm_map_deallocate(map);
            return LOAD_BADMACHO;
        }
    }

and vm_map_has_hard_pagezero() is literally `map->min_offset >= pagezero_size`.
Only a __PAGEZERO segment raises min_offset: load_segment() calls
vm_map_raise_min_offset(map, vmaddr + vmsize).  Our fixture had just __TEXT, so
min_offset stayed 0 and every 64-bit arm64 load fails this check no matter how
correct the rest of the image is.

So repack the header with the standard layout:

    mach_header_64                          32
    LC_SEGMENT_64 __PAGEZERO  0 / 0x100000000, no file content   72
    LC_SEGMENT_64 __TEXT      0x100000 / 0x2000, filesize 0x100c  72
    LC_UNIXTHREAD             pc=0x101000  sp=0x102000  cpsr=0   288

ncmds = 3, sizeofcmds = 432, blob = 464 bytes.
"""
import os
import re
import struct
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'iokit/bsddev/IOKitBSDInit.cpp')

CODE_OFF = 0x1000
CODE_LEN = 12
IMAGE_SIZE = CODE_OFF + CODE_LEN          # 0x100c


def segment(name, vmaddr, vmsize, fileoff, filesize, maxprot, initprot):
    return (struct.pack('<II', 0x19, 72) + name.ljust(16, b'\0') +
            struct.pack('<QQQQIIII', vmaddr, vmsize, fileoff, filesize,
                        maxprot, initprot, 0, 0))


pagezero = segment(b'__PAGEZERO', 0, 0x100000000, 0, 0, 0, 0)
text = segment(b'__TEXT', 0x100000, 0x2000, 0, IMAGE_SIZE, 7, 5)

thread = struct.pack('<IIII', 0x5, 8 + 8 + 34 * 8, 6, 68)
regs = [0] * 34
regs[31] = 0x102000                       # sp
regs[32] = 0x100000 + CODE_OFF            # pc
regs[33] = 0                              # cpsr: EL0t
thread += b''.join(struct.pack('<Q', v) for v in regs)

sizeofcmds = len(pagezero) + len(text) + len(thread)
hdr = struct.pack('<IIIIIIII', 0xFEEDFACF, 0x0100000C, 0, 2,
                  3, sizeofcmds, 0, 0)
blob = hdr + pagezero + text + thread

assert len(hdr) == 32 and len(pagezero) == 72 and len(text) == 72
assert len(thread) == 288 and len(blob) == 32 + sizeofcmds
assert sizeofcmds == 432, sizeofcmds


def c_array(data):
    lines = []
    for i in range(0, len(data), 16):
        lines.append('    ' + ','.join('0x%02X' % b for b in data[i:i + 16]))
    return ',\n'.join(lines)


text_src = open(PATH, encoding='utf-8').read()
if 'g0245d_launchd_hdr[464]' in text_src:
    print('patch_v336: already applied')
    sys.exit(0)

new_array = ('static const unsigned char g0245d_launchd_hdr[%d] = {\n%s\n};'
             % (len(blob), c_array(blob)))
text_src, n = re.subn(r'static const unsigned char g0245d_launchd_hdr\[\d+\] = \{.*?\n\};',
                      new_array, text_src, count=1, flags=re.S)
assert n == 1, n

text_src, n2 = re.subn(r'#define G0245D_LAUNCHD_HDR_SIZE \d+u',
                       '#define G0245D_LAUNCHD_HDR_SIZE %du' % len(blob),
                       text_src, count=1)
assert n2 == 1, n2

open(PATH, 'w', encoding='utf-8').write(text_src)
print('patch_v336: __PAGEZERO added (vmsize 0x100000000), blob=%d ncmds=3 sizeofcmds=%d'
      % (len(blob), sizeofcmds))
