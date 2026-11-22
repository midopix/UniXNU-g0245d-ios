#!/usr/bin/env python3
"""g0245d v244 -- skip kmem_crypto_init(), which calls a NULL crypto table.

Both photos agree on the same stop: pinned row "su 3915 079ade90", and the ring
ends at "v242 su 3915".  Replaying the startup sort (scripts/startup_order.py)
maps #3915 to _kmem_crypto_init at exactly 0xfffffff0079ade90 -- and this time
the pinned-row address and the offline table agree, so there is no ambiguity.

Its whole body is:

    vm_size_t ctx_size = crypto_random_kmem_ctx_size();
    for each kmem size class:
        ks->ks_rng_ctx = zalloc_percpu_permanent(ctx_size, ...);
        zpercpu_foreach(ctx, ks->ks_rng_ctx) crypto_random_kmem_init(ctx);

and both crypto helpers are indirect calls through g_crypto_funcs:

    return g_crypto_funcs->random_kmem_ctx_size_fn();
    g_crypto_funcs->random_kmem_init_fn(ctx);

Offline evidence that the table is NULL: the kernel image has
g_crypto_funcs = 0 in __DATA_CONST at 0xfffffff0071af580, and a full
disassembly contains NO call to register_crypto_functions() -- the only two
mentions are its own label and an internal branch.  The implementation is in a
corecrypto kext that was skipped along with prelink.  So the very first
indirect call is a NULL-pointer data abort, which on this bring-up is silent.

v244 keeps the original body under #if 0 (one edit to restore once corecrypto
is really linked) and returns early with a trace, following the same pattern
that worked for generatePlatformUUID() and pgz_init().
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

Z = os.path.join(WORK, "osfmk/vm/vm_kern.c")

MARK = "g0245d v244"


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


s = read(Z)
if MARK not in s:
    s = sub(
        s,
        "#include <mach/kern_return.h>",
        """#include <mach/kern_return.h>

/* g0245d v244: framebuffer console probes, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_probe_u(const char *tag, unsigned int value);""",
        "vm_kern: externs",
    )

    s = sub(
        s,
        """kmem_crypto_init(void)
{
	vm_size_t ctx_size = crypto_random_kmem_ctx_size();

	for (uint32_t i = 0; i < KMEM_NUM_SIZECLASS; i++) {
		struct kmem_sizeclass *ks = &kmem_size_array[i];

		ks->ks_rng_ctx = zalloc_percpu_permanent(ctx_size, ZALIGN_PTR);
		zpercpu_foreach(ctx, ks->ks_rng_ctx) {
			crypto_random_kmem_init(ctx);
		}
	}
}""",
        """kmem_crypto_init(void)
{
	/* g0245d v244: SKIPPED for bring-up.
	 *
	 * v243's photo stops at startup routine #3915 = this function, and the
	 * pinned row says 079ade90, which is exactly its address.  Both crypto
	 * helpers below call through g_crypto_funcs, which is 0 in __DATA_CONST
	 * and is never assigned: register_crypto_functions() lives in the
	 * corecrypto kext that was skipped along with prelink.  The first
	 * indirect call is therefore a NULL data abort with no exception
	 * handler, i.e. the silent stop we see.
	 *
	 * kmem's per-size-class RNG is a hardening feature, not needed to boot.
	 * Restore the body below once corecrypto is linked in.
	 */
	g0245d_probe_u("nocrypto", 244);
	g0245d_trace("v244 kmem crypto skipped");

#if 0   /* g0245d v244: original body, kept verbatim for restoration */
	vm_size_t ctx_size = crypto_random_kmem_ctx_size();

	for (uint32_t i = 0; i < KMEM_NUM_SIZECLASS; i++) {
		struct kmem_sizeclass *ks = &kmem_size_array[i];

		ks->ks_rng_ctx = zalloc_percpu_permanent(ctx_size, ZALIGN_PTR);
		zpercpu_foreach(ctx, ks->ks_rng_ctx) {
			crypto_random_kmem_init(ctx);
		}
	}
#endif  /* g0245d v244 */
}""",
        "vm_kern: skip kmem_crypto_init",
    )

    write(Z, s)
    print("vm_kern: v244 changes applied")
else:
    print("vm_kern: already patched")

print("v244 patch applied")
