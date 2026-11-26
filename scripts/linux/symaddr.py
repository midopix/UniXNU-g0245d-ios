#!/usr/bin/env python3
"""Minimal Mach-O symbol resolver (no llvm-nm needed).

Usage: symaddr.py <macho> <hexaddr> [<hexaddr> ...]
Prints nearest symbol (<= addr) as sym+0xoff for each address.
"""
import sys, struct, bisect

def load_syms(path):
    with open(path, 'rb') as f:
        data = f.read()
    magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, res = struct.unpack_from('<IiiIIIII', data, 0)
    assert magic == 0xfeedfacf, hex(magic)
    off = 32
    symtab = None
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, off)
        if cmd == 0x2:  # LC_SYMTAB
            symoff, nsyms, stroff, strsize = struct.unpack_from('<IIII', data, off + 8)
            symtab = (symoff, nsyms, stroff, strsize)
        off += cmdsize
    assert symtab, 'no symtab'
    symoff, nsyms, stroff, strsize = symtab
    strtab = data[stroff:stroff + strsize]
    syms = []
    for i in range(nsyms):
        n_strx, n_type, n_sect, n_desc, n_value = struct.unpack_from('<IBBHQ', data, symoff + i * 16)
        if n_value == 0:
            continue
        end = strtab.find(b'\0', n_strx)
        name = strtab[n_strx:end].decode('utf-8', 'replace')
        if not name:
            continue
        syms.append((n_value, name, n_type, n_sect))
    syms.sort()
    return syms

def resolve(syms, addr):
    vals = [s[0] for s in syms]
    i = bisect.bisect_right(vals, addr) - 1
    if i < 0:
        return None
    v, name, t, sect = syms[i]
    return name, addr - v

if __name__ == '__main__':
    macho = sys.argv[1]
    syms = load_syms(macho)
    print(f'# {macho}: {len(syms)} symbols')
    for a in sys.argv[2:]:
        addr = int(a, 16)
        r = resolve(syms, addr)
        if r:
            print(f'{a}  =  {r[0]} + 0x{r[1]:x}')
        else:
            print(f'{a}  =  <below first symbol>')
