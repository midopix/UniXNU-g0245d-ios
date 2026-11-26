#!/usr/bin/env python3
"""g0245d v379 -- tolerate a NULL AMFI ops table on the code-signature path.

v378 photo (2026-11-26 10:43) finally exposed the panic text through the
segmented ring lines:

    v378 pm0  Kernel data abort. at pc
    v378 pm1  0xfffffff0077d36a4, lr
    v378 pm2  0xfffffff0077d23c8 (saved state: 0xffffffffa89f3b000)

and `v377 nocrypto SHA256_Final` right before it, i.e. the v377 crypto guard
worked (no more abort inside SHA256_*).

Symbolizing the v378 kernel (tools/symaddr.py, no llvm-nm needed):
    pc 0xfffffff0077d36a4 = _accelerate_entitlement_queries + 0x1c
    lr 0xfffffff0077d23c8 = _ubc_cs_blob_add + 0x550

Disassembly of the fault:
    adrp x8, 0xfffffff007237000
    ldr  x8, [x8, #0x5d8]      ; _amfi  (NULL: kext skipped by --skip-prelink)
    ldr  x8, [x8, #0x1a0]      ; amfi->OSEntitlements.adjustContextWithoutMonitor  <-- abort
    ldr  x0, [x0, #0xa0]       ; cs_blob->csb_entitlements
    blr  x8

Source: bsd/kern/ubc_subr.c accelerate_entitlement_queries() -- the code signing
monitor path returned KERN_NOT_SUPPORTED, so it falls through to
`amfi->OSEntitlements.adjustContextWithoutMonitor(...)`.  Same root cause as
v372/v373 (amfi == NULL), different consumer: v373 only guarded the three
IOTaskHasEntitlement style entry points in IOKitBSDInit.cpp.

ONE嫌疑点: amfi == NULL must be tolerated by the cs_blob entitlement lifecycle
in ubc_subr.c (both the accelerate call and the matching cleanup invalidate, so
a later blob free cannot panic for the same reason).

Semantics when amfi is NULL:
  - accelerate: nothing can accelerate entitlement queries -> return 0 (success),
    entitlements stay unparsed (bring-up only; no entitlement enforcement).
  - cleanup:    nothing to invalidate -> skip the amfi op, still release the
    os object.

Diagnostics (ring, g0245d_trace):
  v379 noamfi  -- guard taken in accelerate_entitlement_queries
  v379 inval   -- guard taken in cs_blob_cleanup
  v379 bladd   -- ubc_cs_blob_add got past entitlement acceleration (probe)

CUMULATIVE + IDEMPOTENT over v378.  Only bsd/kern/ubc_subr.c is touched.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "bsd", "kern", "ubc_subr.c")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v379 noamfi" in src:
    print("patch_v379: already applied -- skip")
    sys.exit(0)

TRACE = ('{ extern void g0245d_trace(const char *);\n'
         '\t\t  g0245d_trace("%s"); }')

# --- 1. accelerate_entitlement_queries: bail out when AMFI is absent ---------
old1 = ('static errno_t\n'
        'accelerate_entitlement_queries(\n'
        '\tstruct cs_blob *cs_blob)\n'
        '{\n'
        '\tkern_return_t ret = KERN_NOT_SUPPORTED;\n')
new1 = (old1 +
        '\n'
        '\tif (amfi == NULL) {\n'
        '\t\t/* v379: no AMFI kext in this kernel -- nothing can accelerate */\n'
        '\t\t' + TRACE % 'v379 noamfi' + '\n'
        '\t\treturn 0;\n'
        '\t}\n')
n = src.count(old1)
if n != 1:
    sys.exit("patch_v379: anchor1 count=%d (want 1)" % n)
src = src.replace(old1, new1, 1)
print("patch_v379: accelerate_entitlement_queries guarded")

# --- 2. cs_blob_cleanup: skip OSEntitlements_invalidate when AMFI is absent --
old2 = ('\tif (blob->csb_entitlements != NULL) {\n'
        '\t\tamfi->OSEntitlements_invalidate(blob->csb_entitlements);\n')
new2 = ('\tif (blob->csb_entitlements != NULL) {\n'
        '\t\tif (amfi == NULL) {\n'
        '\t\t\t' + TRACE % 'v379 inval' + '\n'
        '\t\t} else {\n'
        '\t\t\tamfi->OSEntitlements_invalidate(blob->csb_entitlements);\n'
        '\t\t}\n')
n = src.count(old2)
if n != 1:
    sys.exit("patch_v379: anchor2 count=%d (want 1)" % n)
src = src.replace(old2, new2, 1)
print("patch_v379: cs_blob_cleanup guarded")

# --- 3. probe: we got past entitlement acceleration ------------------------
old3 = ('\terror = accelerate_entitlement_queries(&tmp_blob);\n'
        '\tif (error != 0) {\n'
        '\t\tgoto out;\n'
        '\t}\n')
new3 = (old3 +
        '\t' + TRACE % 'v379 bladd' + '\n')
n = src.count(old3)
if n != 1:
    sys.exit("patch_v379: anchor3 count=%d (want 1)" % n)
src = src.replace(old3, new3, 1)
print("patch_v379: bladd probe installed")

open(PATH, "w", encoding="utf-8").write(src)
print("patch_v379: AMFI-null tolerance in ubc_subr.c installed")
