#!/usr/bin/env python3
"""g0245d v316 -- bisect spec_strategy around the strategy dispatch.

v315 verdict (photo 09:37): the screen shows ONLY
    8687 v313 unmap call / 8688 v314 unmap ok / 8689 v314 resid ok
    8690 v314 biodone call / 8691 v314 biodone ok
and no v315 probe at all.  Since `v303 mc vfs ret` (mount_common, right after
VFS_MOUNT) also never printed, the freeze is between mdevstrategy returning and
VFS_MOUNT returning -- i.e. in mdevstrategy's CALLER.

The caller is spec_strategy() (spec_vnops.c:2447), which dispatches at line
2671 and then immediately calls microuptime(&bp->b_timestamp_tv).  That is the
prime suspect: time/uptime machinery on this early mockfs path, the same family
of problem as the v212/v213 WFE/timer walls.

v316 probes: entry, before dispatch, after dispatch, after microuptime, and
before return -- so the next photo names the exact statement.

Idempotent.  Run on the tree that already has v315 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v316.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

F = os.path.join(WORK, "bsd/miscfs/specfs/spec_vnops.c")
MARK = "v316 spec enter"


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

s = read(F)
if MARK in s:
    print("spec_vnops.c: already v316")
else:
    s = sub(
        s,
        "\tbp = ap->a_bp;\n\tbdev = buf_device(bp);\n\tmp = buf_vnode(bp)->v_mount;\n\tbap = &bp->b_attr;\n",
        "\tbp = ap->a_bp;\n\tbdev = buf_device(bp);\n\tmp = buf_vnode(bp)->v_mount;\n\tbap = &bp->b_attr;\n"
        "\t" + (T % "v316 spec enter") + "\n",
        "v316: spec_strategy entry",
    )
    s = sub(
        s,
        "\tstrategy_ret = (*(strategy_fcn_ret_t*)bdevsw[major(bdev)].d_strategy)(bp);\n",
        "\t" + (T % "v316 dispatch call") + "\n"
        "\tstrategy_ret = (*(strategy_fcn_ret_t*)bdevsw[major(bdev)].d_strategy)(bp);\n"
        "\t" + (T % "v316 dispatch ret") + "\n",
        "v316: around dispatch",
    )
    s = sub(
        s,
        "\tmicrouptime(&bp->b_timestamp_tv);\n",
        "\t" + (T % "v316 uptime call") + "\n\tmicrouptime(&bp->b_timestamp_tv);\n\t" + (T % "v316 uptime ok") + "\n",
        "v316: around microuptime",
    )
    s = sub(
        s,
        "\t\tthrottle_info_set_initial_window(ut, throttle_info, TRUE, isssd);\n\t}\n\treturn 0;\n}",
        "\t\tthrottle_info_set_initial_window(ut, throttle_info, TRUE, isssd);\n\t}\n\t" + (T % "v316 spec done") + "\n\treturn 0;\n}",
        "v316: before return",
    )
    write(F, s)
    print("spec_vnops.c: v316 spec_strategy probes installed")

print("v316 patch complete")
