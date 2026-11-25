#!/usr/bin/env python3
"""g0245d v367: capture fault registers and shorten persistent status.

The v366 photos show post-switch DABORT. OCR of the panic PC maps near
IOTaskHasEntitlement+0x44, but FAR/PC are not legible in the long v358 row.
Add numeric trace records in the normal synchronous-abort path and a compact
status row. Also mark vm_map_switch return for ordering against exec probes.
"""
import os, sys
W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
SLEH = os.path.join(W, "osfmk", "arm64", "sleh.c")
VM = os.path.join(W, "osfmk", "vm", "vm_map.c")
for p in (SLEH, VM):
    if not os.path.isfile(p):
        sys.exit("required file not found: " + p)
s = open(SLEH, encoding="utf-8", errors="replace").read()
mark = '"v367 far"'
if mark not in s:
    anchor = '\t  g0245d_status(v358buf); }\n'
    if s.count(anchor) != 1:
        sys.exit("patch_v367: v358 status anchor count != 1")
    replacement = '''\t\t  { extern void g0245d_tracev(const char *, unsigned long long);\n\t\t    g0245d_tracev("v367 esr", (unsigned long long)esr);\n\t\t    g0245d_tracev("v367 far", (unsigned long long)(uintptr_t)far);\n\t\t    g0245d_tracev("v367 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state));\n\t\t    g0245d_tracev("v367 x0", (unsigned long long)get_saved_state_reg(state, 0));\n\t\t    g0245d_tracev("v367 x1", (unsigned long long)get_saved_state_reg(state, 1)); }\n\t\t  snprintf(v358buf, sizeof(v358buf), "E%u F=%llx P=%llx",\n\t\t      (unsigned)ESR_EC(esr), (unsigned long long)(uintptr_t)far,\n\t\t      (unsigned long long)(uintptr_t)get_saved_state_pc(state));\n\t\t  g0245d_status(v358buf); }\n'''
    s = s.replace(anchor, replacement, 1)
    open(SLEH, "w", encoding="utf-8").write(s)
    print("patch_v367: fault registers traced; compact status installed")
else:
    print("patch_v367: fault probes already present -- skip")
m = open(VM, encoding="utf-8", errors="replace").read()
vm_mark = '"v367 vmsw returned"'
if vm_mark not in m:
    # Anchor at the unique return of vm_map_switch (not every return in file).
    start = m.find("\nvm_map_t\nvm_map_switch(\n")
    if start < 0:
        sys.exit("patch_v367: vm_map_switch definition not found")
    start += 1
    brace = m.find("{", start)
    end = m.find("\n}", brace)
    if brace < 0 or end < 0:
        sys.exit("patch_v367: vm_map_switch body bounds not found")
    body = m[brace:end]
    ret = "\treturn KERN_SUCCESS;"
    if body.count(ret) != 1:
        # Function may return a variable; use the final return statement.
        import re
        hits = list(re.finditer(r"\n\treturn [^;]+;", body))
        if len(hits) != 1:
            sys.exit("patch_v367: vm_map_switch return anchor ambiguous (%d)" % len(hits))
        hit = hits[0]
        ins = '\n\t{ extern void g0245d_trace(const char *); g0245d_trace("v367 vmsw returned"); }'
        body = body[:hit.start()] + ins + body[hit.start():]
    else:
        body = body.replace(ret, '\t{ extern void g0245d_trace(const char *); g0245d_trace("v367 vmsw returned"); }\n' + ret, 1)
    m = m[:brace] + body + m[end:]
    open(VM, "w", encoding="utf-8").write(m)
    print("patch_v367: vm_map_switch return trace added")
else:
    print("patch_v367: vm_map_switch trace already present -- skip")
