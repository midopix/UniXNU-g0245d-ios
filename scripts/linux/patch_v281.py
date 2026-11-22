#!/usr/bin/env python3
"""g0245d v281 -- bracket IOFindBSDRoot + platform-expert configure loop.

v280 boot picture decoded:

  * "v280 sha1 stub" fired, "sha1 done", "uuid pub done" -- the SHA1 NULL
     guard worked end to end.  publishPlatformUUIDAndSerial() returned.
  * Heartbeat "hb 8432/8398 v280 uuid pub done": last console write is the
     publish probe itself; nothing since.  setconf (8425) already ran, so
     the bsd_init thread is inside IOFindBSDRoot() whose first act is
     waitForMatchingService(IOBSD resource, 30 s) -- concurrent with that,
     the matching thread started the platform expert (uuid probes 8426-32).

Two candidate stalls, currently indistinguishable:
  a) bsd_init still inside the 30 s IOBSD wait (photo may just be early);
     on timeout IOLog("!BSD") would print, then the IOMedia wait loop and
     finally, for an iOS target, panic("Failed to mount root device").
  b) matching thread silently stalled inside IOPlatformExpert::configure()
     (createNub/attach/registerService per top-level node) or in the first
     driver matches that registerService triggers.

v281 probes both paths:

  1. IOFindBSDRoot: "v281 fbr enter" on entry; "v281 fbr iobsd got"/
     "v281 fbr iobsd tmo" after the 30 s wait; "v281 fbr waiting" before
     the final ROOTDEVICETIMEOUT loop; "v281 fbr found" after it.
  2. IOPlatformExpert::configure: "v281 cfg <N>" per top-level nub and
     "v281 cfg reg <N>" after each registerService, plus "v281 cfg done".
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")
PLAT = os.path.join(WORK, "iokit/Kernel/IOPlatformExpert.cpp")

MARK = "g0245d v281"

T = "{ extern void g0245d_trace(const char *);\n" \
    "  g0245d_trace(\"%s\"); }\n"
TU = "{ extern void g0245d_trace_u(const char *, unsigned int);\n" \
     "  g0245d_trace_u(\"%s\", (unsigned int)%s); }\n"


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


# --- 1. IOFindBSDRoot -----------------------------------------------------
s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """	// stall here for anyone matching on the IOBSD resource to finish (filesystems)
	matching = IOService::serviceMatching(gIOResourcesKey);""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 fbr enter"); }
	// stall here for anyone matching on the IOBSD resource to finish (filesystems)
	matching = IOService::serviceMatching(gIOResourcesKey);""",
        "fbr: entry probe",
    )
    s = sub(
        s,
        """	if ((service = IOService::waitForMatchingService(matching, 30ULL * kSecondScale))) {
		OSSafeReleaseNULL(service);
	} else {
		IOLog("!BSD\\n");
	}""",
        """	if ((service = IOService::waitForMatchingService(matching, 30ULL * kSecondScale))) {
		OSSafeReleaseNULL(service);
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v281 fbr iobsd got"); }
	} else {
		IOLog("!BSD\\n");
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v281 fbr iobsd tmo"); }
	}""",
        "fbr: iobsd wait bracketed",
    )
    s = sub(
        s,
        """	do {
		t.tv_sec = ROOTDEVICETIMEOUT;
		t.tv_nsec = 0;
		matching->retain();
		service = IOService::waitForService( matching, &t );""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 fbr waiting"); }
	do {
		t.tv_sec = ROOTDEVICETIMEOUT;
		t.tv_nsec = 0;
		matching->retain();
		service = IOService::waitForService( matching, &t );""",
        "fbr: final wait probed",
    )
    s = sub(
        s,
        """	OSSafeReleaseNULL(matching);

	if (service && mediaProperty) {""",
        """	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 fbr found"); }
	OSSafeReleaseNULL(matching);

	if (service && mediaProperty) {""",
        "fbr: found probe",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: IOFindBSDRoot bracketed")
else:
    print("IOKitBSDInit.cpp: already patched")

# --- 2. configure loop ----------------------------------------------------
s = read(PLAT)
if MARK not in s:
    # C++ TUs need the file-scope extern "C" declaration (block-scope
    # extern "C" linkage specifications are illegal inside a function).
    s = sub(
        s,
        """extern "C" void g0245d_probe(const char *label);""",
        """extern "C" void g0245d_probe(const char *label);
extern "C" void g0245d_trace_u(const char *label, unsigned int value);""",
        "plat: trace_u extern C at file scope",
    )
    s = sub(
        s,
        """	if (topLevel) {
		while ((dict = OSDynamicCast( OSDictionary,
		    topLevel->getAnyObject()))) {
			dict->retain();
			topLevel->removeObject( dict );
			OSSafeReleaseNULL(nub);
			nub = createNub( dict );
			dict->release();
			if (NULL == nub) {
				continue;
			}
			nub->attach( this );
			nub->registerService();
		}
	}
	OSSafeReleaseNULL(nub);
	return true;
}""",
        """	if (topLevel) {
		static int g0245d_cfg_n;
		while ((dict = OSDynamicCast( OSDictionary,
		    topLevel->getAnyObject()))) {
			g0245d_trace_u("v281 cfg", (unsigned int)++g0245d_cfg_n);
			dict->retain();
			topLevel->removeObject( dict );
			OSSafeReleaseNULL(nub);
			nub = createNub( dict );
			dict->release();
			if (NULL == nub) {
				continue;
			}
			nub->attach( this );
			nub->registerService();
			g0245d_trace_u("v281 cfg reg", (unsigned int)g0245d_cfg_n);
		}
	}
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v281 cfg done"); }
	OSSafeReleaseNULL(nub);
	return true;
}""",
        "plat: configure loop probed",
    )
    write(PLAT, s)
    print("IOPlatformExpert.cpp: configure loop probed")
else:
    print("IOPlatformExpert.cpp: already patched")

print("v281 done")
