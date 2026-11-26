#!/usr/bin/env python3
"""g0245d v377 -- guard the NULL corecrypto function table in SHA{256,384,512}.

v376 photo (2026-11-26 10:29): data abort at PC 0xfffffff00792d664, which
symbolizes to _SHA256_Init+0x10 in the v376 kernel (v375 same symbol is
0xfffffff0078a9654; delta 0x84000 == the N4KROOT container size -- confirms
v376 was executed).  SHA256_Init does:

    di = g_crypto_funcs->ccsha256_di;

and g_crypto_funcs is NULL under --skip-prelink (corecrypto kext is skipped;
v244 already hit this in vm_kern.c and skipped kmem_crypto_init).  The real
launchd carries LC_CODE_SIGNATURE / a cdhash, so kern_exec.c:6172 calls
SHA256_Init to hash cdhash + boot-session UUID -> NULL deref.  The synthetic
exit(42) Mach-O had no cdhash, so v375 never reached this path.

ONE嫌疑点: make the SHA wrappers tolerate an unregistered crypto table.
Deterministic stub (no crypto available, so no real digest is possible):
  - Init:   zero the caller's context, trace once
  - Update: no-op, trace once
  - Final:  zero the output digest, trace once
Consequence: the boot-session string becomes a fixed value.  That is harmless
for bring-up (it is informational env data, not verified by the kernel).

CUMULATIVE + IDEMPOTENT over v376.  Only libkern/crypto/corecrypto_sha2.c is
touched; all prior probes stay in place.
"""
import os
import sys

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
PATH = os.path.join(W, "libkern/crypto/corecrypto_sha2.c")
if not os.path.isfile(PATH):
    sys.exit("required file not found: %s" % PATH)

src = open(PATH, encoding="utf-8", errors="replace").read()
if "v377 nocrypto" in src:
    print("patch_v377: already applied -- skip")
    sys.exit(0)


def guard_init(name, ctx_size):
    """Insert a NULL-table guard at the top of SHA*_Init."""
    old = ("void\n%s(%s *ctx)\n{\n" % (name, ctx_size))
    new = (old +
           "\tif (g_crypto_funcs == NULL) {\n"
           "\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n"
           "\t\t  g0245d_tracev(\"v377 nocrypto %s\", (unsigned long long)(uintptr_t)ctx); }\n"
           "\t\tbzero(ctx, sizeof(*ctx));\n"
           "\t\treturn;\n"
           "\t}\n" % name)
    return old, new


def guard_update(name, ctx_size):
    old = ("void\n%s(%s *ctx, const void *data, size_t len)\n{\n" % (name, ctx_size))
    new = (old +
           "\tif (g_crypto_funcs == NULL) {\n"
           "\t\t{ extern void g0245d_tracev(const char *, unsigned long long);\n"
           "\t\t  g0245d_tracev(\"v377 nocrypto %s\", (unsigned long long)len); }\n"
           "\t\treturn;\n"
           "\t}\n" % name)
    return old, new


def guard_final(name):
    base = name[:-len("_Final")]   # SHA256_Final -> SHA256
    old = ("void\n%s(void *digest, %s_CTX *ctx)\n{\n" % (name, base))
    new = (old +
           "\tif (g_crypto_funcs == NULL) {\n"
           "\t\t{ extern void g0245d_trace(const char *);\n"
           "\t\t  g0245d_trace(\"v377 nocrypto %s\"); }\n"
           "\t\tbzero(digest, %s_DIGEST_LENGTH);\n"
           "\t\treturn;\n"
           "\t}\n" % (name, base))
    return old, new


edits = []
for nm in ("SHA256", "SHA384", "SHA512"):
    edits.append(guard_init(nm + "_Init", nm + "_CTX"))
    edits.append(guard_update(nm + "_Update", nm + "_CTX"))
    edits.append(guard_final(nm + "_Final"))

for old, new in edits:
    n = src.count(old)
    if n != 1:
        sys.exit("patch_v377: anchor count=%d for %r" % (n, old[:50]))
    src = src.replace(old, new, 1)

open(PATH, "w", encoding="utf-8").write(src)
print("patch_v377: SHA256/384/512 NULL-crypto guards installed (9 functions)")
