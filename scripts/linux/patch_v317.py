#!/usr/bin/env python3
"""g0245d v317 -- bisect load_init_program (the launchd loader).

v316 verdict (photo 09:43) -- BIG STEP: bsd_init completed.
    8628 v300 ubt done
    8629 bsd calling mountroot_post_hook
    8631 v248 bsd init done
    8634 bsd bsd_do_post - done
    8637 v256 hi alloc enter / 8638 v274 hi caller / 8639 v256 hi alloc ret
Note the trace count DROPPED (8691 -> 8639) yet it got much further: adding
probes inside spec_strategy perturbed the timing of a state-sensitive hang and
the mount completed.  devfs + mountroot_post_hook + utaskbootstrap all pass now.

bsd_init's last call is load_init_program(p) (bsd_init.c:1326) -- loading
launchd.  It runs, in order:
    boot_progress_stage("load_init_program enter")
    mach_vm_allocate_kernel(... scratch page ...)
    memorystatus_init_at_boot_snapshot()            (CONFIG_MEMORYSTATUS)
    load_init_program_at_path(p, scratch, "/sbin/launchd", envp)  -> panic on error

v317 brackets entry, the scratch allocation, and the launchd exec so the next
photo shows exactly which one stalls.

Idempotent.  Run on the tree that already has v316 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v317.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/kern/kern_exec.c")
MARK = "v317 lip enter"


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


T = '{ extern void g0245d_trace(const char *); g0245d_trace("%s"); }'
TU = '{ extern void g0245d_trace_u(const char *, unsigned int); g0245d_trace_u("%s", (unsigned int)(%s)); }'

s = read(F)
if MARK in s:
    print("kern_exec.c: already v317")
else:
    s = sub(
        s,
        '\tboot_progress_stage("load_init_program enter");\n',
        '\tboot_progress_stage("load_init_program enter");\n\t' + (T % "v317 lip enter") + "\n",
        "v317: lip entry",
    )
    s = sub(
        s,
        "\t(void) mach_vm_allocate_kernel(map, &scratch_addr, map_page_size, VM_FLAGS_ANYWHERE, VM_KERN_MEMORY_NONE);\n",
        "\t(void) mach_vm_allocate_kernel(map, &scratch_addr, map_page_size, VM_FLAGS_ANYWHERE, VM_KERN_MEMORY_NONE);\n"
        "\t" + (T % "v317 scratch ok") + "\n",
        "v317: after scratch alloc",
    )
    s = sub(
        s,
        '\t\t\tprintf("load_init_program: attempting to load /sbin/launchd\\n");\n'
        '\t\t\terror = load_init_program_at_path(p, (user_addr_t)scratch_addr, "/sbin/launchd", init_envp);\n',
        '\t\t\tprintf("load_init_program: attempting to load /sbin/launchd\\n");\n'
        "\t\t\t" + (T % "v317 launchd call") + "\n"
        '\t\t\terror = load_init_program_at_path(p, (user_addr_t)scratch_addr, "/sbin/launchd", init_envp);\n'
        "\t\t\t" + (TU % ("v317 launchd ret", "error")) + "\n",
        "v317: launchd exec",
    )
    write(F, s)
    print("kern_exec.c: v317 load_init_program probes installed")

print("v317 patch complete")
