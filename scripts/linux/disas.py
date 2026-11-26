#!/usr/bin/env python3
"""Disassemble a VA range out of a Mach-O using capstone (no llvm-objdump).

Usage: disas.py <macho> <hexaddr> [bytes=96]
"""
import sys, struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from symaddr import load_syms, resolve

def segs(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, res = struct.unpack_from('<IiiIIIII', data, 0)
    off = 32
    out = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            name = data[off+8:off+24].rstrip(b'\0').decode()
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, off+24)
            out.append((name, vmaddr, vmsize, fileoff, filesize))
        off += cmdsize
    return data, out

def va2off(seginfo, va):
    for name, vmaddr, vmsize, fileoff, filesize in seginfo:
        if va >= vmaddr and va < vmaddr + vmsize:
            delta = va - vmaddr
            if delta < filesize:
                return fileoff + delta
    return None

if __name__ == '__main__':
    macho = sys.argv[1]
    va = int(sys.argv[2], 16)
    nbytes = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    data, seginfo = segs(macho)
    syms = load_syms(macho)
    off = va2off(seginfo, va)
    if off is None:
        sys.exit('VA not mapped')
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for ins in md.disasm(data[off:off+nbytes], va):
        r = resolve(syms, ins.address)
        ann = ''
        if r and r[1] == 0:
            ann = f'   <{r[0]}>'
        print(f'{ins.address:016x}: {ins.mnemonic:<8} {ins.op_str}{ann}')
