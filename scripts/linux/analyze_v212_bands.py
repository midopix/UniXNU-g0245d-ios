#!/usr/bin/env python3
"""G0245D v212 色带照片自动判读。

用法: analyze-v212-bands.py <照片> [--json out.json]

判读规则来自 docs/bringup/cards/G0245D-v210-v212-EARLY-INIT-BISECT.md：
屏幕从上到下 = 执行顺序从晚到早；颜色会重复，必须靠“顺序 + 颜色”联合对齐。
输出最高存在的 raw 行号，以及死亡区间（最高存在点 -> 下一个未出现点）。
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow: 在 WSL venv 中 pip install pillow")

# (raw 行, 屏幕 RGB, 说明)，顺序 = 屏幕从上到下 = 执行从晚到早
BANDS = [
    (1760, (0, 255, 0),   "configure_misc_apple_regs 返回"),
    (1740, (255, 0, 255), "configure_misc_apple_boot_args 返回"),
    (1720, (255, 255, 0), "wfe_timeout_init 返回"),
    (1700, (0, 255, 255), "wfe_timeout_configure 返回"),
    (1680, (255, 0, 0),   "configure_timer_apple_regs 返回"),
    (1660, (255, 255, 255),"进 Apple 初始化前"),
    (1640, (128, 128, 255),"processor_bootstrap 返回"),
    (1600, (0, 128, 128), "timer_call_init 返回"),
    (1580, (0, 255, 128), "cpu_bootstrap 返回"),
    (1560, (0, 192, 255), "thread_bootstrap 返回"),
    (1540, (255, 192, 0), "CPU 拓扑就绪"),
    (1520, (128, 0, 255), "Apple timer/wfe/misc 全过"),
    (1500, (255, 128, 0), "boot_progress_init 返回"),
    (1480, (128, 255, 0), "arm_vm_init 前"),
    (1460, (0, 128, 255), "PE_init_platform 返回"),
    (1440, (255, 0, 128), "进入 arm_init 函数体"),
    (1420, (255, 0, 0),   "start.s ret 前"),
    (1400, (255, 255, 255),"MMU + 缓存已开"),
    (1380, (0, 0, 255),   "开 MMU 前最后一笔"),
    (1360, (0, 255, 0),   "TTBR0/1 编程完"),
    (1340, (0, 255, 255), "TCR 编程完"),
    (1320, (255, 255, 0), "common_start"),
    (1300, (255, 0, 255), "start_first_cpu 入口"),
]


def sat(rgb):
    mx, mn = max(rgb), min(rgb)
    return 0 if mx == 0 else (mx - mn) / mx


def color_score(a, b):
    """0..1，颜色越像越大；白色带单独按亮度判（sat 太低）。"""
    mx, mn = max(a), min(a)
    sat = 0 if mx == 0 else (mx - mn) / mx
    if b == (255, 255, 255):
        if mx >= 170 and sat <= 0.18:
            return 1.0 - (255 - mx) / 255.0
        return 0.0
    if mx < 60 or sat < 0.30:
        return 0.0
    d = sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    return max(0.0, 1.0 - d / 300.0)


def row_colors(im):
    w, h = im.size
    x0, x1 = int(w * 0.18), int(w * 0.82)
    out = []
    px = im.load()
    for y in range(h):
        vals = [px[x, y] for x in range(x0, x1, max(1, (x1 - x0) // 120))]
        r = int(statistics.median([v[0] for v in vals]))
        g = int(statistics.median([v[1] for v in vals]))
        b = int(statistics.median([v[2] for v in vals]))
        best = max(range(len(BANDS)), key=lambda i: color_score((r, g, b), BANDS[i][1]))
        score = color_score((r, g, b), BANDS[best][1])
        out.append((best, score, (r, g, b)))
    return out


def detect_bands(im):
    rows = row_colors(im)
    h = len(rows)
    runs = []
    start = None
    cur = None
    scores = []
    for y, (idx, sc, rgb) in enumerate(rows):
        ok = sc >= 0.55
        if ok and idx == cur:
            scores.append(sc)
        elif ok:
            if start is not None and y - start >= 3:
                runs.append((start, y - 1, cur, statistics.mean(scores)))
            start, cur, scores = y, idx, [sc]
        else:
            if start is not None and y - start >= 3:
                runs.append((start, y - 1, cur, statistics.mean(scores)))
            start, cur, scores = None, None, []
    if start is not None and h - start >= 3:
        runs.append((start, h - 1, cur, statistics.mean(scores)))
    # 合并被 1-2 行暗线隔开的同色带
    merged = []
    for r in runs:
        if merged and r[2] == merged[-1][2] and r[0] - merged[-1][1] <= 3:
            m = merged[-1]
            merged[-1] = (m[0], r[1], m[2], max(m[3], r[3]))
        else:
            merged.append(r)
    return merged, h


def align(detected, h):
    """把检测到的带按 y 顺序映射到 BANDS（顺序必须单调），返回最上方被命中的索引 k。

    用 DP 允许中间漏检若干条；不假设尾部全部存在，避免菜单 UI 色块把结果拉到 1760。
    """
    m, n = len(detected), len(BANDS)
    if m == 0:
        return n
    sims = [[color_score(BANDS[didx][1], BANDS[i][1]) for i in range(n)]
            for (_y0, _y1, didx, _s) in detected]
    dp = [[-1e9] * n for _ in range(m)]
    prev = [[-1] * n for _ in range(m)]
    for i in range(n):
        dp[0][i] = sims[0][i] - 0.02 * i
    for j in range(1, m):
        for i in range(n):
            best, bi = -1e9, -1
            for ip in range(i):
                v = dp[j - 1][ip] + sims[j][i] - 0.06 * (i - ip - 1)
                if v > best:
                    best, bi = v, ip
            dp[j][i], prev[j][i] = best, bi
    last = max(range(n), key=lambda i: dp[m - 1][i])
    first = last
    for j in range(m - 1, 0, -1):
        first = prev[j][first]
    return first


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("photo")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    im = Image.open(args.photo).convert("RGB")
    detected, h = detect_bands(im)
    k = align(detected, h)
    present = BANDS[k:]
    absent = BANDS[:k]
    highest = present[0][0] if present else None
    next_band = absent[-1][0] if absent else None

    verdict = {
        "photo": str(args.photo),
        "size": list(im.size),
        "detected_bands": [
            {"y": [y0, y1], "raw": BANDS[i][0], "score": round(s, 3)} for y0, y1, i, s in detected
        ],
        "present": [b[0] for b in present],
        "absent": [b[0] for b in absent],
        "highest_present": highest,
        "next_absent": next_band,
        "diagnosis": (
            f"最高存在点 {highest}，下一个 {next_band} 未出现"
            if highest is not None else "未检测到任何色带（请确认拍的是 DarwinBoot 菜单且屏幕有残影）"
        ),
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
