#!/usr/bin/env python3
"""v229: follow the kernel out of arm_init and into kernel_bootstrap.

v228 proved the whole body of arm_init() runs: idle init, PE_init_platform(TRUE),
ml_map_cpu_pio, cpu_timebase_init, PE_init_cpu/fiq and the /chosen dram lookups
all returned.  What is left is four lines at the very end of the function:

    __stack_chk_guard = (unsigned long)early_random();
    __stack_chk_guard &= ~(0xFFULL << 8);
    machine_startup(args);          -> machine_conf(); kernel_bootstrap();

All three call sites are outside arm_init.c, so they cannot use the static
g0245d_mark().  v229 therefore exports one text-only checkpoint,
g0245d_trace(), and calls it from prng_random.c, machine_routines.c and
startup.c.  No new colour bands: a band is eight rows tall and row 1900 is the
last free slot above the panel edge.

The high-value addition is kernel_bootstrap_log(): it already runs once per
bootstrap phase, so tracing it turns the quietest part of the boot into a
self-describing log -- whatever phrase sits on the last line of the panel is
the phase that did not return.
"""
import glob
import os
import sys
from pathlib import Path

CANDIDATES = [
    os.path.expanduser('~/g0245d-clean/UniXNU-runtime/out/g0245d/'
                       'ios-16.5-20F66/g0245d/tree/.cache/xnu-work'),
]
CANDIDATES += glob.glob('/home/*/g0245d-clean/UniXNU-runtime/out/g0245d/'
                        '*/g0245d/tree/.cache/xnu-work')

XNU = None
for c in CANDIDATES:
    if os.path.isdir(os.path.join(c, 'osfmk/arm')):
        XNU = Path(c)
        break
if XNU is None:
    sys.exit('cannot find the xnu-work tree; tried %r' % CANDIDATES)
print('tree: %s' % XNU)

ARM = XNU / 'osfmk/arm/arm_init.c'
PRNG = XNU / 'osfmk/prng/prng_random.c'
MACH = XNU / 'osfmk/arm64/machine_routines.c'
START = XNU / 'osfmk/kern/startup.c'

DECL = [
    '',
    '/* g0245d v229: text-only checkpoint, defined in osfmk/arm/arm_init.c.',
    ' * A band is eight rows tall and rows above 1900 are past the panel edge,',
    ' * so everything from here on is console text: one line per checkpoint,',
    ' * the console scrolls, and the last line on the panel is the answer.',
    ' */',
    'extern void g0245d_trace(const char *label);',
    'extern void g0245d_tracev(const char *label, unsigned long long value);',
]

HELPER = [
    '/* g0245d v229: same idea as g0245d_mark(), without the band.  Reachable',
    ' * from any subsystem that repeats the two extern declarations above, and',
    ' * safe to call before the console exists (g0245d_con_printf swallows it).',
    ' */',
    'static unsigned int g0245d_trace_seq;',
    '',
    'void',
    'g0245d_trace(const char *label)',
    '{',
    '\tg0245d_con_printf("%u v229 %s\\n", ++g0245d_trace_seq, label);',
    '\tg0245d_con_sync();',
    '}',
    '',
    'void',
    'g0245d_tracev(const char *label, unsigned long long value)',
    '{',
    '\tg0245d_con_printf("%u v229 %s %p\\n", ++g0245d_trace_seq, label,',
    '\t    (void *)(uintptr_t)value);',
    '\tg0245d_con_sync();',
    '}',
]


def read(p):
    return p.read_text().split('\n')


def write(p, lines):
    p.write_text('\n'.join(lines))


def find(lines, needle, what, exact=False, allow_many=False):
    if exact:
        hits = [i for i, line in enumerate(lines) if line.strip() == needle]
    else:
        hits = [i for i, line in enumerate(lines) if needle in line]
    if not hits:
        sys.exit('anchor missing: %s (%r)' % (what, needle))
    if len(hits) > 1 and not allow_many:
        sys.exit('anchor not unique (%d): %s (%r)' % (len(hits), what, needle))
    return hits[0]


def insert(lines, index, block, what):
    lines[index:index] = block
    print('  insert %-30s at line %d' % (what, index + 1))
    return lines


def replace(lines, needle, new, what, exact=False):
    i = find(lines, needle, what, exact)
    if lines[i] == new:
        print('  skip (already applied): %s' % what)
        return lines
    lines[i] = new
    print('  replace %-29s at line %d' % (what, i + 1))
    return lines


def body_insert(lines, sig, block, what):
    """Insert right after the opening brace that follows a signature line."""
    i = find(lines, sig, what, exact=True)
    j = i + 1
    while j < len(lines) and lines[j].strip() != '{':
        j += 1
    if j >= len(lines):
        sys.exit('no body brace after %s' % what)
    lines[j + 1:j + 1] = block
    print('  body   %-30s at line %d' % (what, j + 1))
    return lines


def main():
    # ---------------------------------------------------------------- arm_init
    src = read(ARM)
    text = '\n'.join(src)
    if 'g0245d_trace_seq' in text:
        print('  skip (already applied): trace helper')
    else:
        insert(src, find(src, '/* ===== g0245d v226 console END ===== */',
                         'console END'), HELPER + [''], 'trace helper')

    src = replace(
        src, 'g0245d_con_printf("G0245D XNU %s %s',
        '\tg0245d_con_printf("G0245D XNU %s %s\\n", "v229", "text trace");',
        'banner version')

    text = '\n'.join(src)
    if 'v229 enter early_random' in text:
        print('  skip (already applied): arm_init tail traces')
    else:
        insert(src, find(src, '__stack_chk_guard = (unsigned long)early_random();',
                         'stack guard seed'),
               ['\tg0245d_trace("v229 enter early_random");'], 'before early_random')
        i = find(src, '__stack_chk_guard &= ~(0xFFULL << 8);', 'stack guard mask')
        insert(src, i + 1, ['\tg0245d_trace("v229 stack guard seeded");'],
               'after guard mask')
        insert(src, find(src, '\tmachine_startup(args);', 'machine_startup call'),
               ['\tg0245d_trace("v229 call machine_startup");'], 'before machine_startup')
    write(ARM, src)

    # ------------------------------------------------------------------- prng
    src = read(PRNG)
    text = '\n'.join(src)
    if 'g0245d v229' in text:
        print('  skip (already applied): prng decls')
    else:
        i = find(src, 'early_random(void)', 'early_random sig', exact=True)
        insert(src, i - 1, DECL + [''], 'prng decls')
    text = '\n'.join(src)
    if 'v229 early_random entered' in text:
        print('  skip (already applied): early_random traces')
    else:
        insert(src, find(src, '\tstatic int init = 0;', 'init flag') + 1,
               ['', '\tg0245d_trace("v229 early_random entered");'], 'after init flag')
        i = find(src, '\t\tbootseed_init();', 'bootseed_init')
        insert(src, i + 1, ['\t\tg0245d_trace("v229 bootseed_init returned");'],
               'after bootseed_init')
        i = find(src, '\t\tnonce = ml_get_timebase();', 'timebase query')
        insert(src, i, ['\t\tg0245d_trace("v229 before ml_get_timebase");'],
               'before ml_get_timebase')
        i = find(src, '\t\tnonce = ml_get_timebase();', 'timebase query')
        insert(src, i + 1, ['\t\tg0245d_tracev("v229 timebase", nonce);'],
               'after ml_get_timebase')
        i = find(src, '\t\tinit = 1;', 'drbg init flag')
        insert(src, i + 1, ['\t\tg0245d_trace("v229 drbg initialised");'],
               'after drbg init')
    write(PRNG, src)

    # -------------------------------------------------------- machine_startup
    src = read(MACH)
    text = '\n'.join(src)
    if 'g0245d v229' in text:
        print('  skip (already applied): machine_routines decls')
    else:
        i = find(src, 'machine_startup(__unused boot_args * args)',
                 'machine_startup sig', exact=True)
        insert(src, i - 1, DECL + [''], 'machine_routines decls')
    text = '\n'.join(src)
    if 'v229 machine_startup entered' in text:
        print('  skip (already applied): machine_startup traces')
    else:
        body_insert(src, 'machine_startup(__unused boot_args * args)',
                    ['\tg0245d_trace("v229 machine_startup entered");'],
                    'machine_startup entry')
        i = find(src, '\tmachine_conf();', 'machine_conf call')
        insert(src, i + 1, ['\tg0245d_trace("v229 machine_conf returned");'],
               'after machine_conf')
        i = find(src, '\tkernel_bootstrap();', 'kernel_bootstrap call')
        insert(src, i, ['\tg0245d_trace("v229 call kernel_bootstrap");'],
               'before kernel_bootstrap')
    write(MACH, src)

    # ------------------------------------------------------ kernel_bootstrap
    src = read(START)
    text = '\n'.join(src)
    if 'g0245d v229' in text:
        print('  skip (already applied): startup decls')
    else:
        i = find(src, 'kernel_bootstrap(void)', 'kernel_bootstrap sig', exact=True)
        insert(src, i - 1, DECL + [''], 'startup decls')
    text = '\n'.join(src)
    if 'v229 kernel_bootstrap entered' in text:
        print('  skip (already applied): kernel_bootstrap traces')
    else:
        i = find(src, '\tboot_progress_stage(message);', 'phase hook',
                 allow_many=True)
        insert(src, i, ['\tg0245d_trace(message);'], 'after phase hook')
        body_insert(src, 'kernel_bootstrap(void)',
                    ['\tg0245d_trace("v229 kernel_bootstrap entered");'],
                    'kernel_bootstrap entry')
    write(START, src)

    print('wrote %s' % XNU)


if __name__ == '__main__':
    main()
