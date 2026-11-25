#!/usr/bin/env python3
"""g0245d v375 -- read out the real wait-status at the initproc panic.

v374 photo (16:42:58): the console was NO LONGER stuck in pmap_switch.  Ring
showed `v318 execute ret 0`, `v320 ltp done`, `v326 sc 1`, `v326 exit 42`,
`v373 has/get` (AMFI guards firing), `v329 panic msg`, then the status row:

  initproc failed to start -- no exit reason available -- (signal 8 ...

`kern_exit.c:1834` panic_with_options: prefix = "initproc failed to start"
because initproc_spawned == false, and WTERMSIG(rv) == 8 == SIGFPE.  This
contradicts the synthetic launchd's designed exit(42): that would give
rv = 42<<8, WTERMSIG=0, WEXITSTATUS=42.  (Ring seq is a circular buffer, so
9201/9202 printed physically above 9184 are logically NEWER -- exit(42) did
happen before the panic.)

v375 adds ONE diagnostic chain, immediately before the panic, only for
initproc: raw rv, WTERMSIG, WEXITSTATUS, pid, initproc_spawned.  Values go to
the trace ring (status row would be overwritten by the expanded panic text).
No behavior change, no guard -- we must not suppress the initproc panic
until we know whether this is a real SIGFPE or a malformed wait status.

CUMULATIVE + IDEMPOTENT over v374.  Only kern_exit.c is touched.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
F = os.path.join(W, "bsd", "kern", "kern_exit.c")
if not os.path.isfile(F):
    sys.exit("required file not found: %s" % F)

s = open(F, encoding="utf-8", errors="replace").read()
if "v375 xstat" in s:
    print("patch_v375: already applied -- skip")
    sys.exit(0)

A = ('\tif (p->p_exit_reason == OS_REASON_NULL) {\n'
     '\t\tpanic_with_options(0, NULL, DEBUGGER_OPTION_INITPROC_PANIC, '
     '"%s -- no exit reason available -- (signal %d, exit status %d %s)",\n')
if s.count(A) != 1:
    sys.exit("patch_v375: panic anchor count=%d (want 1)" % s.count(A))

INS = (
    '\tif (p == initproc) {\n'
    '\t\t{ extern void g0245d_status(const char *);\n'
    '\t\t  g0245d_status("v375 exitdiag"); }\n'
    '\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
    '\t\t  g0245d_tracev("v375 rv", (unsigned long long)(unsigned int)rv);\n'
    '\t\t  g0245d_tracev("v375 sig", (unsigned long long)(unsigned int)WTERMSIG(rv));\n'
    '\t\t  g0245d_tracev("v375 xstat", (unsigned long long)(unsigned int)WEXITSTATUS(rv));\n'
    '\t\t  g0245d_tracev("v375 pid", (unsigned long long)(unsigned int)proc_getpid(p));\n'
    '\t\t  g0245d_tracev("v375 spawn", (unsigned long long)(unsigned int)initproc_spawned); }\n'
    '\t}\n'
)
s = s.replace(A, INS + A, 1)
open(F, "w", encoding="utf-8").write(s)
print("patch_v375: kern_exit.c initproc wait-status diagnostics added")
print("patch_v375: done")
