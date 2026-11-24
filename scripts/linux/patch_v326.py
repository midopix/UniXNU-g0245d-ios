#!/usr/bin/env python3
"""g0245d v326: probe the userland hand-off path.

v325 reached `v318 execve ret 0` and then panicked (the screen showed the
kernel debugger key map again), and a later boot stopped even earlier at
`v299 fsv enter`.  Three labels narrow down whether PID1 ever returned to
user mode, whether it issued a syscall, and whether that syscall was exit(42)
from the synthetic launchd Mach-O:

  v326 exc ret   - first entry to thread_exception_return (status row, once)
  v326 sc <n>    - unix_syscall entry, prints the syscall number
  v326 exit <n>  - exit(2) entry, prints the exit value

Everything else stays at the v325 configuration (no native driver, no UFS
device-tree nodes, SoftwareAES off, mockfs on).
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')


def patch(rel, old, new, label):
    path = os.path.join(W, rel)
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    if new in text:
        print(f'  {label}: already applied')
        return
    if text.count(old) != 1:
        sys.exit(f'{label}: anchor count={text.count(old)} in {rel}')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text.replace(old, new, 1))
    print(f'  {label}: applied')


# 1) unix_syscall entry
patch(
    'bsd/dev/arm/systemcalls.c',
    "\tcode = arm_get_syscall_number(state);\n",
    "\tcode = arm_get_syscall_number(state);\n"
    "\t/* g0245d v326: is PID1 actually issuing syscalls after exec? */\n"
    "\t{ extern void g0245d_trace_u(const char *, unsigned int);\n"
    "\t  g0245d_trace_u(\"v326 sc\", (unsigned int)code); }\n",
    'syscall-entry',
)

# 2) exit(2) entry
patch(
    'bsd/kern/kern_exit.c',
    "exit(proc_t p, struct exit_args *uap, int *retval)\n{\n"
    "\tp->p_xhighbits = ((uint32_t)(uap->rval) & 0xFF000000) >> 24;\n",
    "exit(proc_t p, struct exit_args *uap, int *retval)\n{\n"
    "\t/* g0245d v326: the synthetic launchd ends with exit(42). */\n"
    "\t{ extern void g0245d_trace_u(const char *, unsigned int);\n"
    "\t  g0245d_trace_u(\"v326 exit\", (unsigned int)uap->rval); }\n"
    "\tp->p_xhighbits = ((uint32_t)(uap->rval) & 0xFF000000) >> 24;\n",
    'exit-entry',
)

# 3) first return-to-user
patch(
    'osfmk/arm64/sleh.c',
    "thread_exception_return()\n{\n\tthread_t thread = current_thread();\n",
    "thread_exception_return()\n{\n\tthread_t thread = current_thread();\n"
    "\t/* g0245d v326: first kernel->user transition.  Status row only, this\n"
    "\t * path runs for every exception return and would flood the trace ring. */\n"
    "\t{ extern void g0245d_status(const char *);\n"
    "\t  static int v326_once = 0;\n"
    "\t  if (!v326_once) { v326_once = 1; g0245d_status(\"v326 exc ret\"); } }\n",
    'exception-return',
)

print('patch_v326 done')
