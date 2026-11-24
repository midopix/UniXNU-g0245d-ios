#!/usr/bin/env python3
"""g0245d v307 -- heartbeat marker to settle 'is the new kernel running at all'.

Background (2026-11-24 stock verdict):
  stock-boot-trimmed.img flashed to boot and rebooted -> stock Android
  enumerated on USB (05c6:9039) within 30 s.  Both flash AND the load path
  are VALID: the bootloader does load what fastboot writes.

  So the v305/v306 mystery flips: the new kernels were probably loaded and
  running all along, freezing at the SAME spot as v304 (dm kalloc ok).
  Because the code path is deterministic, the trace_seq climbs to the same
  8567 and the final screen is byte-identical to v304's last frame.  The
  v306 BOOT SENTINEL printed first and was scrolled off screen by the 8500
  subsequent trace lines; the v305 pre-lock probe sits AFTER the freeze
  point, so it never prints.  Both "the kernel didn't change" symptoms are
  explained without any bootloader fault.

v307 (heartbeat marker, one string):
  arm_init.c g0245d_hb(): `hb ` -> `hb307 `.  The heartbeat row is redrawn
  in place on every trace and never scrolls.  Verdict by photo:
    `hb307 ...`  => the new kernel IS running (resume devfs_mount work)
    `hb 8567...` => the kernel really dies before its first trace
  Idempotent.  Run on the tree that already has v306 applied.
    XNU_WORK=<.../.cache/xnu-work> python3 patch_v307.py
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM_INIT = os.path.join(WORK, "osfmk/arm/arm_init.c")
MARK = "hb307"


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


s = read(ARM_INIT)
if MARK in s:
    print("arm_init.c: already v307")
else:
    s = sub(
        s,
        'g0245d_con_puts("hb ");',
        'g0245d_con_puts("hb307 "); /* g0245d v307: verdict marker */',
        "v307: heartbeat marker",
    )
    write(ARM_INIT, s)
    print("arm_init.c: v307 heartbeat marker installed")

print("v307 patch complete")
