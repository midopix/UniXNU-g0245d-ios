#!/usr/bin/env python3
"""g0245d v365 -- workaround: skip the shared-region full TLBI that hangs.

Photo evidence (22:33, two rounds): status = `v362 s6a` on BOTH rounds (hb
9092/9049 and 9832/9949 -- different boots, same freeze).  s6a is written right
after the `do_shared_region_flush` block is entered; the next checkpoint s6c
(after flush_core_tlb_async()) never appears.  flush_core_tlb_async() is a
single `tlbi vmalle1` instruction (osfmk/arm64/tlb.h:81).  Combined with earlier
rounds (v361 froze at s6, v362/v363 rounds sometimes passed), the mode verdict:
**`tlbi vmalle1` hangs intermittently on msm8996** (timing-sensitive; possibly
an errata / implementation quirk).

v365: force do_shared_region_flush = false so the shared-flush block (and its
`tlbi vmalle1`) is skipped.  ASID flush (s7) and sync barrier (s8) remain, so
TLB hygiene for the user pmap is still partially maintained via ASID tagging.
Additive probes keep every later checkpoint visible.

CUMULATIVE + IDEMPOTENT over v364.  Anchor unique in pmap.c.
No machine-specific paths.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
if not os.path.isfile(PMAPC):
    sys.exit("required file not found: %s" % PMAPC)
MARK = "v365 noSR"
s = open(PMAPC, encoding="utf-8", errors="replace").read()
if MARK in s:
    print("patch_v365: already applied -- skip")
    sys.exit(0)

OLD = ('\tbool do_shared_region_flush = ((pmap != kernel_pmap) && '
       '(last_nested_pmap != NULL) && (pmap->nested_pmap != last_nested_pmap));\n'
       '\tbool break_before_make = do_shared_region_flush;\n')
NEW = ('\t/* g0245d v365: `tlbi vmalle1` (flush_core_tlb_async) hangs '
       'intermittently on\n'
       '\t * msm8996 (photo verdict: two rounds froze at v362 s6a, i.e. inside\n'
       '\t * this block).  Disable the shared-region flush; ASID flush (s7) '
       'still\n'
       '\t * runs and ASID tagging keeps user mappings isolated for now. */\n'
       '\tbool do_shared_region_flush = false; /* v365 noSR workaround */\n'
       '\tbool break_before_make = do_shared_region_flush;\n'
       '\t{ extern void g0245d_status(const char *);\n'
       '\t  g0245d_status("v365 noSR"); }\n')
c = s.count(OLD)
if c != 1:
    sys.exit("patch_v365: need 1 do_shared_region_flush block, found %d" % c)
s = s.replace(OLD, NEW, 1)
open(PMAPC, "w", encoding="utf-8").write(s)
print("patch_v365: do_shared_region_flush disabled (v365 noSR)")
print("patch_v365: done")
