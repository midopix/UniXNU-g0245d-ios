#!/usr/bin/env python3
"""patch_v373 -- guard the AMFI entitlement dispatch when AMFI is not loaded.

Evidence (v372 photo, 2026-11-25 15:18:58): pc = _IOTaskHasEntitlement+0x44,
`ldr x8, [x8, #0x1b0]` via the `amfi` global, which is NULL in this
--skip-prelink (kext-less) kernel.  Guard all three entitlement entry points
in IOKitBSDInit.cpp and trace the caller LR.

CUMULATIVE + IDEMPOTENT over v372, including repair of an earlier attempt
that put `extern "C"` declarations inside function bodies (illegal in C++).
"""

import os
import sys

W = os.environ.get("XNU_WORK") or sys.exit("patch_v373: set XNU_WORK")
P = os.path.join(W, "iokit", "bsddev", "IOKitBSDInit.cpp")
s = open(P, encoding="utf-8", errors="replace").read()

DECL = 'extern "C" void g0245d_tracev(const char *, unsigned long long);\n'

# --- repair: hoist the declaration out of function bodies ------------------
for label in ("str", "has", "get"):
    old = ('\t{ extern "C" void g0245d_tracev(const char *, unsigned long long);\n'
           '\t  g0245d_tracev("v373 %s", (unsigned long long)(uintptr_t)__builtin_return_address(0)); }\n' % label)
    new = '\tg0245d_tracev("v373 %s", (unsigned long long)(uintptr_t)__builtin_return_address(0));\n' % label
    if old in s:
        s = s.replace(old, new)
        print("patch_v373: repaired inline declaration (%s)" % label)

# --- file-scope declaration, placed before the first guarded function ------
anchor = ('extern "C" OS_ALWAYS_INLINE boolean_t\n'
          'IOCurrentTaskHasStringEntitlement(const char *entitlement, const char *value)\n')
if DECL not in s:
    if s.count(anchor) != 1:
        sys.exit("patch_v373: declaration anchor count=%d" % s.count(anchor))
    s = s.replace(anchor, DECL + '\n' + anchor, 1)
    print("patch_v373: file-scope declaration added")
else:
    print("patch_v373: declaration already present")


def guard(text, old, new, label):
    if "v373 " + label in text:
        print("patch_v373: %s already applied" % label)
        return text
    c = text.count(old)
    if c != 1:
        sys.exit("patch_v373: %s anchor count=%d (want 1)" % (label, c))
    print("patch_v373: %s applied" % label)
    return text.replace(old, new, 1)


def tramp(label):
    return '\tg0245d_tracev("v373 %s", (unsigned long long)(uintptr_t)__builtin_return_address(0));\n' % label


old1 = ('\t/* Validate input arguments */\n'
        '\tif (task == kernel_task || entitlement == NULL || value == NULL) {\n'
        '\t\treturn false;\n'
        '\t}\n'
        '\tproc_t proc = (proc_t)get_bsdtask_info(task);\n')
s = guard(s, old1, old1 + '\tif (amfi == NULL) {\n' + tramp("str") + '\t\treturn false;\n\t}\n', "str")

old2 = ('\t/* Validate input arguments */\n'
        '\tif (task == kernel_task || entitlement == NULL) {\n'
        '\t\treturn false;\n'
        '\t}\n'
        '\tproc_t proc = (proc_t)get_bsdtask_info(task);\n')
s = guard(s, old2, old2 + '\tif (amfi == NULL) {\n' + tramp("has") + '\t\treturn false;\n\t}\n', "has")

old3 = ('\t/* Validate input arguments */\n'
        '\tif (task == kernel_task || entitlement == NULL) {\n'
        '\t\treturn NULL;\n'
        '\t}\n'
        '\tproc_t proc = (proc_t)get_bsdtask_info(task);\n')
s = guard(s, old3, old3 + '\tif (amfi == NULL) {\n' + tramp("get") + '\t\treturn NULL;\n\t}\n', "get")

open(P, "w", encoding="utf-8").write(s)
print("patch_v373: AMFI-null guards installed")
