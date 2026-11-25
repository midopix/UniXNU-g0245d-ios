#!/usr/bin/env python3
"""g0245d v374 -- bisect the s1b -> s9a window inside pmap_switch_internal().

v373 photo (16:31:22): status=`v364 s1b`; ring tail 8872 `v356 post`, with
`v371 ttep 0x9619d000/asid 0x0` and `v371 ttep 0x970bc000/asid 0x1`.
Both ttep values are non-zero, so the "switch onto a torn-down pmap (TTB=0)"
hypothesis is ruled out.  Several complete switch rounds are visible in the
ring (s1->s9->post), so pmap_switch_internal() can return; the last round
reached s1b and produced no later status or ring entry.

v374 adds status sentinels across the remaining window, one per decision
point, immediately BEFORE the statement each describes:

  c0 : before the ASID-overflow `if`
  c1 : inside that `if`, before `asid_index -= 1`
  c2 : after the `if`, before the mixed-page-size TCR check
  c3 : before the `break_before_make && !pmap_user_ttb_is_clear()` block
  c4 : before the shared-region flush block
  c5 : before the `do_asid_flush` block
  c6 : before the sync-flush block
  c7 : immediately before pmap_switch_user_ttb()

Last visible status = deepest checkpoint reached.  c1 is conditional; when
the ASID branch is not taken, status goes from c0 straight to c2 (which is
unconditional), so the reading stays unambiguous.

CUMULATIVE + IDEMPOTENT over v373.  Only pmap.c is touched; no behavior change.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
F = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
if not os.path.isfile(F):
    sys.exit("required file not found: %s" % F)

s = open(F, encoding="utf-8", errors="replace").read()
if "v374 c7" in s:
    print("patch_v374: already applied -- skip")
    sys.exit(0)


def st(label):
    return ('\t{ extern void g0245d_status(const char *);\n'
            '\t  g0245d_status("%s"); }\n' % label)


def before_once(text, anchor, ins, label):
    c = text.count(anchor)
    if c != 1:
        sys.exit("patch_v374: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(anchor, ins + anchor, 1)


# c0: immediately before the ASID-overflow if, right after v364 s1b
A0 = '\tif ((pmap_max_asids > MAX_HW_ASIDS) && (asid_index > 0)) {\n'
s = before_once(s, A0, st("v374 c0"), "c0")

# c1: inside that if, before the decrement
A1 = (A0 + '\t\tasid_index -= 1;\n')
s = before_once(s, A1, st("v374 c1"), "c1")

# c2: after the if closes, before the mixed-page-size TCR comparison
A2 = ('#if __ARM_MIXED_PAGE_SIZE__\n'
      '\tif (pt_attr->pta_tcr_value != get_tcr()) {\n')
s = before_once(s, A2, st("v374 c2"), "c2")

# c3: before the break_before_make / clear-user-ttb block
A3 = '\tif (__improbable(break_before_make && !pmap_user_ttb_is_clear())) {\n'
s = before_once(s, A3, st("v374 c3"), "c3")

# c4: before the shared-region flush block (comment is unique)
A4 = ("\t/* If we're switching to a different nested pmap (i.e. shared region), we'll need\n")
s = before_once(s, A4, st("v374 c4"), "c4")

# c5: before the ASID flush block
A5 = '\tif (__improbable(do_asid_flush)) {\n'
s = before_once(s, A5, st("v374 c5"), "c5")

# c6: before the sync flush block
A6 = '\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n'
s = before_once(s, A6, st("v374 c6"), "c6")

# c7: immediately before the TTBR switch -- the most important checkpoint
A7 = '\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n'
s = before_once(s, A7, st("v374 c7"), "c7")

open(F, "w", encoding="utf-8").write(s)
print("patch_v374: pmap.c s1b->s9a window checkpoints c0..c7 added")
print("patch_v374: done")
