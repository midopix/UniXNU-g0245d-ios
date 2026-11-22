#!/usr/bin/env python3
"""g0245d v260 -- make read_random() survive without the corecrypto kext.

v259's photo shows mcache_init() sailing through everything:

    8189..8196  v259 mc bkt 2..9
    8197        v259 mc bkt done
    8198/8199   v259 mc audit enter/done
    8200/8201   v259 mc applyall enter/done
    hb 8203/8148

so the two dark rows after 8201 are 8202 "v258 mcache done" and
8203 "bsd calling mbinit" -- and the machine stops inside mbinit().

mbinit()'s first runtime statements are:

    read_random(&mb_redzone_cookie, sizeof(mb_redzone_cookie));
    read_random(&mb_obscure_extref, sizeof(mb_obscure_extref));
    read_random(&mb_obscure_extfree, sizeof(mb_obscure_extfree));

and read_random() is

    prng_funcs.refresh(prng_ctx);
    read_random_generate(buffer, numbytes);      /* -> prng_funcs.generate(...) */

Both are indirect calls through `prng_funcs`, a SECURITY_READ_ONLY_LATE
struct.  Its own comment says the kernel PRNG "happens during corecrypto kext
initialization" -- the kext this skip-prelink build never links.  So the table
is all zeros and the first call is a NULL function call, the same family as
g_crypto_funcs (kmem_crypto_init) and invalidate_hmac_function.

read_random() is used all over BSD (sockets, kauth, kext loading), so skipping
mbinit's three calls would only postpone the crash.  v260 fixes the function
itself: if the table is not installed, fill the buffer from a small local
generator instead.  Entropy quality is irrelevant for what boot-time callers
want (redzone canaries, jitter), and the real PRNG comes back as soon as
corecrypto is linked.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

PRNG = os.path.join(WORK, "osfmk/prng/prng_random.c")

MARK = "g0245d v260"


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


s = read(PRNG)
if MARK not in s:
    s = sub(
        s,
        """void
read_random(void * buffer, u_int numbytes)
{
	prng_funcs.refresh(prng_ctx);
	read_random_generate(buffer, numbytes);
}""",
        """/* g0245d v260: prng_funcs is installed by the corecrypto kext, which this
 * build does not link, so both indirect calls in read_random() would be NULL
 * calls -- mbinit() hit exactly that with its redzone cookies.  Fall back to a
 * local generator when the table is absent; quality does not matter for the
 * boot-time callers, and the real PRNG returns once corecrypto is linked.
 */
static uint32_t g0245d_rand_state = 0x9e3779b9u;
static int      g0245d_rand_traced;

static void
g0245d_rand_fill(void *buffer, u_int numbytes)
{
	uint8_t *p = (uint8_t *)buffer;
	u_int    i;

	if (!g0245d_rand_traced) {
		g0245d_rand_traced = 1;
		g0245d_trace("v260 read_random fallback");
	}
	for (i = 0; i < numbytes; i++) {
		g0245d_rand_state = g0245d_rand_state * 1664525u + 1013904223u;
		p[i] = (uint8_t)(g0245d_rand_state >> 24);
	}
}

void
read_random(void * buffer, u_int numbytes)
{
	if (prng_funcs.refresh == NULL || prng_funcs.generate == NULL) {
		g0245d_rand_fill(buffer, numbytes);
		return;
	}
	prng_funcs.refresh(prng_ctx);
	read_random_generate(buffer, numbytes);
}""",
        "prng: read_random fallback",
    )
    write(PRNG, s)
    print("prng: v260 changes applied")
else:
    print("prng: already patched")

print("v260 patch applied")
