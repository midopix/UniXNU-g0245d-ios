#!/usr/bin/env python3
"""v224: locate the new halt between serial_init() and PE_init_printf().

v223 result: every mark up to 1380 (serial_init returned) is on screen, 1360
(PE_init_printf returned) is not -- and with TTBR0 kept alive that is a real
absence, not a blind probe.  So the boot now stops somewhere in:

    kernel_startup_initialize_upto(STARTUP_SUB_KPRINTF) -> kprintf() ->
    serial boot-arg parsing -> PE_create_console() -> PE_init_printf()

Four marks bisect that window on rows 1080..1140 (free strip between 1060 and
1360; panel mapping line = 1919 - row, 20 rows per slot):

    1080 RGB(0,255,0)    green   startup_initialize_upto(KPRINTF) returned
    1100 RGB(255,0,0)    red     kprintf("kprintf initialized") returned
    1120 RGB(255,0,255)  magenta serial boot-arg block finished
    1140 RGB(0,0,255)    blue    PE_create_console() returned

1360 stays as the "PE_init_printf returned" marker, so the first missing one
pinpoints the call that never returns.
"""
import os
from pathlib import Path

BASE = Path(os.environ.get('G0245D_BASE', str(Path.home() / 'g0245d-clean'))
            + '/UniXNU-runtime/out/g0245d/ios-16.5-20F66/'
            'g0245d/tree/.cache/xnu-work')
p = BASE / 'osfmk/arm/arm_init.c'
lines = p.read_text().split('\n')

if any('g0245d v224' in l for l in lines):
    print('already patched, nothing to do')
    raise SystemExit(0)


def find(anchor, occurrence=1):
    seen = 0
    for i, l in enumerate(lines):
        if l.strip() == anchor:
            seen += 1
            if seen == occurrence:
                return i
    raise SystemExit('anchor not found: %r' % anchor)


def mark(row, g, r, b, what):
    return ('\tg0245d_fb_band(args, %d, 0x%02X, 0x%02X, 0x%02X);\t'
            '/* g0245d v224: %s */' % (row, g, r, b, what))


def after(anchor, text):
    i = find(anchor)
    lines[i + 1:i + 1] = [text]


def before(anchor, text):
    i = find(anchor)
    lines[i:i] = [text]


after('kernel_startup_initialize_upto(STARTUP_SUB_KPRINTF);',
      mark(1080, 0x00, 0xFF, 0x00, 'kprintf subsystem up'))

after('kprintf("kprintf initialized\\n");',
      mark(1100, 0xFF, 0x00, 0x00, 'first kprintf returned'))

before('/* Start serial if requested and a serial device was enumerated in serial_init(). */',
       mark(1120, 0xFF, 0x00, 0xFF, 'serial boot-arg block done'))

after('PE_create_console();',
      mark(1140, 0x00, 0x00, 0xFF, 'PE_create_console returned'))

p.write_text('\n'.join(lines))
src = p.read_text()
print('arm_init.c patched for v224')
for key in ('1080, 0x00, 0xFF, 0x00', '1100, 0xFF, 0x00, 0x00',
            '1120, 0xFF, 0x00, 0xFF', '1140, 0x00, 0x00, 0xFF',
            '1360, 0xE0, 0xFF, 0xE0'):
    print('  %-24s %s' % (key, 'present' if key in src else 'ABSENT'))
