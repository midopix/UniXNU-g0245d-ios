#!/usr/bin/env python3
"""g0245d v333 -- two things at once.

1) The launchd fixture's exit sequence was wrong.  Decoding v289's 12 bytes
   against the arm64 encoding:

       40 05 80 52   mov  w0, #42      correct
       20 00 80 D2   mov  x0, #1       WRONG: clobbers the status and targets
                                       x0, while Darwin takes the syscall
                                       number in x16
       01 00 10 D4   svc  #0x8000      WRONG: imm16 is 0x8000, not 0x80

   Now: mov w0,#42 ; mov x16,#1 ; svc #0x80.

2) execve still returns ENOEXEC (errno 8) for /sbin/launchd even though the
   rebuilt Mach-O parses cleanly with llvm-objdump.  In XNU the value -1 is
   folded into ENOEXEC at the `bad:` label, and load_machfile failures reach
   the same errno through load_return_to_errno(), so the errno alone cannot
   say which check rejected the image.  Print what the kernel actually read:

       v333 magic        mach_header->magic (want 0xfeedfacf)
       v333 type ncmds   filetype << 16 | ncmds (want 2 << 16 | 2)
       v333 szcmds       sizeofcmds (want 360)
       v333 lret         load_machfile return (0 == LOAD_SUCCESS)
       v333 bad err      the errno the activator finally returns

   If `v333 magic` is garbage the problem is what mockfs handed us (the memdisk
   is served by bcopy from mdBase<<12, so a misaligned pool address would
   shift the whole image).  If magic is right but lret is non-zero, the loader
   rejected the load commands and the next step is mach_loader.c itself.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
EXEC = os.path.join(W, 'bsd/kern/kern_exec.c')
BSDINIT = os.path.join(W, 'iokit/bsddev/IOKitBSDInit.cpp')

if 'v333 bad err' in open(EXEC, encoding='utf-8').read():
    print('patch_v333: already applied')
    sys.exit(0)

# --------------------------------------------------- 1. fix the exit sequence
BAD_CODE = ('static const unsigned char g0245d_launchd_code[12] = '
            '{ 0x40,0x05,0x80,0x52,0x20,0x00,0x80,0xD2,0x01,0x00,0x10,0xD4 };')
GOOD_CODE = ('/* v333: v289 wrote x0 instead of x16 and used svc #0x8000.\n'
             ' * Darwin arm64: syscall number in x16, trap via svc #0x80. */\n'
             'static const unsigned char g0245d_launchd_code[12] = '
             '{ 0x40,0x05,0x80,0x52,0x30,0x00,0x80,0xD2,0x01,0x10,0x00,0xD4 };')
t = open(BSDINIT, encoding='utf-8').read()
assert t.count(BAD_CODE) == 1, t.count(BAD_CODE)
open(BSDINIT, 'w', encoding='utf-8').write(t.replace(BAD_CODE, GOOD_CODE, 1))

# ------------------------------------------- 2. dump the header the kernel saw
s = open(EXEC, encoding='utf-8').read()

ENTRY = '\tstruct mach_header *mach_header = (struct mach_header *)imgp->ip_vdata;\n'
ENTRY_NEW = ENTRY + (
    '\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
    '\t  extern void g0245d_tracev(const char *, unsigned long long);\n'
    '\t  g0245d_tracev("v333 magic", (unsigned long long)mach_header->magic);\n'
    '\t  g0245d_trace_u("v333 type ncmds",\n'
    '\t      ((unsigned int)mach_header->filetype << 16) |\n'
    '\t      (unsigned int)(mach_header->ncmds & 0xFFFFu));\n'
    '\t  g0245d_trace_u("v333 szcmds", (unsigned int)mach_header->sizeofcmds); }\n')
assert s.count(ENTRY) == 1
s = s.replace(ENTRY, ENTRY_NEW, 1)

LOAD = '\tlret = load_machfile(imgp, mach_header, thread, &map, &load_result);\n'
LOAD_NEW = LOAD + (
    '\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
    '\t  g0245d_trace_u("v333 lret", (unsigned int)lret); }\n')
assert s.count(LOAD) == 1
s = s.replace(LOAD, LOAD_NEW, 1)

BADBLK = ('bad:\n'
          '\t/* If we hit this, we likely would have leaked an exit reason */\n'
          '\tassert(exec_failure_reason == OS_REASON_NULL);\n')
BADBLK_NEW = ('bad:\n'
              '\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
              '\t  g0245d_trace_u("v333 bad err", (unsigned int)error); }\n'
              '\t/* If we hit this, we likely would have leaked an exit reason */\n'
              '\tassert(exec_failure_reason == OS_REASON_NULL);\n')
assert s.count(BADBLK) == 1
s = s.replace(BADBLK, BADBLK_NEW, 1)

open(EXEC, 'w', encoding='utf-8').write(s)
print('patch_v333: exit sequence fixed, 5 exec probes installed')
