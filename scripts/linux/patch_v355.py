#!/usr/bin/env python3
"""g0245d v355 -- align roots on the dev line + read the incoming ASID.

WHY (HANDOFF 14.19.6/14.19.7):  the v354 photo's trace ring ends at
`v354 ttep low` (entry probe in pmap_switch_user) and never reaches
`v352 switch done` (printed right after pmap_set_pmap()).  pmap_set_pmap()
-> pmap_switch() -> pmap_switch_internal() is a MARK_AS_PMAP_TEXT (PPL)
function.  Inside it:

    uint16_t asid_index = pmap->hw_asid;
    if ((asid_index == 0) && (pmap != kernel_pmap)) panic("invalid ASID");
    ...
    if ((pmap_max_asids > MAX_HW_ASIDS) && (asid_index > 0)) {
        asid_index -= 1;   /* PLRU virtualisation */
        ...
    }

The second switch (init task's own map) uses ASID 1.  If PLRU subtracts one,
asid_index becomes 0, the invalid-ASID panic fires deep in PPL text, and a
panic there cannot reach the framebuffer console -> photo freezes with no
`switch done`.  v355 prints the raw values from ORDINARY code, before the
PPL call, so the photo settles the hypothesis in one shot:

    v355 asid    - new_pmap->hw_asid   (incoming ASID == 1?)
    v355 maxasid - pmap_max_asids
    v355 plru    - pmap_asid_plru      (1 => the -=1 branch is live)
    v355 pmap    - new_pmap pointer
    v355 kern    - kernel_pmap pointer (pmap != kernel_pmap ?)

Reads only; no behaviour change.  The fix itself comes in v356.

DUAL-LINE COMPATIBILITY  (the core requirement)
-----------------------------------------------
Two bring-up lines share pmap.c but differ in applied versions:

  * dev line   (this Windows/WSL host): v349 + v350 + v351.  It does NOT
    have the v354 root-alignment fix -> it would regress to the v353
    translation-fault storm if built as-is.
  * ubuntu line(the Ubuntu builder, built v354): v349 + v352 + v353 + v354. It HAS
    the alignment fix, lacks the dev line's v350 switch-back guard.

v355 does two independent, individually-idempotent things:

  STEP 1 - root alignment: if the OLD carve-up snippet is present (dev
    line), replace it with the page-rounding fix, exactly as patch_v354
    did on the ubuntu line.  If the v354 fix is already there (ubuntu
    line), skip.  This makes BOTH lines carry the alignment fix, so the
    ASID read is not masked by the v353 storm.
  STEP 2 - ASID read probes: append after the v349 probe block, which is
    the ONE anchor both lines share untouched.  Never touch the A0
    `thread->map = new_map;\n\tpmap_set_pmap(...)` site -- v352 rewrote
    it differently on the ubuntu line.

Idempotent: re-running on either line reports what is already present.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
if not os.path.isfile(PMAPC):
    sys.exit("pmap.c not found: %s" % PMAPC)

s = open(PMAPC, encoding="utf-8", errors="replace").read()
changed = False

# ---------------------------------------------------------------- STEP 1 --
# root alignment (dev line only).  Identical snippet in alloc + deallocate.
OLD = ("\tif ((size < PAGE_SIZE) && (size != PMAP_ROOT_ALLOC_SIZE)) {\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")
NEW = ("\tif (size < PAGE_SIZE) {\n"
       "\t\t/* g0245d v354/v355: roots must be granule aligned.  Carving a\n"
       "\t\t * sub-page root off a shared page hands out 2 KB-aligned roots\n"
       "\t\t * like 0x96c51800; TTBR0 faults every user translation on such\n"
       "\t\t * a root (ESR 0x96000145) until the kernel stack overflows.\n"
       "\t\t * Round every root up to a full page; the unused tail stays 0. */\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")
n = s.count(OLD)
if n == 2:
    s = s.replace(OLD, NEW)
    changed = True
    print("patch_v355 STEP1: dev line -- root carve-up removed (alloc+dealloc)")
elif "roots must be granule aligned" in s or "v354: roots must be granule aligned" in s:
    print("patch_v355 STEP1: alignment fix already present (ubuntu line) -- skip")
elif n == 0 and "g0245d v354" in s:
    print("patch_v355 STEP1: v354 fix present (comment) -- skip")
else:
    print("patch_v355 STEP1: WARNING -- unexpected root snippet count=%d; "
          "leaving alignment untouched" % n)

# ---------------------------------------------------------------- STEP 2 --
MARK = "v355 asid"
if MARK in s:
    print("patch_v355 STEP2: ASID probes already applied -- skip")
else:
    A = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
         '\t  g0245d_tracev("v349 pmap ttep", (unsigned long long)(uintptr_t)new_pmap->ttep);\n'
         '\t  g0245d_tracev("v349 pmap asid", (unsigned long long)(uintptr_t)new_pmap->hw_asid); }\n')
    B = A + (
        '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
        '\t  extern uint32_t pmap_max_asids;\n'
        '\t  extern int pmap_asid_plru;\n'
        '\t  /* kernel_pmap is already declared in pmap.c -- do not redeclare. */\n'
        '\t  g0245d_tracev("v355 asid", (unsigned long long)new_pmap->hw_asid);\n'
        '\t  g0245d_tracev("v355 maxasid", (unsigned long long)pmap_max_asids);\n'
        '\t  g0245d_tracev("v355 plru", (unsigned long long)pmap_asid_plru);\n'
        '\t  g0245d_tracev("v355 pmap", (unsigned long long)(uintptr_t)new_pmap);\n'
        '\t  g0245d_tracev("v355 kern", (unsigned long long)(uintptr_t)kernel_pmap); }\n')
    m = s.count(A)
    if m != 1:
        sys.exit("patch_v355 STEP2: expected 1 shared v349 probe block, found %d" % m)
    s = s.replace(A, B, 1)
    changed = True
    print("patch_v355 STEP2: appended ASID read probes after v349 block")

if changed:
    open(PMAPC, "w", encoding="utf-8", errors="replace").write(s)
    print("patch_v355: written")
else:
    print("patch_v355: nothing changed (already fully applied)")
