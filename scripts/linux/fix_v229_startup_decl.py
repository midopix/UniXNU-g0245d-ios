#!/usr/bin/env python3
"""v229 fix: startup.c uses g0245d_trace() in kernel_bootstrap_log() at line
225, but the declaration had been inserted next to kernel_bootstrap() at line
432, so the first call was an implicit declaration and the second one
conflicted with it.  Move the block above the first use.
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
    sys.exit('no tree')

START = os.path.join(XNU, 'osfmk/kern/startup.c')
lines = open(START).read().split('\n')

BEGIN = '/* g0245d v229: text-only checkpoint, defined in osfmk/arm/arm_init.c.'
END = 'extern void g0245d_tracev(const char *label, unsigned long long value);'

if not any(l.strip() == BEGIN for l in lines):
    sys.exit('declaration block not found')

i = next(i for i, l in enumerate(lines) if l.strip() == BEGIN)
j = next(k for k in range(i, len(lines)) if lines[k].strip() == END)
block = lines[i:j + 1]
del lines[i:j + 1]

anchor = next(k for k, l in enumerate(lines)
              if 'TUNABLE(startup_debug_t, startup_debug' in l)
lines[anchor:anchor] = block + ['']
print('moved %d lines above line %d' % (len(block), anchor + 1))

open(START, 'w').write('\n'.join(lines))

first_use = next(k for k, l in enumerate(lines) if 'g0245d_trace(message)' in l)
print('first use now at line %d, declaration ends at line %d'
      % (first_use + 1, anchor + len(block)))
