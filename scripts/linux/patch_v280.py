#!/usr/bin/env python3
"""g0245d v280 -- SHA1 NULL-table stubs + uuid path probes.

v279 boot picture decoded (biggest jump yet):

  * "v279 fbt pool" printed -- the permanent-pool probetab worked; fbt's
    invop/node/reg all returned; pseu 13001 -> pseu done: the WHOLE
    pseudo_inits loop finished; ioi enter/pub: IOKitBSDInit passed; then
    loopattach / ether_family_init / net_init_run / inittodr / setconf
    stage lines -- bsd_autoconf is BEHIND us.
  * Heartbeat "hb 8429/8387 v248 uuid chip1" is a misread of
    "v240 uuid chip1" (IOPlatformExpert.cpp): generatePlatformUUID() found
    /chosen AND unique-chip-id, then never returned.  This is the SECOND
    call site (publishPlatformUUIDAndSerial); v241 skipped the first one
    (configureDefaults) back in the v240 era.
  * Window after the chip1 probe: chip-id property read (safe), then
    SHA1Init/Update/Final.  libkern/crypto/corecrypto_sha1.c dereferences
    g_crypto_funcs->ccsha1_di directly -- corecrypto kext absent, NULL
    table, exactly the v276 AES wall family.  SHA1Init is the first caller
    since the v241 skip.  uuid_unparse is plain string formatting.

v280 changes:

  1. corecrypto_sha1.c: NULL guards on SHA1Init (bzero ctx), SHA1Update
     (no-op), SHA1Final (bzero 20-byte digest), one-shot "v280 sha1 stub"
     marker.  Same guard family as the v276 AES stubs; real code returns
     once corecrypto is linked.
  2. IOPlatformExpert.cpp: "v280 uuid sha1 enter"/"done" around the SHA1
     block in generatePlatformUUID (arm64 path), "v280 uuid pub done"
     after the call in publishPlatformUUIDAndSerial.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

SHA1 = os.path.join(WORK, "libkern/crypto/corecrypto_sha1.c")
PLAT = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")

MARK = "g0245d v280"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what):
    n = src.count(old)
    if n != 1:
        sys.exit("%s: anchor found %d times" % (what, n))
    return src.replace(old, new)


# --- 1. corecrypto_sha1.c: NULL-table stubs ------------------------------
s = read(SHA1)
if MARK not in s:
    s = sub(
        s,
        """#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/sha1.h>
#include <kern/debug.h>
#include <corecrypto/ccdigest.h>
""",
        """#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/sha1.h>
#include <kern/debug.h>
#include <corecrypto/ccdigest.h>

/* g0245d v280: g_crypto_funcs comes from the corecrypto kext, which this
 * build does not link (same wall family as the v276 AES stubs and the
 * v260 read_random fallback).  generatePlatformUUID() is the first boot
 * caller of SHA1Init and died on the NULL table.  Stub the SHA1 layer:
 * zero the context / digest, return success.  Real code returns once
 * corecrypto is linked. */
extern void g0245d_trace(const char *label);
static int g0245d_sha1_traced;

static void
g0245d_sha1_stub_note(void)
{
	if (!g0245d_sha1_traced) {
		g0245d_sha1_traced = 1;
		g0245d_trace("v280 sha1 stub");
	}
}
""",
        "sha1: stub preamble",
    )
    s = sub(
        s,
        """void
SHA1Init(SHA1_CTX *ctx)
{
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	g_crypto_funcs->ccdigest_init_fn(di, di_ctx);

	DiToSHA1(di, di_ctx, ctx);
}""",
        """void
SHA1Init(SHA1_CTX *ctx)
{
	/* g0245d v280: corecrypto absent -- zero the context instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_sha1_stub_note();
		bzero(ctx, sizeof(*ctx));
		return;
	}
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	g_crypto_funcs->ccdigest_init_fn(di, di_ctx);

	DiToSHA1(di, di_ctx, ctx);
}""",
        "sha1: SHA1Init guard",
    )
    s = sub(
        s,
        """void
SHA1Update(SHA1_CTX *ctx, const void *data, size_t len)
{
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	SHA1ToDi(di, ctx, di_ctx);
	g_crypto_funcs->ccdigest_update_fn(di, di_ctx, len, data);
	DiToSHA1(di, di_ctx, ctx);
}""",
        """void
SHA1Update(SHA1_CTX *ctx, const void *data, size_t len)
{
	/* g0245d v280: corecrypto absent -- keep the context as-is. */
	if (g_crypto_funcs == NULL) {
		g0245d_sha1_stub_note();
		return;
	}
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	SHA1ToDi(di, ctx, di_ctx);
	g_crypto_funcs->ccdigest_update_fn(di, di_ctx, len, data);
	DiToSHA1(di, di_ctx, ctx);
}""",
        "sha1: SHA1Update guard",
    )
    s = sub(
        s,
        """void
SHA1Final(void *digest, SHA1_CTX *ctx)
{
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	SHA1ToDi(di, ctx, di_ctx);
	ccdigest_final(di, di_ctx, digest);
}""",
        """void
SHA1Final(void *digest, SHA1_CTX *ctx)
{
	/* g0245d v280: corecrypto absent -- zero the digest instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_sha1_stub_note();
		bzero(digest, SHA_DIGEST_LENGTH);
		return;
	}
	const struct ccdigest_info *di = g_crypto_funcs->ccsha1_di;
	ccdigest_di_decl(di, di_ctx);

	SHA1ToDi(di, ctx, di_ctx);
	ccdigest_final(di, di_ctx, digest);
}""",
        "sha1: SHA1Final guard",
    )
    write(SHA1, s)
    print("corecrypto_sha1.c: 3 guards added")
else:
    print("corecrypto_sha1.c: already patched")

# --- 2. IOPlatformExpert.cpp: uuid path probes ---------------------------
s = read(PLAT)
if MARK not in s:
    s = sub(
        s,
        """				SHA1Init( &context );
				SHA1Update( &context, space, sizeof(space));
				SHA1Update( &context, data1->getBytesNoCopy(), data1->getLength());
				SHA1Update( &context, data2->getBytesNoCopy(), data2->getLength());
				SHA1Final( digest, &context );""",
        """				g0245d_trace("v280 uuid sha1 enter");
				SHA1Init( &context );
				SHA1Update( &context, space, sizeof(space));
				SHA1Update( &context, data1->getBytesNoCopy(), data1->getLength());
				SHA1Update( &context, data2->getBytesNoCopy(), data2->getLength());
				SHA1Final( digest, &context );
				g0245d_trace("v280 uuid sha1 done");""",
        "uuid: sha1 bracketed",
    )
    s = sub(
        s,
        """		provider->generatePlatformUUID();
	}""",
        """		provider->generatePlatformUUID();
		g0245d_trace("v280 uuid pub done");
	}""",
        "uuid: publish call bracketed",
    )
    write(PLAT, s)
    print("IOPlatformExpert.cpp: uuid probes added")
else:
    print("IOPlatformExpert.cpp: already patched")

print("v280 done")
