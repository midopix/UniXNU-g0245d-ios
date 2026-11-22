#!/usr/bin/env python3
"""Build a band manifest straight from the XNU sources.

Every probe the G0245D port paints is one of

    g0245d_fb_band(args, <row>, 0xG, 0xR, 0xB)
    g0245d_wfe_mark(<row>, 0xG, 0xR, 0xB, value)
    g0245d_band_here(<row>, 0xG, 0xR, 0xB)

The three colour bytes are stored as byte0=G, byte1=R, byte2=B and the
panel scans them out as (R,G,B) -- so the colour you see on screen is
(r, g, b), i.e. the last two arguments swapped relative to the source
order.  Getting that backwards is what made the v215/v224 manifests
wrong, so this script is now the only source of truth for manifests.

usage:
    gen_manifest.py <xnu-work-dir> [--version v225] [-o out.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

FILES = [
    'osfmk/arm/arm_init.c',
    'osfmk/arm/rtclock.c',
    'osfmk/arm64/arm_vm_init.c',
    'osfmk/arm/machine_routines.c',
    'osfmk/arm64/machine_routines.c',
    'pexpert/arm/pe_init.c',
    'osfmk/prng/prng_random.c',
    'osfmk/kern/startup.c',
]

# v229: probes past row 1900 have no room for a band, so they are text only.
TRACE_PAT = re.compile(r'g0245d_tracev?\s*\(\s*"([^"]*)"')

# Probes whose colour is a runtime ternary cannot be resolved statically.
# Keyed by row, value = (normal branch rgb, fallback branch rgb, what decides).
OVERRIDES = {
    640: ((255, 255, 0), (0, 0, 120), 'yellow = fb PA inside [gPhysBase,+real_phys_size); deep blue = outside'),
    660: ((0, 255, 255), (255, 0, 255), 'cyan = g0245d_fb_kva() != 0; magenta = it returned 0'),
}

NUM = r'(0x[0-9A-Fa-f]+|\d+)'

PATTERNS = [
    (re.compile(r'g0245d_fb_band\s*\(\s*[^,]+,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM), 1),
    (re.compile(r'g0245d_wfe_mark\s*\(\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM), 1),
    (re.compile(r'g0245d_band_here\s*\(\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM), 1),
    # v226: every band call in arm_init.c goes through g0245d_mark(), which
    # also prints a text line; the trailing string is the note.
    (re.compile(r'g0245d_mark\s*\(\s*[^,]+,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*,\s*"([^"]*)"'), 1),
]


def val(tok):
    return int(tok, 0)


def collect(root):
    found = []
    for rel in FILES:
        p = Path(root) / rel
        if not p.exists():
            continue
        for lineno, line in enumerate(p.read_text(errors='replace').split('\n'), 1):
            if line.lstrip().startswith('*') or line.lstrip().startswith('/*'):
                continue
            for pat, _ in PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                row, g, r, b = (val(m.group(i)) for i in range(1, 5))
                note = ''
                if m.lastindex and m.lastindex >= 5 and m.group(5):
                    note = m.group(5).strip()
                elif '/*' in line:
                    note = line.split('/*', 1)[1].strip()
                    if note.endswith('*/'):
                        note = note[:-2].strip()
                elif '//' in line:
                    note = line.split('//', 1)[1].strip()
                found.append({
                    'row': row,
                    'rgb': [r, g, b],
                    'g_r_b': [g, r, b],
                    'note': note,
                    'source': '%s:%d' % (rel, lineno),
                })
                break
    return found


def collect_traces(root):
    """v229: text-only checkpoints, in source order."""
    out = []
    for rel in FILES:
        p = Path(root) / rel
        if not p.exists():
            continue
        for lineno, line in enumerate(p.read_text(errors='replace').split('\n'), 1):
            if line.lstrip().startswith('*') or line.lstrip().startswith('/*'):
                continue
            m = TRACE_PAT.search(line)
            if m:
                out.append({'label': m.group(1).strip(),
                            'source': '%s:%d' % (rel, lineno)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tree')
    ap.add_argument('--version', default='')
    ap.add_argument('-o', '--out', default='')
    a = ap.parse_args()

    items = collect(a.tree)
    if not items:
        sys.exit('no probes found under %s' % a.tree)

    # rows whose colour is a runtime branch
    seen = {it['row'] for it in items}
    for row, (normal, alt, why) in OVERRIDES.items():
        if row in seen:
            continue
        items.append({
            'row': row,
            'rgb': list(normal),
            'rgb_if_false': list(alt),
            'note': why,
            'source': 'override',
        })

    # one checkpoint per row; a row painted twice keeps the last write
    by_row = {}
    for it in items:
        by_row[it['row']] = it
    rows = [by_row[r] for r in sorted(by_row, reverse=True)]
    for i, it in enumerate(rows):
        it['order'] = i + 1

    doc = {
        'version': a.version or 'unknown',
        'generated_by': 'scripts/linux/gen_manifest.py',
        'mapping': 'panel line = 1919 - row; top of screen = largest row',
        'color_note': 'rgb here is what the panel shows: byte0=G, byte1=R, byte2=B',
        'checkpoints': rows,
        'traces': collect_traces(a.tree),
    }
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text)
        print('%d checkpoints -> %s' % (len(rows), a.out))
    else:
        print(text)


if __name__ == '__main__':
    main()
