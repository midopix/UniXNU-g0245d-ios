#!/usr/bin/env python3
"""g0245d v358 -- surface the EL1 data-abort FAR/PC on the status line.

v357 photo (19:50): pmap_switch FINALLY returned (v356 post present), status
advanced to `v342 b5 vmexec ok` (vm_map_exec() returned) -- then a storm of
`v328 ec 37` = ESR_EC_DABORT_EL1 (kernel data abort, proc_reg.h:1723).

Problem: v328's `v328 far` probe IS in the binary but is invisible in the
photo -- the 12-entry cap is consumed by the ec/far pairs and the far lines
sit in the glare zone / scroll off.  We cannot locate the fault without the
FAR (faulting address) and PC (faulting instruction).

v358: in sleh_synchronous(), right after the existing exception probe, print
ESR / FAR / PC as a *status* line (g0245d_status writes the LAST screen row,
which never scrolls and is not washed by the trace ring).  Once only -- status
is overwrite-style, so a single full capture is enough.

Two-line compatible sleh.c anchors:
  * dev line    : `g0245d_trace_u("v328 ec" ...)` block
  * Ubuntu line : patch_v352 rewrites `v351 esr/far/pc` -> `v352 esr/far/pc`
    (both are inside sleh_synchronous, ordinary code, console-safe).
We anchor on the stable `arm_saved_state_t * state = &context->ss;` line which
exists on both lines, and insert AFTER it (variables esr/far/state all live).

CUMULATIVE + IDEMPOTENT over v357 (STEP1-4) for either bring-up line.
"""
import os, sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PMAPC = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
SLEH  = os.path.join(W, "osfmk", "arm64", "sleh.c")
for f in (PMAPC, SLEH):
    if not os.path.isfile(f):
        sys.exit("required file not found: %s" % f)
s = open(PMAPC, encoding="utf-8", errors="replace").read()
changed = False

PROBE = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
         '\t  g0245d_tracev("%s", (unsigned long long)(uintptr_t)pmap); }\n')

# ---------------------------------------------------------------- STEP 1 -- (v354 align)
OLD = ("\tif ((size < PAGE_SIZE) && (size != PMAP_ROOT_ALLOC_SIZE)) {\n"
       "\t\tsize = PAGE_SIZE;\n\t}\n")
NEW = ("\tif (size < PAGE_SIZE) {\n"
       "\t\t/* g0245d v354..v358: roots must be granule aligned. */\n"
       "\t\tsize = PAGE_SIZE;\n\t}\n")
if s.count(OLD) == 2:
    s = s.replace(OLD, NEW); changed = True
    print("patch_v358 STEP1: root carve-up removed (dev line)")
elif s.count(OLD) == 0 and s.count("roots must be granule aligned") >= 1:
    # already aligned by an earlier v354/v355/v357 patch (comment text varies
    # across versions: "v354/v355", "v354..v357", etc.).  Recognize by marker.
    print("patch_v358 STEP1: root align already applied -- skip")
else:
    sys.exit("patch_v358 STEP1: unexpected root-carve anchor counts OLD=%d ALIGN=%d"
             % (s.count(OLD), s.count("roots must be granule aligned")))

# ---------------------------------------------------------------- STEP 2 -- (v355 ASID probes)
if "v355 asid" in s:
    print("patch_v358 STEP2: v355 ASID probes already present -- skip")
else:
    A2 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  extern uint32_t pmap_max_asids;\n'
          '\t  extern int pmap_asid_plru;\n'
          '\t  g0245d_tracev("v355 asid", (unsigned long long)new_pmap->hw_asid);\n'
          '\t  g0245d_tracev("v355 maxasid", (unsigned long long)pmap_max_asids);\n'
          '\t  g0245d_tracev("v355 plru", (unsigned long long)pmap_asid_plru);\n'
          '\t  g0245d_tracev("v355 pmap", (unsigned long long)(uintptr_t)new_pmap); }\n')
    # anchor on the v349 pmap-asid probe block after pmap_switch_user entry
    m = s.count("v349 pmap asid")
    if m != 1:
        sys.exit("patch_v358 STEP2: need 1 v349 pmap asid anchor, found %d" % m)
    idx = s.index("v349 pmap asid")
    line_end = s.index("\n", idx) + 1
    s = s[:line_end] + A2 + s[line_end:]
    changed = True
    print("patch_v358 STEP2: added v355 ASID probes after v349 block")

# ---------------------------------------------------------------- STEP 3 -- (v356 pre/post)
if "v356 pre" in s:
    print("patch_v358 STEP3: v356 pre/post already present -- skip")
else:
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
        sys.exit("patch_v358 STEP3: need 1 pmap_switch dispatch, found %d" % m)
    s = s.replace(C3, D3, 1); changed = True
    print("patch_v358 STEP3: added unconditional v356 pre/post")

# ---------------------------------------------------------------- STEP 4 -- (v357 stage probes)
if "v357 s9" in s:
    print("patch_v358 STEP4: v357 stage probes already present -- skip")
else:
    FSIG = "pmap_switch_internal("
    starts = [i for i in range(len(s)) if s.startswith(FSIG, i)]
    # function definition is the one followed by '(' ... '{' at column 0 form
    body = None
    for st in starts:
        brace = s.find("{", st)
        if brace < 0: continue
        # definition line typically 'pmap_switch_internal(\n' then args then '{'
        seg = s[st:brace]
        if "\n" in seg and ";" not in seg:
            body = brace; break
    if body is None:
        sys.exit("patch_v358 STEP4: cannot locate pmap_switch_internal body")
    end = s.find("\n}", body)
    func = s[body:end]
    stages = [
        ("v357 s1", "\tvalidate_pmap_mutable(pmap);\n", "after"),
        ("v357 s2", "asid_index -= 1;\n", "after"),
        ("v357 s3", "pmap_update_plru(asid_index);\n", "after"),
        ("v357 s9", "pmap_switch_user_ttb(", "before"),
    ]
    for label, anchor, where in stages:
        c = func.count(anchor)
        if c < 1:
            sys.exit("patch_v358 STEP4: anchor %r count=%d" % (anchor, c))
        p = PROBE % label
        if where == "after":
            ai = func.index(anchor) + len(anchor)
            func = func[:ai] + p + func[ai:]
        else:
            ai = func.index(anchor)
            func = func[:ai] + p + func[ai:]
    s = s[:body] + func + s[end:]
    changed = True
    print("patch_v358 STEP4: added v357 stage probes (s1,s2,s3,s9) in internal body")

if changed:
    open(PMAPC, "w", encoding="utf-8").write(s)
    print("patch_v358: wrote %s" % PMAPC)

# ---------------------------------------------------------------- STEP 5 -- (v358: status FAR/PC)
t = open(SLEH, encoding="utf-8", errors="replace").read()
V358_MARK = "v358 ec=%u esr=%x"
if V358_MARK in t:
    print("patch_v358 STEP5: sleh status probe already present -- skip")
else:
    # stable anchor: sleh_synchronous() declares `esr`, `far`, `state` in its
    # prologue.  Insert right after the local declarations so all three live.
    # We key on the exact dev-line declaration block; Ubuntu line (patch_v352)
    # keeps the same prologue (only the later esr/far/pc *probes* differ).
    A5 = ("void\nsleh_synchronous(arm_context_t *context, uint32_t esr, vm_offset_t far)\n"
          "{\n"
          "\tesr_exception_class_t  class   = ESR_EC(esr);\n"
          "\tarm_saved_state_t    * state   = &context->ss;\n"
          "\tthread_t               thread  = current_thread();\n")
    B5 = A5 + (
        "\t/* g0245d v358: print the fault on the STATUS row (never scrolls). */\n"
        "\t{ extern void g0245d_status(const char *);\n"
        "\t  static char v358buf[128];\n"
        "\t  snprintf(v358buf, sizeof(v358buf),\n"
        "\t      \"v358 ec=%u esr=%x far=%llx pc=%llx\",\n"
        "\t      (unsigned)ESR_EC(esr), (unsigned)esr,\n"
        "\t      (unsigned long long)(uintptr_t)far,\n"
        "\t      (unsigned long long)(uintptr_t)get_saved_state_pc(state));\n"
        "\t  g0245d_status(v358buf); }\n")
    c = t.count(A5)
    if c != 1:
        sys.exit("patch_v358 STEP5: need 1 sleh prologue anchor, found %d" % c)
    t = t.replace(A5, B5, 1)
    open(SLEH, "w", encoding="utf-8").write(t)
    print("patch_v358 STEP5: added v358 esr/far/pc status probe in sleh_synchronous")
print("patch_v358: done")
