#!/usr/bin/env python3
"""g0245d v245 -- skip trust caches, bracket lockdown and IOKit matching.

v244's photo is another big step:

    8039 v242 su 3917 / 8040 v242 ok 3917      <- all 3917 startup routines ran
    8041 v241 spllo enter / 8042 spllo done    <- interrupts on, no crash
    8043 v241 screen init enter / 8044 done    <- console survived the screen grab
    8045 mac_policy_initmach
    8046 vm_compressor_init
    status: >trust_cache_init

so '>trust_cache_init' is the last stage logged and the machine stops in
trust_cache_runtime_init() or load_static_trust_cache().  Both consume code
signing / hash data, i.e. the same NULL g_crypto_funcs table that killed
kmem_crypto_init -- there is no crypto kext in this skip-prelink build.

v245 skips both trust-cache calls (hardening data, not needed to boot), keeps
the originals under #if 0, and brackets everything that follows so one more
photo covers the whole end of kernel_bootstrap(): the LOCKDOWN startup phase,
OSKextRemoveKextBootstrap, machine_lockdown and PE_lockdown_iokit.

It also removes the known NativeAES personality from KernelConfigTables.cpp.
That class descends from IOAESAccelerator::gMetaClass, an absolute prelink
symbol at 0xfffffff006ae52d0 (unmapped, see HANDOFF 2.11); StartIOKitMatching
would instantiate it and die on the same address.  The class is gone from this
build, so the personality must go too.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

START = os.path.join(WORK, "osfmk/kern/startup.c")
PE = os.path.join(WORK, "pexpert/arm/pe_init.c")
IOK = os.path.join(WORK, "iokit/Kernel/IOStartIOKit.cpp")
KT = os.path.join(WORK, "iokit/KernelConfigTables.cpp")

MARK = "g0245d v245"


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


# ---------------------------------------------------------------- startup.c
s = read(START)
if MARK not in s:
    s = sub(
        s,
        """	kernel_bootstrap_log("trust_cache_init");

	/* Initialize the runtime for the trust cache interface */
	trust_cache_runtime_init();

	/* Load the static and engineering trust caches */
	load_static_trust_cache();""",
        """	kernel_bootstrap_log("trust_cache_init");
	/* g0245d v245: trust caches carry code-signing hashes, so loading them
	 * uses the same g_crypto_funcs table that is NULL in this skip-prelink
	 * build (see v244).  Keep the originals below for a build with corecrypto.
	 */
	g0245d_trace("v245 trust cache skipped");
#if 0   /* g0245d v245 */
	trust_cache_runtime_init();
	load_static_trust_cache();
#endif  /* g0245d v245 */""",
        "startup: skip trust caches",
    )

    s = sub(
        s,
        """	kernel_startup_initialize_upto(STARTUP_SUB_LOCKDOWN);""",
        """	g0245d_trace("v245 lockdown routines enter");
	kernel_startup_initialize_upto(STARTUP_SUB_LOCKDOWN);
	g0245d_trace("v245 lockdown routines done");""",
        "startup: lockdown routines",
    )
    s = sub(
        s,
        """	kernel_bootstrap_log("OSKextRemoveKextBootstrap");
	OSKextRemoveKextBootstrap();""",
        """	kernel_bootstrap_log("OSKextRemoveKextBootstrap");
	g0245d_trace("v245 oskext jettison enter");
	OSKextRemoveKextBootstrap();
	g0245d_trace("v245 oskext jettison done");""",
        "startup: jettison",
    )
    s = sub(
        s,
        """	kernel_bootstrap_log("machine_lockdown");
	machine_lockdown();""",
        """	kernel_bootstrap_log("machine_lockdown");
	g0245d_trace("v245 machine lockdown enter");
	machine_lockdown();
	g0245d_trace("v245 machine lockdown done");""",
        "startup: machine_lockdown",
    )
    s = sub(
        s,
        """	kernel_bootstrap_log("PE_lockdown_iokit");
	PE_lockdown_iokit();""",
        """	kernel_bootstrap_log("PE_lockdown_iokit");
	g0245d_trace("v245 PE lockdown enter");
	PE_lockdown_iokit();
	g0245d_trace("v245 PE lockdown done");""",
        "startup: PE_lockdown_iokit",
    )

    write(START, s)
    print("startup: v245 changes applied")
else:
    print("startup: already patched")

# --------------------------------------------------------------- pe_init.c
s = read(PE)
if MARK not in s:
    s = sub(
        s,
        """	StartIOKitMatching();""",
        """	g0245d_trace("v245 start matching enter");
	StartIOKitMatching();
	g0245d_trace("v245 start matching done");""",
        "pe_init: StartIOKitMatching bracket",
    )
    write(PE, s)
    print("pe_init: v245 changes applied")
else:
    print("pe_init: already patched")

# -------------------------------------------------------- IOStartIOKit.cpp
s = read(IOK)
if MARK not in s:
    s = sub(
        s,
        """	bool ok = gRootNub->startIOServiceMatching();""",
        """	g0245d_trace("v245 matching call enter");
	bool ok = gRootNub->startIOServiceMatching();
	g0245d_trace("v245 matching call done");""",
        "IOStartIOKit: matching call bracket",
    )
    write(IOK, s)
    print("IOStartIOKit: v245 changes applied")
else:
    print("IOStartIOKit: already patched")

# ------------------------------------------------------- KernelConfigTables
s = read(KT)
if MARK not in s:
    s = sub(
        s,
        """#if defined(XNU_NATIVE_AES) && XNU_NATIVE_AES
    "   ,{"
    "     'IOClass'         = NativeAES;"
    "     'IOProviderClass' = IOResources;"
    "     'IOResourceMatch' = IOBSD;"
    "     'IOProbeScore'    = 1000:32;"
    "   }"
#endif""",
        """/* g0245d v245: NativeAES derives from IOAESAccelerator, whose gMetaClass
 * is a prelink absolute symbol at 0xfffffff006ae52d0 (unmapped here).  IOKit
 * matching would instantiate the class and die on that address, and the class
 * is not built in this kernel anyway.  Drop the personality.
 */
#if 0   /* g0245d v245: was defined(XNU_NATIVE_AES) && XNU_NATIVE_AES */
    "   ,{"
    "     'IOClass'         = NativeAES;"
    "     'IOProviderClass' = IOResources;"
    "     'IOResourceMatch' = IOBSD;"
    "     'IOProbeScore'    = 1000:32;"
    "   }"
#endif""",
        "KernelConfigTables: drop NativeAES personality",
    )
    write(KT, s)
    print("KernelConfigTables: v245 changes applied")
else:
    print("KernelConfigTables: already patched")

print("v245 patch applied")
