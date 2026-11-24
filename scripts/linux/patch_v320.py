#!/usr/bin/env python3
"""g0245d v320 -- confirm load_init_program returned and probe post-bsd_init boot.

v319 verdict (photo 10:00) -- the milestone chain is now fully readable:
    8595 v311 statfs ret / 8596 v304 dm statfs ok
    8597 v303 mc vfs ret 0        <- devfs_mount returned 0
    8604 v300 km mc ret 0         <- mount_common returned 0
    8606 v300 dkm km ret 0        <- devfs_kernel_mount returned 0
    8607 v300 post devfs
    8608 v300 siginit call ... 8610 siginit done
    8611 v300 ubt call ... 8618 v300 ubt done
    8619 bsd calling mountroot_post_hook / 8620 bsd done
    8621 v248 bsd init done       <- bsd_init RETURNED
    8622 v319 lk enoent

bsd_init only returns after load_init_program() finishes without panicking --
and load_init_program panics if ALL init_programs paths fail.  So PID1's exec
did succeed (the v317/v319 lines just scrolled above 8621); the trailing
`lk enoent` is a later lookup in the post-bsd_init boot path.

v320 brackets the call site inside bsd_init (`v320 lip call` / `v320 lip done`)
and probes the four steps right after bsd_init() in kernel_bootstrap_thread
(kdebug_free_early_buf / serial_keyboard_init / vm_page_init_local_q /
vm_free_delayed_pages), so the next photo shows how far the boot got.

Idempotent.  Run on the tree that already has v319 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v320.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSD = os.path.join(WORK, "bsd/kern/bsd_init.c")
STARTUP = os.path.join(WORK, "osfmk/kern/startup.c")
MARK = "v320 lip call"


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

s = read(BSD)
if MARK in s:
    print("bsd_init.c: already v320")
else:
    s = sub(
        s,
        '\tbsd_init_kprintf("bsd_do_post - done");\n\n\tload_init_program(p);\n',
        '\tbsd_init_kprintf("bsd_do_post - done");\n\n'
        "\t" + (T % "v320 lip call") + "\n"
        "\tload_init_program(p);\n"
        "\t" + (T % "v320 lip done") + "\n",
        "v320: bracket load_init_program",
    )
    write(BSD, s)
    print("bsd_init.c: v320 load_init_program bracket installed")

s = read(STARTUP)
if "v320 kdbg ok" in s:
    print("startup.c: already v320")
else:
    s = sub(
        s,
        '\tbsd_init();\n\tg0245d_trace("v248 bsd init done");\n',
        '\tbsd_init();\n\tg0245d_trace("v248 bsd init done");\n\t' + (T % "v320 kdbg ok") + "\n",
        "v320: after bsd_init",
    )
    s = sub(
        s,
        "\tserial_keyboard_init();         /* Start serial keyboard if wanted */\n",
        "\t" + (T % "v320 serial kbd ok") + "\n\tserial_keyboard_init();         /* Start serial keyboard if wanted */\n",
        "v320: before serial_keyboard_init",
    )
    s = sub(
        s,
        "\tvm_page_init_local_q(machine_info.max_cpus);\n",
        "\t" + (T % "v320 vmpage ok") + "\n\tvm_page_init_local_q(machine_info.max_cpus);\n",
        "v320: before vm_page_init_local_q",
    )
    s = sub(
        s,
        "\tvm_free_delayed_pages();\n",
        "\t" + (T % "v320 delayed free ok") + "\n\tvm_free_delayed_pages();\n",
        "v320: before vm_free_delayed_pages",
    )
    write(STARTUP, s)
    print("startup.c: v320 post-bsd_init probes installed")

print("v320 patch complete")
