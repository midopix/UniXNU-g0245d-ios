#!/usr/bin/env python3
"""g0245d v359 -- surface execve()'s errno on the STATUS row.

v358 photo (20:07, g0245d-v358-screen-200740.jpg): status FINALLY advanced past
`v342 b5 vmexec ok` to `v341 g execve ret` (kern_exec.c:7986) -- execve() from
load_init_program_at_path() returned.  No `v358 ec=` / `v328 ec 37` this time,
and hb307's counter was still climbing (kernel alive, doing specfs buf I/O).

The ONE remaining unknown is execve()'s return value.  `v318 execve ret` is a
trace_u that got scrolled out of the 12-line ring by the following
`v316 spec enter/dispatch call` lines, so it cannot be read from the photo.
HANDOFF §14 already recorded an earlier PID1 exec returning ENOEXEC(8).

v359: replace the fixed `v341 g execve ret` status with a FORMATTED status that
carries the errno, and add two more status-row checkpoints on the failure path
(the init_programs[] retry loop and the pre-panic block).  Because status is
overwrite-style and sits on the last screen row, the final visible status tells
us exactly how far load_init_program() got and with what error.

CUMULATIVE + IDEMPOTENT over v358.  Anchors (v341/v329 probes) come from the
common early patches and exist on BOTH bring-up lines (dev and Ubuntu).
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
KE = os.path.join(W, "bsd", "kern", "kern_exec.c")
if not os.path.isfile(KE):
    sys.exit("required file not found: %s" % KE)
s = open(KE, encoding="utf-8", errors="replace").read()
MARK = "v359 exret"
if MARK in s:
    print("patch_v359: already applied -- skip")
    sys.exit(0)

# -------------------------------------------------------------- STEP 1 -- execve errno
OLD1 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  g0245d_status("v341 g execve ret"); }\n')
NEW1 = ('\t{ extern void g0245d_status(const char *);\n'
        '\t  static char v359buf[96];\n'
        '\t  snprintf(v359buf, sizeof(v359buf), "v359 exret err=%u",\n'
        '\t      (unsigned int)(error));\n'
        '\t  g0245d_status(v359buf); }\n')
c = s.count(OLD1)
if c != 1:
    sys.exit("patch_v359 STEP1: need 1 v341 g execve ret status block, found %d" % c)
s = s.replace(OLD1, NEW1, 1)
print("patch_v359 STEP1: execve errno -> status row")

# ------------------------------------------------- STEP 2 -- retry-loop errno
OLD2 = ('\t\terror = load_init_program_at_path(p, (user_addr_t)scratch_addr, '
        'init_programs[i], init_envp);\n')
NEW2 = OLD2 + (
    '\t\t{ extern void g0245d_status(const char *);\n'
    '\t\t  static char v359tbuf[96];\n'
    '\t\t  snprintf(v359tbuf, sizeof(v359tbuf), "v359 try i=%u err=%u",\n'
    '\t\t      (unsigned int)i, (unsigned int)(error));\n'
    '\t\t  g0245d_status(v359tbuf); }\n')
c = s.count(OLD2)
if c != 1:
    sys.exit("patch_v359 STEP2: need 1 init_programs retry call, found %d" % c)
s = s.replace(OLD2, NEW2, 1)
print("patch_v359 STEP2: init_programs[] retry errno -> status row")

# --------------------------------------------------- STEP 3 -- pre-panic errno
OLD3 = '\t  g0245d_trace_u("v329 pan err", (unsigned int)error); }\n'
NEW3 = OLD3 + (
    '\t{ extern void g0245d_status(const char *);\n'
    '\t  static char v359pbuf[96];\n'
    '\t  snprintf(v359pbuf, sizeof(v359pbuf), "v359 pan i=%u err=%u",\n'
    '\t      (unsigned int)i, (unsigned int)error);\n'
    '\t  g0245d_status(v359pbuf); }\n')
c = s.count(OLD3)
if c != 1:
    sys.exit("patch_v359 STEP3: need 1 v329 pan err trace, found %d" % c)
s = s.replace(OLD3, NEW3, 1)
print("patch_v359 STEP3: pre-panic i/errno -> status row")

open(KE, "w", encoding="utf-8").write(s)
print("patch_v359: wrote %s" % KE)
print("patch_v359: done")
