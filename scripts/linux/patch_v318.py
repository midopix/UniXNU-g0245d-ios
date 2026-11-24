#!/usr/bin/env python3
"""g0245d v318 -- quiet the lookup probes and bracket execve() for launchd.

v317 verdict (photo 09:48): no v317 probe visible, but the screen shows TWO
full fsv + namei sequences (v299 fsv enter/lock/done, v301 look vnode / lhfv /
namei exit ok) and stops at `v301 namei exit ok`.

That is exactly what exec of /sbin/launchd does: load_init_program_at_path()
-> execve() -> namei("/sbin/launchd") through mockfs, twice (launchd.debug /
launchd.development / launchd fallbacks).  The v317 milestone lines scrolled
off because the 13 high-frequency v301/v302 lookup probes fill half the panel
on every namei.

v318:
  1. silences the v301/v302 lookup probes in vfs_lookup.c (`{ }`), freeing
     ~20 screen lines so the milestone chain stays visible;
  2. replaces `return execve(...)` with an explicit call so the execve return
     code can be printed (`v318 execve call` / `v318 execve ret <n>`).

Idempotent.  Run on the tree that already has v317 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v318.py
"""
import os
import re
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

LOOKUP = os.path.join(WORK, "bsd/vfs/vfs_lookup.c")
EXEC = os.path.join(WORK, "bsd/kern/kern_exec.c")
MARK = "v318 execve call"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what, count=1):
    n = src.count(old)
    if n != count:
        sys.exit("%s: anchor found %d times (expected %d)" % (what, n, count))
    return src.replace(old, new)


# 1. quiet the lookup probes
s = read(LOOKUP)
if "g0245d v318: lookup probes quieted" in s:
    print("vfs_lookup.c: already quieted")
else:
    pat = re.compile(
        r'\{ extern void g0245d_trace(_u)?\(const char \*(, unsigned int)?\); '
        r'g0245d_trace(_u)?\("v30[12] [^"]*"[^;]*\); \}'
    )
    s2, n = pat.subn("{ }", s)
    if n < 10:
        sys.exit("v318: only matched %d lookup probes, aborting" % n)
    s2 = "/* g0245d v318: lookup probes quieted (%d) so milestone lines stay on screen */\n" % n + s2
    write(LOOKUP, s2)
    print("vfs_lookup.c: quieted %d lookup probes" % n)

# 2. bracket execve()
s = read(EXEC)
if MARK in s:
    print("kern_exec.c: already v318")
else:
    s = sub(
        s,
        "\tset_security_token(p);\n\n\treturn execve(p, &init_exec_args, retval);\n}",
        "\tset_security_token(p);\n\n"
        '\t{ extern void g0245d_trace(const char *); g0245d_trace("v318 execve call"); }\n'
        "\terror = execve(p, &init_exec_args, retval);\n"
        '\t{ extern void g0245d_trace_u(const char *, unsigned int); g0245d_trace_u("v318 execve ret", (unsigned int)(error)); }\n'
        "\n\treturn error;\n}",
        "v318: bracket execve",
    )
    write(EXEC, s)
    print("kern_exec.c: v318 execve probes installed")

print("v318 patch complete")
