#!/usr/bin/env python3
"""g0245d v356 -- bisect the freeze around pmap_switch() / pmap_switch_ppl().

WHY (HANDOFF 14.19.9/14.19.10):  v355's five ASID probes all printed (last
trace label = `v355 kern`), ttep is aligned (0x976ab000, low 12 bits 0),
but status stays at `v349 vs pmap` and no later trace appears.  The freeze
is therefore inside pmap_set_pmap() -> pmap_switch().

The board defines XNU_MONITOR=1 (pexpert/pexpert/arm64/board_config.h), so
pmap_switch() dispatches to pmap_switch_ppl() (PPL text), NOT to
pmap_switch_internal().  PPL text cannot call the framebuffer console
(v351 lesson), so the only safe next step is ordinary-code probes placed
immediately before/after the PPL dispatch.  v356 adds four READ-ONLY
tracev probes, all in ordinary (non-PPL) text:

    v356 spmap  - pmap_set_pmap(): before pmap_switch(pmap)
    v356 sdone  - pmap_set_pmap(): after  pmap_switch(pmap)
    v356 pre    - pmap_switch():   before pmap_switch_ppl(pmap)
    v356 post   - pmap_switch():   after  pmap_switch_ppl(pmap)

Photo interpretation:
    spmap + sdone + pre + post  -> freeze is later; re-locate
    spmap + pre, no post        -> CONFIRMED frozen inside PPL dispatch
    spmap, no pre               -> frozen between pmap_set_pmap and switch
    no spmap                    -> earlier than expected; re-check v355

DUAL-LINE COMPATIBILITY
-----------------------
The two bring-up lines share pmap.c but differ in applied versions:

  * dev line   (Windows/WSL host): v349 + v350 + v351, no v354 alignment
                fix, no v352..v354 probes.
  * ubuntu line(Ubuntu builder):   v349 + v352 + v353 + v354, has the
                alignment fix, lacks the dev line's v350 switch-back guard.

v356 is fully cumulative and individually idempotent, so it can be applied
to EITHER line directly (the Ubuntu line does not need a separate v355 run):

  STEP 1 - root alignment (dev line only; skip if already fixed)
  STEP 2 - v355 ASID read probes (shared v349 probe block anchor)
  STEP 3 - v356 bisect probes (pmap_set_pmap / pmap_switch anchors, which
           neither v352..v354 nor v355 modify)

Every step detects its own already-applied state; re-running is a no-op.
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
OLD = ("\tif ((size < PAGE_SIZE) && (size != PMAP_ROOT_ALLOC_SIZE)) {\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")
NEW = ("\tif (size < PAGE_SIZE) {\n"
       "\t\t/* g0245d v354/v355/v356: roots must be granule aligned.  Carving\n"
       "\t\t * a sub-page root off a shared page hands out 2 KB-aligned roots\n"
       "\t\t * like 0x96c51800; TTBR0 faults every user translation on such a\n"
       "\t\t * root (ESR 0x96000145) until the kernel stack overflows. */\n"
       "\t\tsize = PAGE_SIZE;\n"
       "\t}\n")
n = s.count(OLD)
if n == 2:
    s = s.replace(OLD, NEW)
    changed = True
    print("patch_v356 STEP1: dev line -- root carve-up removed (alloc+dealloc)")
elif ("roots must be granule aligned" in s or
      "v354: roots must be granule aligned" in s or "g0245d v354" in s):
    print("patch_v356 STEP1: alignment fix already present (ubuntu line) -- skip")
else:
    print("patch_v356 STEP1: WARNING -- unexpected root snippet count=%d; "
          "leaving alignment untouched" % n)

# ---------------------------------------------------------------- STEP 2 --
if "v355 asid" in s:
    print("patch_v356 STEP2: v355 ASID probes already applied -- skip")
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
        sys.exit("patch_v356 STEP2: expected 1 shared v349 probe block, found %d" % m)
    s = s.replace(A, B, 1)
    changed = True
    print("patch_v356 STEP2: appended v355 ASID read probes after v349 block")

# ---------------------------------------------------------------- STEP 3a --
# pmap_set_pmap(): the exact anchor uses the closing signature so that the
# other `pmap_switch(pmap)` call site (pmap.c:13927) cannot match.
if "v356 spmap" in s:
    print("patch_v356 STEP3a: pmap_set_pmap probes already applied -- skip")
else:
    A3 = ('\tthread_t        thread)\n'
          '{\n'
          '\tpmap_switch(pmap);\n'
          '#if __ARM_USER_PROTECT__\n')
    B3 = ('\tthread_t        thread)\n'
          '{\n'
          '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v356 spmap", (unsigned long long)(uintptr_t)pmap); }\n'
          '\tpmap_switch(pmap);\n'
          '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v356 sdone", (unsigned long long)(uintptr_t)pmap); }\n'
          '#if __ARM_USER_PROTECT__\n')
    m = s.count(A3)
    if m != 1:
        sys.exit("patch_v356 STEP3a: expected 1 pmap_set_pmap body, found %d" % m)
    s = s.replace(A3, B3, 1)
    changed = True
    print("patch_v356 STEP3a: added v356 spmap/sdone around pmap_switch()")

# ---------------------------------------------------------------- STEP 3b --
# XNU_MONITOR is 0 on this target (the board_config.h `= 1` defines are for
# Apple T8101/T8103 boards and do not apply to msm8996).  The build therefore
# uses pmap_switch_internal(), and probes placed INSIDE `#if XNU_MONITOR`
# are compiled out.  Put pre/post OUTSIDE the conditional so they are always
# present, whatever the monitor setting.
NEW_MARK = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
            '\t  g0245d_tracev("v356 pre", (unsigned long long)(uintptr_t)pmap); }\n'
            '#if XNU_MONITOR\n')
if NEW_MARK in s:
    print("patch_v356 STEP3b: unconditional v356 pre/post already present -- skip")
else:
    if "v356 pre" in s:
        print("patch_v356 STEP3b: normalizing v356 pre/post placement")
        OLD_BLK = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
                   '\t  g0245d_tracev("v356 pre", (unsigned long long)(uintptr_t)pmap); }\n')
        OLD_BLK2 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
                    '\t  g0245d_tracev("v356 post", (unsigned long long)(uintptr_t)pmap); }\n')
        s = s.replace(OLD_BLK, "").replace(OLD_BLK2, "")
        changed = True
    C3 = ('#if XNU_MONITOR\n'
          '\tpmap_switch_ppl(pmap);\n'
          '#else\n'
          '\tpmap_switch_internal(pmap);\n'
          '#endif\n')
    D3 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v356 pre", (unsigned long long)(uintptr_t)pmap); }\n'
          + C3 +
          '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v356 post", (unsigned long long)(uintptr_t)pmap); }\n')
    m = s.count(C3)
    if m != 1:
        sys.exit("patch_v356 STEP3b: expected 1 pmap_switch dispatch block, found %d" % m)
    s = s.replace(C3, D3, 1)
    changed = True
    print("patch_v356 STEP3b: added unconditional v356 pre/post around the dispatch")

if changed:
    open(PMAPC, "w", encoding="utf-8", errors="replace").write(s)
    print("patch_v356: written")
else:
    print("patch_v356: nothing changed (already fully applied)")
