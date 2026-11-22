#!/usr/bin/env python3
"""g0245d v282 -- shorten the IOBSD resource wait to 3 s, probe before it.

v281 boot picture decoded:

  * "v281 fbr enter" (8426) then the full uuid sequence and "v281 cfg done"
     (8435): the matching thread finished IOPlatformExpert::start.  No
     "v281 cfg <N>" probes at all => the top-level set is empty for this
     device tree; configure() loop ran zero iterations.
  * "v281 fbr iobsd got/tmo" NEVER appeared.  The bsd_init thread is still
     inside waitForMatchingService(IOBSD, 30 s) -- or deadlocked inside it.
     Photo is ~90 s after flash; if the wait were healthy it must have
     returned (with a probe!) by now.  Ambiguity remains only if boot is
     slower than assumed.

v282 makes the experiment decisive:

  1. "v282 fbr prewait" right before waitForMatchingService (separates
     serviceMatching construction from the wait itself).
  2. Timeout 30 s -> 3 s.  If "iobsd tmo" appears ~3 s later, the wait
     machinery is healthy and v281's photo was simply early.  If the
     console still freezes after prewait, the wait itself is deadlocked
     and the next iteration goes after IOService::waitForMatchingService.
     The IOBSD wait is only a courtesy wait for filesystem kexts; timing
     out is harmless at this bring-up stage.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSDINIT = os.path.join(WORK, "iokit/bsddev/IOKitBSDInit.cpp")

MARK = "g0245d v282"


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


s = read(BSDINIT)
if MARK not in s:
    s = sub(
        s,
        """	matching->setObject(gIOResourceMatchedKey, gIOBSDKey);

	if ((service = IOService::waitForMatchingService(matching, 30ULL * kSecondScale))) {""",
        """	matching->setObject(gIOResourceMatchedKey, gIOBSDKey);

	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v282 fbr prewait"); }
	/* g0245d v282: 30 s -> 3 s.  The IOBSD resource wait is a courtesy
	 * wait for filesystem kexts; timing out is harmless here, and a 3 s
	 * deadline distinguishes "photo taken too early" from a deadlocked
	 * wait (v281 showed the wait outliving its own 30 s timeout). */
	if ((service = IOService::waitForMatchingService(matching, 3ULL * kSecondScale))) {""",
        "fbr: prewait probe + 3s timeout",
    )
    write(BSDINIT, s)
    print("IOKitBSDInit.cpp: prewait probe + 3s timeout")
else:
    print("IOKitBSDInit.cpp: already patched")

print("v282 done")
