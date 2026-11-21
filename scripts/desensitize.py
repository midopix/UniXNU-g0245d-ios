#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去敏：把本机用户名 / 会话路径 / 设备序列号换成可移植的变量或占位符。

规则全是**模式**，脚本本身不含任何具体的用户名、主机名或序列号，
所以本文件可以安全地放进仓库。幂等，重复跑不会二次改写。

用法：python desensitize.py <目录>
"""
import os
import re
import sys

# (正则, 替换) —— 顺序有意义，先长后短
RULES = [
    # Windows 侧工作区（/mnt/c/Users/<user>/WorkBuddy/<session>/<repo>）
    (re.compile(r"/mnt/[a-z]/Users/[^/\s]+/WorkBuddy/[^/\s]+/UniXNU-g0245d-ios"), "$WORKSPACE"),
    # 构建机主目录：WorkBuddy 会话目录（带时间戳）
    (re.compile(r"/home/[a-z][a-z0-9_-]*/WorkBuddy/\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}/G0245D"),
     "$HOME/WorkBuddy/G0245D"),
    (re.compile(r"/home/[a-z][a-z0-9_-]*/\.workbuddy"), "$HOME/.workbuddy"),
    (re.compile(r"/home/[a-z][a-z0-9_-]*/图片"), "$HOME/Pictures"),
    (re.compile(r"/home/[a-z][a-z0-9_-]*/g0245d-clean"), "$HOME/g0245d-clean"),
    # 输出目录（Windows D 盘）
    (re.compile(r"/mnt/[a-z]/G0245D"), "$G0245D_OUT"),
    # WSL 发行版名（只认 "在 WSL 中执行" 这种固定句式）
    (re.compile(r"在 WSL 中执行"), "在 WSL 中执行"),
    # 设备序列号形态：S0 + 13 位数字
    (re.compile(r"\bS0\d{13}\b"), "$G0245D_SERIAL"),
]

# 文件级补丁：全局替换之后，再把路径上下文修成可运行的写法
FIXUPS = {
    "scripts/linux/auto-v212-pipeline.sh": [
        (
            "set -euo pipefail\n",
            "set -euo pipefail\n"
            "# 路径全部走环境变量/推导，仓库里不留本机绝对路径\n"
            'WORKSPACE=${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}\n',
            "WORKSPACE=${WORKSPACE",
        ),
        ("OUTROOT=$G0245D_OUT/auto\n", "OUTROOT=${G0245D_OUT:-$HOME/g0245d-auto}/auto\n", "${G0245D_OUT:-"),
        ("BASE=$HOME/g0245d-clean\nUX", "BASE=${G0245D_BASE:-$HOME/g0245d-clean}\nUX", "G0245D_BASE"),
    ],
    "linux/auto-flash-daemon.sh": [
        (
            "SERIAL=$G0245D_SERIAL\n",
            'SERIAL=${G0245D_SERIAL:-$(fastboot devices 2>/dev/null | awk \'NR==1{print $1}\')}\n',
            "fastboot devices 2>/dev/null",
        ),
    ],
}

# Python 字面量里的 $HOME 不会展开，改成真正可运行的写法
PY_BASE_OLD = "'$HOME/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/'"

TEXT_EXT = {".sh", ".py", ".ps1", ".md", ".cmd", ".bat", ".toml", ".json", ".txt",
            ".c", ".h", ".patch", ".js", ".ts", ".yml", ".yaml", ""}


def process(path, rel):
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            src = f.read()
    except (UnicodeDecodeError, OSError):
        return False
    out = src
    for pat, rep in RULES:
        out = pat.sub(rep, out)
    for old_s, new_s, marker in FIXUPS.get(rel, []):
        if marker not in out:
            out = out.replace(old_s, new_s, 1)
    if rel.endswith("patch_v224.py") and PY_BASE_OLD in out:
        new = ("os.environ.get('G0245D_BASE', str(Path.home() / 'g0245d-clean'))\n"
               "            + '/UniXNU-runtime/out/g0245d/ios-16.5-20F66/'")
        out = out.replace(PY_BASE_OLD, new, 1)
        if "import os" not in out:
            out = out.replace("from pathlib import Path", "import os\nfrom pathlib import Path", 1)
    if out != src:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        return True
    return False


def main():
    root = sys.argv[1]
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "node_modules")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT and not fn.endswith(".patch"):
                continue
            if process(full, rel):
                n += 1
                print("rewrote", rel)
    print(f"{n} file(s) changed")


if __name__ == "__main__":
    main()
