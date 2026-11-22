#!/usr/bin/env python3
"""v230: stop the firehose, and give the panel a fixed status row.

v229's photo is unambiguous but misleading: 3,819 trace lines, the last two
thousand of them *all* `v229 early_random entered`.  That is not a loop.
`zalloc_random_mask64()` is `early_random() & mask` on arm64, so every zoned
allocation asks for a random index; kernel_bootstrap allocates constantly.
The kernel was moving; our own tracing was drowning the evidence.

Two fixes, both about legibility rather than progress:

1. Trace early_random() only on its first (initialising) call, plus a
   heartbeat every 1024 calls so a long allocation burst still shows motion.

2. Reserve the last console row for a status line.  Text now scrolls in rows
   0..rows-2, and row rows-1 always shows the most recent boot phase, so no
   amount of ordinary output can hide where the kernel actually is.
   kernel_bootstrap_log() drives it, which means every phase name is pinned
   to the bottom of the screen.

Also drops the doubled version tag: v229 printed "%u v229 %s" while the labels
themselves already began with "v229", so every line read "3020 v229 v229 ...".
"""
import glob
import os
import sys

CANDIDATES = [
    os.path.expanduser('~/g0245d-clean/UniXNU-runtime/out/g0245d/'
                       'ios-16.5-20F66/g0245d/tree/.cache/xnu-work'),
]
CANDIDATES += glob.glob('/home/*/g0245d-clean/UniXNU-runtime/out/g0245d/'
                        '*/g0245d/tree/.cache/xnu-work')
XNU = next((c for c in CANDIDATES if os.path.isdir(os.path.join(c, 'osfmk/arm'))), None)
if XNU is None:
    sys.exit('cannot find xnu-work')

ARM = os.path.join(XNU, 'osfmk/arm/arm_init.c')
PRNG = os.path.join(XNU, 'osfmk/prng/prng_random.c')
MACH = os.path.join(XNU, 'osfmk/arm64/machine_routines.c')
START = os.path.join(XNU, 'osfmk/kern/startup.c')


def sub(path, old, new, what):
    src = open(path).read()
    if new in src and old not in src:
        print('  skip (already applied): %s' % what)
        return
    if src.count(old) != 1:
        sys.exit('anchor %r hit %d times (%s)' % (old[:60], src.count(old), what))
    open(path, 'w').write(src.replace(old, new, 1))
    print('  patch %-40s %r' % (what, old[:52].replace('\n', ' ')))


# ---------------------------------------------------------------- status row
sub(ARM,
    'static unsigned int  g0245d_con_rows;\n',
    'static unsigned int  g0245d_con_rows;\n'
    'static unsigned int  g0245d_con_nscroll;  /* g0245d v230: rows - 1 */\n',
    'nscroll variable')

sub(ARM,
    '\tg0245d_con_rows = G0245D_CON_TOP / G0245D_CON_CH;\n',
    '\tg0245d_con_rows = G0245D_CON_TOP / G0245D_CON_CH;\n'
    '\t/* g0245d v230: keep the last row out of the scroll ring so it can\n'
    '\t * hold a status line that never scrolls away. */\n'
    '\tg0245d_con_nscroll = (g0245d_con_rows > 1) ?\n'
    '\t    g0245d_con_rows - 1 : g0245d_con_rows;\n',
    'nscroll in init')

sub(ARM,
    '\t\tg0245d_con_row = (g0245d_con_row + 1) % g0245d_con_rows;\n',
    '\t\tg0245d_con_row = (g0245d_con_row + 1) % g0245d_con_nscroll;\n',
    'scroll ring')

# the status row is below the top of the ring, so flush the whole text area
sub(ARM,
    '\tend = (unsigned long)g0245d_con_base\n'
    '\t    + (unsigned long)(g0245d_con_row + 1) * G0245D_CON_CH * g0245d_con_stride;\n',
    '\t/* g0245d v230: the status row sits below the scroll cursor, so flush\n'
    '\t * every text row instead of only the ones above the cursor. */\n'
    '\tend = (unsigned long)g0245d_con_base\n'
    '\t    + (unsigned long)g0245d_con_rows * G0245D_CON_CH * g0245d_con_stride;\n',
    'sync range')

STATUS = '''
/* g0245d v230: one fixed line at the bottom of the text area.  Ordinary
 * traces scroll through rows 0..rows-2; this row is never part of the ring,
 * so the last phase to call it stays on screen no matter how much output
 * follows.  Pass a short label; it is clipped to the panel width.
 */
void
g0245d_status(const char *label)
{
	unsigned int    row = g0245d_con_row;
	unsigned int    col = g0245d_con_col;
	unsigned int    i;

	if (!g0245d_con_ready || g0245d_con_rows < 2 || label == 0) {
		return;
	}
	g0245d_con_row = g0245d_con_rows - 1;
	g0245d_con_col = 0;
	g0245d_con_fill_row(g0245d_con_row);
	g0245d_con_putc('>');
	for (i = 1; i + 1 < g0245d_con_cols && label[i - 1]; i++) {
		g0245d_con_putc(label[i - 1]);
	}
	g0245d_con_row = row;
	g0245d_con_col = col;
	g0245d_con_sync();
}
'''

sub(ARM,
    'static void\ng0245d_con_putu(unsigned long v, unsigned int base, unsigned int pad)\n',
    STATUS + '\nstatic void\ng0245d_con_putu(unsigned long v, unsigned int base, unsigned int pad)\n',
    'status function')

# --------------------------------------------------- trace format, no doubles
sub(ARM,
    '\tg0245d_con_printf("%u v229 %s\\n", ++g0245d_trace_seq, label);\n',
    '\tg0245d_con_printf("%u %s\\n", ++g0245d_trace_seq, label);\n',
    'trace format')

sub(ARM,
    '\tg0245d_con_printf("%u v229 %s %p\\n", ++g0245d_trace_seq, label,\n',
    '\tg0245d_con_printf("%u %s %p\\n", ++g0245d_trace_seq, label,\n',
    'tracev format')

sub(ARM,
    '\tg0245d_con_printf("G0245D XNU %s %s\\n", "v229", "text trace");\n',
    '\tg0245d_con_printf("G0245D XNU %s %s\\n", "v230", "trace+status");\n',
    'banner')

# labels carry the version now that the format string no longer does
for path in (ARM, PRNG, MACH, START):
    src = open(path).read()
    if '"v229 ' in src:
        open(path, 'w').write(src.replace('"v229 ', '"v230 '))
        print('  relabel %s' % os.path.basename(path))

# --------------------------------------------------------- early_random noise
sub(PRNG,
    '\tg0245d_trace("v230 early_random entered");\n',
    '\tg0245d_er_calls++;\n'
    '\t/* g0245d v230: zalloc_random_mask64() calls this on every zoned\n'
    '\t * allocation, so trace only the first call and then a heartbeat. */\n',
    'early_random throttle')

sub(PRNG,
    '\tif (init == 0) {\n\t\tbootseed_init();\n',
    '\tif (init == 0) {\n'
    '\t\tg0245d_trace("v230 early_random first call");\n'
    '\t\tbootseed_init();\n',
    'early_random first-call trace')

sub(PRNG,
    '\tconst char ps[] = "xnu early random";\n'
    '\tstatic int init = 0;\n',
    '\tconst char ps[] = "xnu early random";\n'
    '\tstatic int init = 0;\n'
    '\tstatic unsigned int g0245d_er_calls;\n',
    'early_random counter')

sub(PRNG,
    '\tread_erandom(&result, sizeof(result));\n',
    '\tif (g0245d_er_calls > 1 && (g0245d_er_calls & 0x3FF) == 0) {\n'
    '\t\tg0245d_tracev("v230 early_random calls", g0245d_er_calls);\n'
    '\t}\n'
    '\tread_erandom(&result, sizeof(result));\n',
    'early_random heartbeat')

# ------------------------------------------------- pin the phase to the status
sub(START,
    'extern void g0245d_trace(const char *label);\n',
    'extern void g0245d_trace(const char *label);\n'
    'extern void g0245d_status(const char *label);\n',
    'status declaration')

sub(START,
    '\tg0245d_trace(message);\n'
    '\tboot_progress_stage(message);\n',
    '\tg0245d_trace(message);\n'
    '\tg0245d_status(message);\n'
    '\tboot_progress_stage(message);\n',
    'status in kernel_bootstrap_log')

sub(MACH,
    'extern void g0245d_trace(const char *label);\n',
    'extern void g0245d_trace(const char *label);\n'
    'extern void g0245d_status(const char *label);\n',
    'status declaration (mach)')

sub(MACH,
    '\tg0245d_trace("v230 machine_startup entered");\n',
    '\tg0245d_trace("v230 machine_startup entered");\n'
    '\tg0245d_status("machine_startup");\n',
    'status at machine_startup')

print('done')
