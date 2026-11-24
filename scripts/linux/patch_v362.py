#!/usr/bin/env python3
"""g0245d v362 -- pinpoint the exact TLB-flush call that freezes pmap_switch.

v361 photo (21:35): status=`v349 vs pmap`, last trace=`v357 s6`.  That means the
run never reached execve; it froze in vm_map_switch -> pmap_switch_internal at
the `do_shared_region_flush` block (pmap.c:4565).  With __ARM_RANGE_TLBI__=1
(H13.h:82), s6 is followed by ARM range-TLBI instructions
(flush_core_tlb_allrange_async / flush_core_tlb_async) -- unsupported/suspect on
msm8996.  Earlier rounds sometimes passed s6->s9 (heisenbug).

v362: add status-row checkpoints around each flush call between s6 and s9:
  v362 s6a -- right after s6 (entering shared-region flush)
  v362 s6b -- after flush_core_tlb_allrange_async (range TLBI)
  v362 s6c -- after flush_core_tlb_async (full TLBI fallback)
  v362 s7a -- after pmap_flush_core_tlb_asid_async (ASID TLBI)
  v362 s8a -- after sync_tlb_flush_local (the barrier)
  v362 s9a -- after pmap_switch_user_ttb (TTBR switch)
Last visible status = the last flush that RETURNED; the next one is the freeze.
Additive only (traces untouched), no behavior change.

CUMULATIVE + IDEMPOTENT over v361.  Anchors are unique in pmap.c.
No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
if not os.path.isfile(PMAPC):
    sys.exit("required file not found: %s" % PMAPC)
MARK = "v362 s6a"
s = open(PMAPC, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v362: already applied -- skip")
    sys.exit(0)

def st(label):
    return ('\t{ extern void g0245d_status(const char *);\n'
            '\t  g0245d_status("%s"); }\n' % label)

# Limit edits to the s6..s9 slice so identical flush lines elsewhere are safe.
i0 = s.index('g0245d_tracev("v357 s6"')
i1 = s.index('g0245d_tracev("v357 s9"') + len('g0245d_tracev("v357 s9", (unsigned long long)(uintptr_t)pmap); }')
head, mid, tail = s[:i0], s[i0:i1], s[i1:]

def after_once(text, anchor, ins, label):
    c = text.count(anchor)
    if c != 1:
        sys.exit("patch_v362: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(anchor, anchor + ins, 1)

# s9a: after the s9 trace block (in mid, since the slice includes the s9 line)
S9 = 'g0245d_tracev("v357 s9", (unsigned long long)(uintptr_t)pmap); }'
mid = after_once(mid, S9, st("v362 s9a"), "s9a")

# s6a: after the s6 trace block (line ends with `); }`)
mid = after_once(mid, 'g0245d_tracev("v357 s6", (unsigned long long)(uintptr_t)pmap); }',
                 st("v362 s6a"), "s6a")
# s6b: after range-TLBI call (first flush_core_tlb_allrange_async in this slice)
mid = after_once(mid,
    'flush_core_tlb_allrange_async(generate_rtlbi_param((ppnum_t)npages_prev, 0, last_nested_region_addr, page_shift_prev));',
    st("v362 s6b"), "s6b")
# s6c: after full-TLBI calls (2 in slice: #if range else + #else). Mark both.
full = 'flush_core_tlb_async();'
if mid.count(full) != 2:
    sys.exit("patch_v362: full-TLBI count in slice=%d (want 2)" % mid.count(full))
mid = mid.replace(full, full + st("v362 s6c"))
# s7a: after ASID TLBI
mid = after_once(mid, 'pmap_flush_core_tlb_asid_async(pmap);',
                 st("v362 s7a"), "s7a")
# s8a: after the barrier
mid = after_once(mid, 'sync_tlb_flush_local();',
                 st("v362 s8a"), "s8a")
open(PMAPC, "w", encoding="utf-8").write(head + mid + tail)
print("patch_v362: s6a/s6b/s6c/s7a/s8a/s9a status probes added in s6..s9 slice")
print("patch_v362: done")
