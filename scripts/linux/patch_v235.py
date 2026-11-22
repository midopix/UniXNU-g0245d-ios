#!/usr/bin/env python3
"""g0245d v235 -- bracket the last static constructor call.

v234's photo ends at "75 v234 structors section" with the pinned row reading
"97 fffffff0079b90fc".  That address is __GLOBAL__sub_I_bootstrap.cpp, the
last entry of the kernel's __mod_init_func, and its body is four instructions
(two ADR + two STR).  Nothing in it can block, so the stop is either in the
call itself, in OSMetaClass::checkModLoad() right after it, or in the segment
walk that follows.

v235 brackets every step of that window:

  * "v235 ctor enter" / "v235 ctor ret" around the call, for index >= 96 only
  * "v235 boot ctor enter" / "ret" inside KLDBootstrap::KLDBootstrap()
  * "v235 sect checked" after the trailing checkModLoad()
  * "v235 seg <name>" after each segment the walker finishes

so one photo names the exact instruction that does not return.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

ARM = os.path.join(WORK, "osfmk/arm/arm_init.c")
OSR = os.path.join(WORK, "libkern/c++/OSRuntime.cpp")
BSP = os.path.join(WORK, "libsa/bootstrap.cpp")

MARK = "g0245d v235"


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


# ---------------------------------------------------------------- arm_init.c
s = read(ARM)
if MARK not in s:
    anchor = """void
g0245d_tracev(const char *label, unsigned long long value)
{
	g0245d_con_printf("%u %s %p\\n", ++g0245d_trace_seq, label,
	    (void *)(uintptr_t)value);
	g0245d_con_sync();
}
"""
    add = anchor + """
/* g0245d v235: trace that carries a Mach-O segment name.  segname is
 * char[16] and is not guaranteed to be NUL-terminated, so copy first.
 */
void
g0245d_trace_seg(const char *label, const char *segname)
{
	char           buf[17];
	unsigned int   i;

	if (!g0245d_con_ready) {
		return;
	}
	for (i = 0; i < 16 && segname != 0 && segname[i] != '\\0'; i++) {
		buf[i] = segname[i];
	}
	buf[i] = '\\0';
	g0245d_con_printf("%u %s %s\\n", ++g0245d_trace_seq, label, buf);
	g0245d_con_sync();
}
"""
    s = sub(s, anchor, add, "arm_init: g0245d_trace_seg")
    write(ARM, s)
    print("arm_init: g0245d_trace_seg added")
else:
    print("arm_init: already patched")

# --------------------------------------------------------------- OSRuntime.cpp
s = read(OSR)
if MARK not in s:
    s = sub(
        s,
        'extern "C" void g0245d_probe_pc(uintptr_t pc, unsigned int idx);',
        'extern "C" void g0245d_probe_pc(uintptr_t pc, unsigned int idx);\n'
        'extern "C" void g0245d_trace_seg(const char *label, const char *segname);',
        "OSRuntime: extern g0245d_trace_seg")

    s = sub(
        s,
        """				g0245d_probe_pc(value,
				    g0245d_structor_index++);
				(*structor)();""",
        """				unsigned int thisIdx = g0245d_structor_index++;
				g0245d_probe_pc(value, thisIdx);
				/* g0245d v235: bracket the call.  __DATA_CONST
				 * holds the 96 real constructors; 96 is the
				 * _last_kernel_constructor label and 97 is the
				 * two-store stub in libsa/bootstrap.cpp, so an
				 * "enter" without a "ret" can only mean the
				 * call itself never came back.
				 */
				if (thisIdx >= 96) {
					g0245d_trace("v235 ctor enter");
				}
				(*structor)();
				if (thisIdx >= 96) {
					g0245d_trace("v235 ctor ret");
				}""",
        "OSRuntime: bracket the structor call")

    s = sub(
        s,
        """		if (metaHandle) {
			result = OSMetaClass::checkModLoad(metaHandle);
		}
		break;""",
        """		if (metaHandle) {
			result = OSMetaClass::checkModLoad(metaHandle);
		}
		/* g0245d v235: the trailing checkModLoad() is the last call
		 * before the walker moves on; a hang here leaves the pinned
		 * row on the constructor that had just been run.
		 */
		g0245d_trace("v235 sect checked");
		break;""",
        "OSRuntime: trace after checkModLoad")

    s = sub(
        s,
        """		load_success = OSRuntimeCallStructorsInSection(
			theKext, kmodInfo, metaHandle, segment,
			sectionNames[kOSSectionNameInitializer],
			textStart, textEnd);""",
        """		load_success = OSRuntimeCallStructorsInSection(
			theKext, kmodInfo, metaHandle, segment,
			sectionNames[kOSSectionNameInitializer],
			textStart, textEnd);
		/* g0245d v235: name every segment the walker finishes, so a
		 * stop between two segments is visible.
		 */
		g0245d_trace_seg("v235 seg", segment->segname);""",
        "OSRuntime: trace per segment")

    write(OSR, s)
    print("OSRuntime: v235 traces added")
else:
    print("OSRuntime: already patched")

# ------------------------------------------------------------ libsa/bootstrap.cpp
s = read(BSP)
if MARK not in s:
    s = sub(
        s,
        "#define IOKIT_ENABLE_SHARED_PTR\n",
        """#define IOKIT_ENABLE_SHARED_PTR

/* g0245d v235: framebuffer console, from osfmk/arm/arm_init.c.  This file's
 * static constructor is the last entry of the kernel's __mod_init_func, so an
 * enter/exit pair here says whether the caller reached it at all.
 */
extern "C" void g0245d_trace(const char *label);
""",
        "bootstrap: extern g0245d_trace")

    s = sub(
        s,
        """KLDBootstrap::KLDBootstrap(void)
{
	if (this != &sBootstrapObject) {""",
        """KLDBootstrap::KLDBootstrap(void)
{
	g0245d_trace("v235 boot ctor enter");
	if (this != &sBootstrapObject) {""",
        "bootstrap: ctor enter")

    s = sub(
        s,
        """	record_startup_extensions_function = &bootstrapRecordStartupExtensions;
	load_security_extensions_function = &bootstrapLoadSecurityExtensions;
}""",
        """	record_startup_extensions_function = &bootstrapRecordStartupExtensions;
	load_security_extensions_function = &bootstrapLoadSecurityExtensions;
	g0245d_trace("v235 boot ctor ret");
}""",
        "bootstrap: ctor ret")

    write(BSP, s)
    print("bootstrap: v235 traces added")
else:
    print("bootstrap: already patched")

print("v235 patch applied")
