#!/usr/bin/env python3
"""g0245d v357 -- bisect INSIDE pmap_switch_internal with stage probes.

v356 photo: trace ends at `v356 pre`, no `v356 post`/`v356 sdone`,
status `v349 vs pmap` -> freeze is INSIDE pmap_switch_internal().

KEY: MARK_AS_PMAP_TEXT is EMPTY when XNU_MONITOR=0 (pmap.h:815).  This target
is XNU_MONITOR=0 (v356 binary: pmap_switch_ppl=0, pmap_switch_internal=2),
so pmap_switch_internal is ordinary text and console probes are SAFE here.

Strategy: slice out the pmap_switch_internal() function body, insert 8 stage
probes inside that slice only (so common anchors like validate_pmap_mutable
cannot match other functions), then write the slice back.

  v357 s1 before validate_pmap_mutable  (function entry)
  v357 s2 after  asid_index -= 1
  v357 s3 after  pmap_update_plru(asid_index)
  v357 s4 after  cpu_sw_asids[asid_index] = new_sw_asid
  v357 s5 before pmap_clear_user_ttb_internal() branch
  v357 s6 before do_shared_region_flush TLBI block
  v357 s7 before do_asid_flush TLBI block
  v357 s8 before sync_tlb_flush_local()
  v357 s9 before pmap_switch_user_ttb() (final step)

Last printed stage in the photo pinpoints the hanging block.

CUMULATIVE + IDEMPOTENT over v356 (STEP1-3) for either bring-up line.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
if not os.path.isfile(PMAPC):
    sys.exit("pmap.c not found: %s" % PMAPC)
s = open(PMAPC, encoding="utf-8", errors="replace").read()
changed = False

PROBE = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
         '\t  g0245d_tracev("%s", (unsigned long long)(uintptr_t)pmap); }\n')

# ---------------------------------------------------------------- STEP 1 --
OLD = ("\tif ((size < PAGE_SIZE) && (size != PMAP_ROOT_ALLOC_SIZE)) {\n"
       "\t\tsize = PAGE_SIZE;\n\t}\n")
NEW = ("\tif (size < PAGE_SIZE) {\n"
       "\t\t/* g0245d v354..v357: roots must be granule aligned. */\n"
       "\t\tsize = PAGE_SIZE;\n\t}\n")
if s.count(OLD) == 2:
    s = s.replace(OLD, NEW); changed = True
    print("STEP1: dev line -- root carve-up removed")
elif "g0245d v354" in s or "roots must be granule aligned" in s:
    print("STEP1: alignment fix already present -- skip")
else:
    print("STEP1: WARNING unexpected root count=%d; untouched" % s.count(OLD))

# ---------------------------------------------------------------- STEP 2 --
if "v355 asid" in s:
    print("STEP2: v355 ASID probes present -- skip")
else:
    A = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
         '\t  g0245d_tracev("v349 pmap ttep", (unsigned long long)(uintptr_t)new_pmap->ttep);\n'
         '\t  g0245d_tracev("v349 pmap asid", (unsigned long long)(uintptr_t)new_pmap->hw_asid); }\n')
    B = A + ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
             '\t  extern uint32_t pmap_max_asids;\n\t  extern int pmap_asid_plru;\n'
             '\t  g0245d_tracev("v355 asid", (unsigned long long)new_pmap->hw_asid);\n'
             '\t  g0245d_tracev("v355 maxasid", (unsigned long long)pmap_max_asids);\n'
             '\t  g0245d_tracev("v355 plru", (unsigned long long)pmap_asid_plru);\n'
             '\t  g0245d_tracev("v355 pmap", (unsigned long long)(uintptr_t)new_pmap);\n'
             '\t  g0245d_tracev("v355 kern", (unsigned long long)(uintptr_t)kernel_pmap); }\n')
    if s.count(A) != 1:
        sys.exit("STEP2: expected 1 v349 block, found %d" % s.count(A))
    s = s.replace(A, B, 1); changed = True
    print("STEP2: appended v355 ASID probes")

# ---------------------------------------------------------------- STEP 3 --
if "v356 spmap" in s:
    print("STEP3a: present -- skip")
else:
    A3 = ('\tthread_t        thread)\n{\n\tpmap_switch(pmap);\n#if __ARM_USER_PROTECT__\n')
    B3 = ('\tthread_t        thread)\n{\n' + (PROBE % "v356 spmap") +
          '\tpmap_switch(pmap);\n' + (PROBE % "v356 sdone") + '#if __ARM_USER_PROTECT__\n')
    if s.count(A3) != 1:
        sys.exit("STEP3a: expected 1 pmap_set_pmap body, found %d" % s.count(A3))
    s = s.replace(A3, B3, 1); changed = True
    print("STEP3a: added spmap/sdone")
NEW_MARK = (PROBE % "v356 pre") + '#if XNU_MONITOR\n'
if NEW_MARK in s:
    print("STEP3b: present -- skip")
else:
    if "v356 pre" in s:
        s = s.replace(PROBE % "v356 pre", "").replace(PROBE % "v356 post", "")
        changed = True
    C3 = ('#if XNU_MONITOR\n\tpmap_switch_ppl(pmap);\n#else\n'
          '\tpmap_switch_internal(pmap);\n#endif\n')
    D3 = (PROBE % "v356 pre") + C3 + (PROBE % "v356 post")
    if s.count(C3) != 1:
        sys.exit("STEP3b: expected 1 dispatch block, found %d" % s.count(C3))
    s = s.replace(C3, D3, 1); changed = True
    print("STEP3b: added unconditional pre/post")

# ---------------------------------------------------------------- STEP 4 --
# Slice out pmap_switch_internal's body.  Its definition is unique.
start = s.find('pmap_switch_internal(\n\tpmap_t pmap)\n{')
if start < 0:
    sys.exit("STEP4: cannot find pmap_switch_internal definition")
brace = s.find('{', start)
depth = 0
end = -1
for i in range(brace, len(s)):
    if s[i] == '{': depth += 1
    elif s[i] == '}':
        depth -= 1
        if depth == 0:
            end = i + 1
            break
if end < 0:
    sys.exit("STEP4: cannot find matching brace")
body = s[brace:end]
print("STEP4: pmap_switch_internal body = %d bytes" % len(body))

def ins_in_body(anchor, label, tag):
    global body, changed
    if ('"' + label + '"') in body:
        print("  %s: present -- skip" % tag)
        return
    n = body.count(anchor)
    if n != 1:
        sys.exit("  %s: expected 1 anchor in body, found %d -- ABORT" % (tag, n))
    body = body.replace(anchor, anchor + (PROBE % label), 1)
    changed = True
    print("  %s: inserted" % tag)

ins_in_body('\tvalidate_pmap_mutable(pmap);\n', 'v357 s1', 's1')
ins_in_body('\t\tasid_index -= 1;\n', 'v357 s2', 's2')
ins_in_body('\t\tpmap_update_plru(asid_index);\n', 'v357 s3', 's3')
ins_in_body('\t\t\tcpu_data_ptr->cpu_sw_asids[asid_index] = new_sw_asid;\n', 'v357 s4', 's4')
ins_in_body('\tif (__improbable(break_before_make && !pmap_user_ttb_is_clear())) {\n', 'v357 s5', 's5')
ins_in_body('\tif (__improbable(do_shared_region_flush)) {\n', 'v357 s6', 's6')
ins_in_body('\tif (__improbable(do_asid_flush)) {\n', 'v357 s7', 's7')
ins_in_body('\tif (__improbable(do_asid_flush || do_shared_region_flush || do_commpage_flush)) {\n', 'v357 s8', 's8')
ins_in_body('\tpmap_switch_user_ttb(pmap, cpu_data_ptr);\n', 'v357 s9', 's9')

s = s[:brace] + body + s[end:]

if changed:
    open(PMAPC, "w", encoding="utf-8", errors="replace").write(s)
    print("patch_v357: written")
else:
    print("patch_v357: nothing changed (already fully applied)")
