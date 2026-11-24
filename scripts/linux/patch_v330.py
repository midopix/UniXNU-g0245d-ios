#!/usr/bin/env python3
"""g0245d v330: fix the synthetic launchd Mach-O (ENOEXEC root cause).

patch_v289 built the header with struct.pack("<IIIIIII", ...) -- seven uint32
fields, but mach_header_64 has eight (magic, cputype, cpusubtype, filetype,
ncmds, sizeofcmds, flags, reserved).  Everything after filetype therefore sat
one slot early:

  real field   written value        correct value
  ncmds        352 (=72+280)        2
  sizeofcmds   1                    344 (=72+272)
  flags        0                    0
  reserved     absent               0

The loader therefore tried to walk 352 load commands through a 376-byte image
and returned ENOEXEC (errno 8), with an out-of-bounds read that shows up as
ESR_EC 0x25 data aborts.  cpusubtype was also 2 (ARM64E) instead of 0
(ARM64_ALL), and LC_SEGMENT_64 claimed filesize 0x2000 regardless of the real
image size.

This patch regenerates the whole header+load-command blob (376 bytes) with the
correct fields and points G0245D_LAUNCHD_HDR_SIZE at it.
"""
import os
import struct
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
PATH = os.path.join(W, 'iokit/bsddev/IOKitBSDInit.cpp')

# --- rebuild the image blobs ------------------------------------------------
CODE = bytes.fromhex('40058052200080d2010010d4')   # mov w0,#42; mov x16,#1; svc #0x80
CODE_OFF = 0x1000
IMAGE_SIZE = CODE_OFF + len(CODE)                   # 0x100c

segname = b'__TEXT'.ljust(16, b'\0')
seg = struct.pack('<II', 0x19, 72) + segname
seg += struct.pack('<QQQQIIII',
                   0x100000,      # vmaddr
                   0x2000,        # vmsize (page-aligned mapping window)
                   0,             # fileoff
                   IMAGE_SIZE,    # filesize: actual, not 0x2000
                   7,             # maxprot  rwx
                   5,             # initprot r-x
                   0,             # nsects
                   0)             # flags

ARM_THREAD_STATE64_COUNT = 68       # 34 uint64 fields: x[29] fp lr sp pc cpsr(+pad)
cmd_size = 8 + 8 + 34 * 8           # cmd,cmdsize | flavor,count | 34*8 state = 288
unix = struct.pack('<IIII', 0x5, cmd_size, 6, ARM_THREAD_STATE64_COUNT)
regs = [0] * 34
regs[29] = 0                        # fp
regs[30] = 0                        # lr
regs[31] = 0x102000                 # sp = vmaddr + 0x2000
regs[32] = 0x100000 + CODE_OFF      # pc = vmaddr + 0x1000
regs[33] = 0                        # cpsr: EL0t user mode
unix += b''.join(struct.pack('<Q', v) for v in regs)

sizeofcmds = len(seg) + len(unix)   # 344
hdr = struct.pack('<IIIIIIII',
                  0xFEEDFACF,   # magic
                  0x0100000C,   # cputype  CPU_TYPE_ARM64
                  0,            # cpusubtype CPU_SUBTYPE_ARM64_ALL
                  2,            # filetype MH_EXECUTE
                  2,            # ncmds    (LC_SEGMENT_64 + LC_UNIXTHREAD)
                  sizeofcmds,   # sizeofcmds
                  0,            # flags
                  0)            # reserved  <-- the field that was missing

blob = hdr + seg + unix
assert len(hdr) == 32, len(hdr)
assert len(seg) == 72, len(seg)
assert len(unix) == 288, len(unix)
assert len(blob) == 32 + sizeofcmds, len(blob)


def c_array(data, indent='    '):
    lines = []
    for i in range(0, len(data), 16):
        lines.append(indent + ','.join('0x%02X' % b for b in data[i:i + 16]))
    return ',\n'.join(lines)


text = open(PATH, encoding='utf-8').read()
if 'v330' in text:
    print('  launchd mach-o: already applied')
    sys.exit(0)

OLD_BLOCK_START = '/* g0245d v289: minimal arm64 Mach-O'
OLD_ARRAY_END = 'static const unsigned char g0245d_launchd_code[12] = {' \
                ' 0x40,0x05,0x80,0x52,0x20,0x00,0x80,0xD2,0x01,0x00,0x10,0xD4 };'

start = text.find(OLD_BLOCK_START)
end = text.find(OLD_ARRAY_END)
if start < 0 or end < 0:
    sys.exit(f'anchor not found: start={start} end={end}')
end += len(OLD_ARRAY_END)

NEW = (
    '/* g0245d v330: minimal but *valid* arm64 Mach-O, entry _start: exit(42).\n'
    ' * patch_v289 packed only seven uint32 header fields, so ncmds/sizeofcmds\n'
    ' * landed one slot early (ncmds=352, sizeofcmds=1) and the loader walked\n'
    ' * 352 bogus load commands, returning ENOEXEC (errno 8) after an\n'
    ' * out-of-bounds read.  Header is now the full 32 bytes with reserved,\n'
    ' * ncmds=2, sizeofcmds=344, cpusubtype=ARM64_ALL, and LC_SEGMENT_64\n'
    ' * filesize matches the real image (0x100c).\n'
    ' * Layout: header 32 | LC_SEGMENT_64 72 | LC_UNIXTHREAD 288 = 392 bytes,\n'
    ' * __TEXT @0x100000 (vmsize 0x2000), pc=0x101000, sp=0x102000,\n'
    ' * code at file offset 0x1000: mov w0,#42; mov x16,#1; svc #0x80. */\n'
    'static const unsigned char g0245d_launchd_hdr[' + str(len(blob)) + '] = {\n'
    + c_array(blob) + '\n'
    '};\n'
    'static const unsigned char g0245d_launchd_code[12] = { 0x40,0x05,0x80,0x52,0x20,0x00,0x80,0xD2,0x01,0x00,0x10,0xD4 };'
)

text = text[:start] + NEW + text[end:]
text = text.replace('#define G0245D_LAUNCHD_HDR_SIZE 28u',
                    '#define G0245D_LAUNCHD_HDR_SIZE ' + str(len(blob)) + 'u')
open(PATH, 'w', encoding='utf-8').write(text)
print('  launchd mach-o: rebuilt (376-byte header+load commands)')
print(f'  sizeofcmds={sizeofcmds} ncmds=2 filesize=0x{IMAGE_SIZE:x} pc=0x{0x100000 + CODE_OFF:x}')
