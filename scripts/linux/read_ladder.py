#!/usr/bin/env python3
"""read_ladder.py -- 读「干净屏幕」上的色带阶梯（v215+）。

v215 起，XNU 会在画色带前整屏擦黑（g0245d_fb_wipe），屏幕上除了我们自己画的
横线什么都没有。于是判读退化成一件很笨但很稳的事：

  1. 每行找最长的、颜色饱和且够亮的水平连续段（纯白按亮度单独放行）
  2. 够长（默认 >=400 px）才算一条线
  3. 相邻且同色的行合并成带
  4. 丢掉厚度 >20 px 的亮块（进度条/机身白边/反光，不是色带）

不需要定位屏幕，也不需要几何标定 —— 擦屏之后整块屏就是黑底加几根线。

用法:
  python3 read_ladder.py photo.jpg
  python3 read_ladder.py photo.jpg --manifest band-manifests/v215.json
  python3 read_ladder.py photo.jpg --manifest .../v215.json --json
"""
import sys
import json
import argparse

from PIL import Image

NAMES = [
    ((255, 0, 255), "magenta"),
    ((255, 255, 0), "yellow"),
    ((0, 255, 255), "cyan"),
    ((0, 255, 0), "green"),
    ((0, 0, 255), "blue"),
    ((255, 255, 255), "white"),
    ((255, 0, 0), "red"),
    ((255, 0, 128), "pink"),
    ((0, 128, 255), "azure"),
    ((255, 128, 0), "orange"),
    ((128, 0, 255), "purple"),
    ((255, 192, 0), "gold"),
    ((0, 192, 255), "sky"),
    ((0, 255, 128), "spring"),
    ((0, 128, 128), "teal"),
    ((128, 128, 255), "periwinkle"),
    ((255, 255, 128), "pale-yellow"),
    ((128, 255, 0), "yellow-green"),
]


def name_of(rgb):
    best, bd = "?", None
    for c, n in NAMES:
        d = sum((a - b) ** 2 for a, b in zip(c, rgb))
        if bd is None or d < bd:
            best, bd = n, d
    return best


def dist(c1, c2):
    return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--json", action="store_true", help="结论以 JSON 打到 stdout")
    ap.add_argument("--min-run", type=int, default=400)
    ap.add_argument("--sat", type=int, default=70)
    args = ap.parse_args()

    def say(*a, **k):
        if args.json:
            print(*a, file=sys.stderr, **k)
        else:
            print(*a, **k)

    im = Image.open(args.image).convert("RGB")
    W, H = im.size
    px = im.load()
    say("图片 %s  %dx%d" % (args.image, W, H))

    step = 2
    rows = []
    for y in range(H):
        best_len, best_start, best_sum = 0, -1, [0, 0, 0]
        cur_len, cur_start, cur_sum = 0, -1, [0, 0, 0]
        for x in range(0, W, step):
            r, g, b = px[x, y]
            sat = max(r, g, b) - min(r, g, b)
            ok = (sat >= args.sat and max(r, g, b) >= 90) or (max(r, g, b) >= 200 and sat <= 45)
            if ok:
                if cur_len == 0:
                    cur_start = x
                    cur_sum = [0, 0, 0]
                cur_len += step
                cur_sum[0] += r; cur_sum[1] += g; cur_sum[2] += b
            else:
                if cur_len > best_len:
                    n = max(cur_len // step, 1)
                    best_len = cur_len
                    best_start = cur_start
                    best_sum = [v // n for v in cur_sum]
                cur_len = 0
        if cur_len > best_len:
            n = max(cur_len // step, 1)
            best_len = cur_len
            best_start = cur_start
            best_sum = [v // n for v in cur_sum]
        if best_len >= args.min_run:
            rows.append((y, best_start, best_len, tuple(best_sum)))

    if not rows:
        say("\n没找到任何长横线。屏幕全黑说明擦屏成功但一条带都没画出来。")
        if args.json:
            print(json.dumps({"bands": [], "matched": [], "last_contiguous_checkpoint": None,
                              "next_checkpoint": None, "geometry_valid": False,
                              "reason": "no_band_found"}, ensure_ascii=False))
        return

    bands = []
    for y, x0, ln, rgb in rows:
        if bands and y - bands[-1]["y1"] <= 2 and dist(rgb, bands[-1]["rgb"]) < 90:
            b = bands[-1]
            b["y1"] = y
            b["n"] += 1
            b["rgb"] = tuple((a * (b["n"] - 1) + c) // b["n"] for a, c in zip(b["rgb"], rgb))
        else:
            bands.append({"y0": y, "y1": y, "x0": x0, "len": ln, "rgb": rgb, "n": 1})

    thin = [b for b in bands if 5 <= (b["y1"] - b["y0"] + 1) <= 20]
    dropped = len(bands) - len(thin)
    if dropped:
        say("\n已丢弃 %d 个过厚/过薄的亮块（<5px 是色带边缘反光，>20px 是 UI/机身，都不是色带）" % dropped)
    bands = thin

    if not bands:
        say("\n只找到厚亮块，没有色带。")
        if args.json:
            print(json.dumps({"bands": [], "matched": [], "last_contiguous_checkpoint": None,
                              "next_checkpoint": None, "geometry_valid": False,
                              "reason": "only_thick_blocks"}, ensure_ascii=False))
        return

    say("\n=== 自上而下的色带（共 %d 条） ===" % len(bands))
    say(" #  y范围       厚度  x起  长度   实测RGB            名称")
    for i, b in enumerate(bands, 1):
        say(" %2d %4d-%4d  %4d  %4d %5d  (%3d,%3d,%3d)  %s"
            % (i, b["y0"], b["y1"], b["y1"] - b["y0"] + 1, b["x0"], b["len"],
               b["rgb"][0], b["rgb"][1], b["rgb"][2], name_of(b["rgb"])))

    if not args.manifest:
        return

    man = json.load(open(args.manifest, encoding="utf-8"))
    cps = man["checkpoints"]
    say("\n=== 对表（%s） ===" % man.get("version", "?"))

    # --- 几何定标 ---
    # 色带之间的行距是固定的（20 行），相机偏色会让颜色不可信，但 y 位置不会骗人。
    # 先由相邻带的中位间距求 px/20行，再暴力试「哪条带 = 哪个打点」当锚点，
    # 选整体色差最小的那组分配；最后要求 rows 随 y 严格递减。
    ys = [b["y0"] for b in bands]
    diffs = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    unit = None
    if diffs:
        cand = [d for d in diffs if d >= 8]     # 2-4px 的亮边不是带间隔
        if not cand:
            cand = diffs
        cand.sort()
        unit = cand[len(cand) // 2]             # 中位数：多数相邻带正好是 20 行
    say("\n几何定标：相邻带中位间距 %.1f px = 20 行" % (unit or 0))

    best_assign, best_score = None, None
    if unit:
        for ai, a in enumerate(bands):
            for c in cps:
                assign, score = [], 0.0
                for b in bands:
                    pred = c["row"] - (b["y0"] - a["y0"]) / unit * 20.0
                    near = min(cps, key=lambda k: abs(k["row"] - pred))
                    d = dist(b["rgb"], tuple(near["rgb"]))
                    score += min(d, 200.0)
                    assign.append((b, near, pred, d))
                # 同一条带不许被分到两个不同行，且行号必须随 y 单调递减
                rows_seq = [t[1]["row"] for t in assign]
                if len(set(rows_seq)) != len(rows_seq):
                    score += 200.0 * (len(rows_seq) - len(set(rows_seq)))
                if any(rows_seq[i] <= rows_seq[i + 1] for i in range(len(rows_seq) - 1)):
                    score += 400.0
                if best_score is None or score < best_score:
                    best_score, best_assign = score, assign

    matched = []
    say("")
    for b, near, pred, d in (best_assign or []):
        matched.append({"row": near["row"], "note": near["note"], "order": near["order"],
                        "y": b["y0"], "rgb": list(b["rgb"]), "dist": round(d, 1),
                        "pred_row": round(pred, 1)})
        flag = "" if d < 130 else "   << 颜色与打点不符，仅按位置归属"
        say("  y=%4d  row %4d (拟合%5.0f)  %-34s 色差%3.0f%s"
            % (b["y0"], near["row"], pred, near["note"], d, flag))

    matched.sort(key=lambda m: m["order"])
    last = matched[-1] if matched else None
    nxt = None
    if last:
        nxt = next((c for c in cps if c["order"] == last["order"] + 1), None)

    rows_hit = sorted({m["row"] for m in matched})
    say("\n命中行号（升序）:", ", ".join(str(r) for r in rows_hit))
    if last:
        say("按执行顺序最后一条: row %d  %s" % (last["row"], last["note"]))
    if nxt:
        say("下一条应出现但未出现: row %d  %s" % (nxt["row"], nxt["note"]))
        say("\n>>> 卡点：row %d 与 row %d 之间" % (last["row"], nxt["row"]))

    if args.json:
        print(json.dumps({
            "bands": [{"y0": b["y0"], "y1": b["y1"], "rgb": list(b["rgb"]), "name": name_of(b["rgb"])}
                      for b in bands],
            "matched": matched,
            "last_contiguous_checkpoint": last,
            "next_checkpoint": nxt,
            "geometry_valid": len(matched) > 0,
            "reason": "ok" if matched else "no_manifest_match",
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
