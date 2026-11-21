#!/usr/bin/env python3
"""read_bands2.py - robust colour-band reader for the G0245D probe ladder.

Why this exists: read_ladder.py matched colours one by one, which broke as soon
as the camera shifted a hue (magenta -> purple, yellow -> gold) or a thin 6 px
band got dropped by the thickness filter. This version:

  1. finds local maxima of the per-row brightness profile (no thickness filter,
     so 6 px bands survive),
  2. estimates the lattice pitch from the median gap,
  3. RANSAC-fits the affine map "panel row -> photo y" using every checkpoint
     in the manifest as a possible anchor, scoring assignments by colour
     distance plus monotonicity,
  4. prints the matched ladder and the first checkpoint that is missing.

Usage:
  read_bands2.py photo.jpg --manifest band-manifests/v221.json [--json]
"""
import argparse
import json
import math
import sys

from PIL import Image


def say(*a):
    print(*a)


def screen_bounds(px, w, h):
    """The glass is either dark or strongly coloured; the body/bezel is bright
    and desaturated. Classify per row, then take the longest contiguous run.

    A plain "luminance < 50" test fails as soon as a bright band (cyan, yellow)
    sits in the middle of the screen: the run breaks at every band and the
    lower empty area wins.
    """
    def row_stat(y):
        r = g = b = n = 0
        for x in range(int(w * 0.28), int(w * 0.72), 4):
            rr, gg, bb = px[x, y]
            r += rr
            g += gg
            b += bb
            n += 1
        r //= n
        g //= n
        b //= n
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        chroma = max(r, g, b) - min(r, g, b)
        return lum, chroma

    dark = [y for y in range(h) if (lambda s: s[0] < 62 or s[1] > 35)(row_stat(y))]
    if not dark:
        return 0, h - 1
    # take the longest contiguous dark run
    best, cur = (dark[0], dark[0]), (dark[0], dark[0])
    for y in dark[1:]:
        # tolerate a ~26 px hole: a pure white band (row 1660) is bright and
        # desaturated, so it looks exactly like bezel and would otherwise cut
        # the screen into pieces.
        if y - cur[1] <= 26:
            cur = (cur[0], y)
        else:
            if cur[1] - cur[0] > best[1] - best[0]:
                best = cur
            cur = (y, y)
    if cur[1] - cur[0] > best[1] - best[0]:
        best = cur
    return best


def profile(px, w, y0, y1):
    rows = []
    for y in range(y0, y1 + 1):
        r = g = b = n = 0
        for x in range(int(w * 0.16), int(w * 0.80), 4):
            rr, gg, bb = px[x, y]
            r += rr
            g += gg
            b += bb
            n += 1
        rows.append((y, r // n, g // n, b // n, max(r // n, g // n, b // n)))
    return rows


def find_bands(rows, thresh=85):
    peaks = []
    for i in range(2, len(rows) - 2):
        y, r, g, b, m = rows[i]
        if m < thresh:
            continue
        if m >= rows[i - 1][4] and m >= rows[i + 1][4] and \
           m > rows[i - 2][4] and m > rows[i + 2][4]:
            peaks.append([y, r, g, b, m])
    merged = []
    for p in peaks:
        if merged and p[0] - merged[-1][0] < 10:
            if p[4] > merged[-1][4]:
                merged[-1] = p
        else:
            merged.append(p)
    return merged


def cdist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def fit(bands, cps, unit):
    """RANSAC over anchors: row = r0 for band k, pitch = unit px per 20 rows.

    Bands that match nothing are outliers (reflections, glare, a 3 px bezel
    edge), not a reason to reject the whole hypothesis: score by inlier count
    and break ties on colour distance.
    """
    best = None
    b_per_row = unit / 20.0
    for k, band in enumerate(bands):
        for cp in cps:
            a = band[0] - b_per_row * (1919 - cp["row"])
            used = {}
            cost = 0.0
            for bd in bands:
                row = 1919 - (bd[0] - a) / b_per_row
                near = min(cps, key=lambda c: abs(c["row"] - row))
                if abs(near["row"] - row) > 12:
                    continue
                d = cdist(bd[1:4], near["rgb"])
                if d > 175:
                    continue
                if near["row"] in used and used[near["row"]][0] <= d:
                    continue
                used[near["row"]] = (d, bd)
                cost += d
            score = (len(used), -cost)
            if best is None or score > best[0]:
                best = (score, a, b_per_row, used)
    if best is None:
        return None
    return (best[0][1], best[1], best[2], best[3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photo")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    im = Image.open(args.photo).convert("RGB")
    w, h = im.size
    px = im.load()
    y0, y1 = screen_bounds(px, w, h)
    rows = profile(px, w, y0, y1)
    bands = find_bands(rows)
    if not bands:
        say("no bands found")
        return 1

    gaps = sorted(bands[i + 1][0] - bands[i][0] for i in range(len(bands) - 1))
    small = [g for g in gaps if g >= 8]
    unit = sorted(small)[len(small) // 2] if small else 20.0

    man = json.load(open(args.manifest))
    cps = man["checkpoints"]
    best = fit(bands, cps, unit)
    if best is None:
        say("fit failed: bands=%d pitch=%.1f" % (len(bands), unit))
        return 2
    cost, a, b_per_row, used = best

    if not args.json:
        say("photo %dx%d   screen y %d..%d" % (w, h, y0, y1))
        say("bands %d   pitch %.1f px / 20 rows   inliers %d" %
            (len(bands), unit, len(used)))
        say("")
        say("  row   y     measured RGB      checkpoint")
        for row in sorted(used, reverse=True):
            d, bd = used[row]
            note = next(c["note"] for c in cps if c["row"] == row)
            flag = "" if d < 110 else "   (colour off %.0f, position only)" % d
            say("  %4d  %4d  (%3d,%3d,%3d)   %s%s" % (row, bd[0], bd[1], bd[2], bd[3], note, flag))

    order = {c["row"]: c["order"] for c in cps}
    hits = sorted(used, key=lambda r: order[r])
    started = [r for r in hits]
    last = hits[-1] if hits else None
    missing = [c for c in sorted(cps, key=lambda c: c["order"])
               if c["order"] > order.get(last, -1)]
    nxt = missing[0] if missing else None
    if not args.json:
        say("")
        say("执行顺序最后一条: row %s" % last)
        say("下一条应出现但未出现: row %s  %s" % (nxt["row"], nxt["note"]) if nxt else "全部命中")
    if args.json:
        print(json.dumps({"hits": hits, "last": last,
                          "next": nxt["row"] if nxt else None,
                          "next_note": nxt["note"] if nxt else None,
                          "bands": len(bands), "pitch": unit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
