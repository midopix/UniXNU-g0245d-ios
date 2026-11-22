#!/usr/bin/env python3
"""g0245d v276 -- give the kernel a working (stub) AES layer.

v275 boot picture decoded:
  * udp_init is FULLY green now: both hashinits allocated (callers
    _udp_init+0xa0/+0xb4), "udp hash2" -> "udp grp" -> "udp done" ->
    "prinit done" all on screen.  The v274 hang is closed.
  * tcp_init entered; the heartbeat froze on "v275 tcp frnd" (after the
    first read_frandom).  The frnd->tfo window contains only two empty
    SYSCTL macros and tcp_tfo_init():
      read_frandom(key, 16)          -- read_erandom, local DRBG, works
      aes_encrypt_key128(key, &tfo_ctx)
    aes_encrypt_key128 -> aes_encrypt_key -> g_crypto_funcs->ccaes_cbc_encrypt.
    g_crypto_funcs is installed ONLY by the corecrypto kext
    (libkern/crypto/register_crypto.c), which this build does not link --
    exactly the same situation as the v260 read_random NULL-call.  Boot
    therefore dies on the kernel's very first AES call: NULL table deref,
    silent stop, no panic string.

v276 does two things:

  1. libkern/crypto/corecrypto_aes.c: NULL-guard all four entry points
     (aes_encrypt_key/_cbc, aes_decrypt_key/_cbc).  When g_crypto_funcs is
     absent, zero the context (and the output for the CBC routines) and
     return success, with a one-shot "v276 aes stub" trace.  Quality is
     irrelevant at bring-up; the real implementation returns when
     corecrypto is linked.
  2. tcp_subr.c: probe inside tcp_tfo_init ("v276 tfo frnd" / "v276 tfo
     aes") so the photo proves which half ran.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

AES = os.path.join(WORK, "libkern/crypto/corecrypto_aes.c")
TCP = os.path.join(WORK, "bsd/netinet/tcp_subr.c")

MARK = "g0245d v276"


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


# ------------------------------------------------- corecrypto_aes.c (guards)
s = read(AES)
if MARK not in s:
    s = sub(
        s,
        """#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/aes.h>
#include <corecrypto/ccmode.h>
#include <corecrypto/ccaes.h>
#include <kern/debug.h>
""",
        """#include <libkern/crypto/crypto_internal.h>
#include <libkern/crypto/aes.h>
#include <corecrypto/ccmode.h>
#include <corecrypto/ccaes.h>
#include <kern/debug.h>

/* g0245d v276: g_crypto_funcs is installed by the corecrypto kext, which
 * this build does not link (same situation as the v260 read_random
 * fallback).  tcp_tfo_init() is the first caller at boot and died
 * dereferencing the NULL table.  Stub the AES layer below: zero the
 * context (and the output for CBC), return success.  Quality does not
 * matter at bring-up; the real implementation returns once corecrypto is
 * linked. */
extern void g0245d_trace(const char *label);
static int g0245d_aes_traced;

static void
g0245d_aes_stub_note(void)
{
	if (!g0245d_aes_traced) {
		g0245d_aes_traced = 1;
		g0245d_trace("v276 aes stub");
	}
}
""",
        "aes: stub helpers after includes",
    )

    s = sub(
        s,
        """aes_rval
aes_encrypt_key(const unsigned char *key, int key_len, aes_encrypt_ctx cx[1])
{
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_encrypt;
""",
        """aes_rval
aes_encrypt_key(const unsigned char *key, int key_len, aes_encrypt_ctx cx[1])
{
	/* g0245d v276: corecrypto absent -- zero-fill the context instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_aes_stub_note();
		bzero(cx[0].ctx, sizeof(aes_encrypt_ctx));
		return 0;
	}
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_encrypt;
""",
        "aes: encrypt_key guard",
    )

    s = sub(
        s,
        """aes_rval
aes_encrypt_cbc(const unsigned char *in_blk, const unsigned char *in_iv, unsigned int num_blk,
    unsigned char *out_blk, aes_encrypt_ctx cx[1])
{
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_encrypt;
""",
        """aes_rval
aes_encrypt_cbc(const unsigned char *in_blk, const unsigned char *in_iv, unsigned int num_blk,
    unsigned char *out_blk, aes_encrypt_ctx cx[1])
{
	/* g0245d v276: corecrypto absent -- zero the output buffer instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_aes_stub_note();
		bzero(out_blk, num_blk * AES_BLOCK_SIZE);
		return 0;
	}
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_encrypt;
""",
        "aes: encrypt_cbc guard",
    )

    s = sub(
        s,
        """aes_rval
aes_decrypt_key(const unsigned char *key, int key_len, aes_decrypt_ctx cx[1])
{
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_decrypt;
""",
        """aes_rval
aes_decrypt_key(const unsigned char *key, int key_len, aes_decrypt_ctx cx[1])
{
	/* g0245d v276: corecrypto absent -- zero-fill the context instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_aes_stub_note();
		bzero(cx[0].ctx, sizeof(aes_decrypt_ctx));
		return 0;
	}
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_decrypt;
""",
        "aes: decrypt_key guard",
    )

    s = sub(
        s,
        """aes_rval
aes_decrypt_cbc(const unsigned char *in_blk, const unsigned char *in_iv, unsigned int num_blk,
    unsigned char *out_blk, aes_decrypt_ctx cx[1])
{
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_decrypt;
""",
        """aes_rval
aes_decrypt_cbc(const unsigned char *in_blk, const unsigned char *in_iv, unsigned int num_blk,
    unsigned char *out_blk, aes_decrypt_ctx cx[1])
{
	/* g0245d v276: corecrypto absent -- zero the output buffer instead. */
	if (g_crypto_funcs == NULL) {
		g0245d_aes_stub_note();
		bzero(out_blk, num_blk * AES_BLOCK_SIZE);
		return 0;
	}
	const struct ccmode_cbc *cbc = g_crypto_funcs->ccaes_cbc_decrypt;
""",
        "aes: decrypt_cbc guard",
    )

    write(AES, s)
    print("corecrypto_aes.c: NULL guards installed")
else:
    print("corecrypto_aes.c: already patched")

# --------------------------------------------------- tcp_subr.c (tfo probes)
s = read(TCP)
if MARK not in s:
    s = sub(
        s,
        """	read_frandom(key, sizeof(key));
	aes_encrypt_key128(key, &tfo_ctx);""",
        """	read_frandom(key, sizeof(key));
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v276 tfo frnd"); }
	aes_encrypt_key128(key, &tfo_ctx);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v276 tfo aes"); }""",
        "tcp: probes inside tcp_tfo_init",
    )
    write(TCP, s)
    print("tcp_subr.c: tcp_tfo_init probed")
else:
    print("tcp_subr.c: already patched")

print("v276 done")
