#!/usr/bin/env python3
"""g0245d v378 -- make the panic message readable in a glary photo.

v377 photo: the SHA256 data abort is GONE (guard worked), but the expanded
panic text written by v329 (`g0245d_trace(v329_msg)`) was obscured by phone
case reflection.  Status row showed only `v363 post`, so the panic itself
could not be read.

This patch is DIAGNOSTIC ONLY (no behavior change).  It uses the already
expanded v329_msg and:
  - writes three short, labeled ring lines: v378 pm0/pm1/pm2 (24 chars each),
    with the label at the START of each line so a partially glary photo still
    shows which segment it is;
  - sets the status row to a short `v378 <first 24 chars>` so the most
    informative prefix survives even when the ring is covered;
  - records panic_caller via tracev as v378 pc.

CUMULATIVE + IDEMPOTENT over v377.  Only osfmk/kern/debug.c is touched.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "osfmk/kern/debug.c")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

src = open(PATH, encoding="utf-8", errors="replace").read()
if 'v378 pm%d' in src:
    print("patch_v378: already applied -- skip")
    sys.exit(0)

old = (
    '\t\tg0245d_status(v329_msg);\n'
    '\t\tg0245d_trace("v329 panic msg");\n'
    '\t\tg0245d_trace(v329_msg);\n'
    '\t\tg0245d_tracev("v329 pc", (unsigned long long)panic_caller);\n'
)
if src.count(old) != 1:
    sys.exit("patch_v378: anchor count=%d" % src.count(old))

new = old + (
    '\t\t/* g0245d v378: split the expanded panic message into short labeled\n'
    '\t\t * ring lines so a glary photo still exposes the errno/path. */\n'
    '\t\t{\n'
    '\t\t\tchar v378_buf[48];\n'
    '\t\t\tint v378_i;\n'
    '\t\t\tfor (v378_i = 0; v378_i < 3; v378_i++) {\n'
    '\t\t\t\tsnprintf(v378_buf, sizeof(v378_buf), "v378 pm%d %.*s",\n'
    '\t\t\t\t    v378_i, 24, v329_msg + v378_i * 24);\n'
    '\t\t\t\tg0245d_trace(v378_buf);\n'
    '\t\t\t}\n'
    '\t\t\tsnprintf(v378_buf, sizeof(v378_buf), "v378 %.24s", v329_msg);\n'
    '\t\t\tg0245d_status(v378_buf);\n'
    '\t\t\tg0245d_tracev("v378 pc", (unsigned long long)panic_caller);\n'
    '\t\t}\n'
)

src = src.replace(old, new, 1)
open(PATH, "w", encoding="utf-8").write(src)
print("patch_v378: panic message split into v378 pm0/pm1/pm2 + short status")
