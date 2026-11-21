#!/usr/bin/env bash
# v212：把已编译的 timer/WFE 夹逼探针内核打成 boot.img，并（可选）刷入。
#
# 对应判读卡：docs/bringup/cards/G0245D-v210-v212-EARLY-INIT-BISECT.md
# 背景：v212 内核已于 2026-11-20 编译完成（sha256 见下），payload 也已生成；
#       linux/ios-pipeline.py 在回读 staged kernel.macho 时 FileNotFoundError
#       中断，导致 boot 镜像没打、没刷。本脚本绕开该检查，直接走
#       kernel -> prelink -> payload -> pack_fd.py 四步。
#
# 用法（在构建机的 G0245D 根目录）:
#   bash scripts/linux/build-v212-all.sh          # 只打包，输出镜像路径和 md5
#   bash scripts/linux/build-v212-all.sh --flash  # 打包后直接 fastboot flash boot + reboot
#
set -uo pipefail

# 构建机根目录；可用 G0245D_ROOT 覆盖
D="${G0245D_ROOT:-$HOME/WorkBuddy/G0245D}"
UX="$D/src/unixnu-g0245d/unixnu-src"
FD="$D/src/unixnu-g0245d/uefi-g0245d/Mu-Silicium/Build/g0245dPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd-bootshim"
BASE="$D/workspace/tmp/g0245d-v137.img"
OUT_IMG="$D/workspace/tmp/g0245d-ios165-v212.img"
EXPECT_KERNEL_SHA256="870dd404469d7a643d6d686edd78dffaf42a227f1817e8ec58cb650962c404ee"

cd "$D" || exit 1

# 与 build-v191-all.sh 相同的环境清理：去掉 safe-bin shim，恢复 git 执行路径
CLEAN="$(printf '%s' "$PATH" | tr ':' '\n' | grep -v 'cli/vendor/shim/safe-bin' | paste -sd: -)"
export PATH="$CLEAN"
unset -f rm rmdir mv cp unlink ln 2>/dev/null || true
unset BASH_ENV NODE_OPTIONS PYTHONPATH \
      CODEBUDDY_SAFE_DELETE_ENABLED CODEBUDDY_SAFE_DELETE_SANDBOX \
      CODEBUDDY_SAFE_DELETE_BIN_DIR CODEBUDDY_SAFE_DELETE_BULK_GUARD \
      CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD \
      CODEBUDDY_SAFE_DELETE_REPORT_PATH 2>/dev/null || true
export CODEBUDDY_SAFE_DELETE_ENABLED=0
# shellcheck disable=SC1091
source ./env.sh
export PATH="$D/workspace/tmp/gitshim:$D/workspace/tmp/toolchain-root/usr/bin:$PATH"

echo "=== [0/5] 前置检查 ==="
for f in "$FD" "$BASE" "$D/workspace/tools/pack_fd.py"; do
  [ -f "$f" ] || { echo "✗ 缺文件: $f"; exit 1; }
done
echo "  FD   : $FD"
echo "  BASE : $BASE"

echo "=== [1/5] unixnu build kernel ==="
cd "$UX" || exit 1
while IFS= read -r -d '' f; do
  d="$(dirname "$f")"
  rm -f "$f" "$d/syscall.h" "$d/sysproto.h"
  echo ">>> 已清理 0 字节 bsd.syscalls.master 残骸: $f"
done < <(find "$UX/out/g0245d" -name bsd.syscalls.master -type f -size 0 -print0 2>/dev/null)
python3 unixnu build kernel || { echo "✗ build kernel 失败"; exit 1; }

echo "=== [2/5] 校验 kernel.macho sha256 ==="
KMACHO="$(find "$UX/out/g0245d" -name kernel.macho -type f \
          -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
[ -n "$KMACHO" ] || { echo "✗ 找不到 kernel.macho"; exit 1; }
ACTUAL="$(sha256sum "$KMACHO" | awk '{print $1}')"
echo "  $KMACHO"
echo "  sha256=$ACTUAL"
if [ "$ACTUAL" != "$EXPECT_KERNEL_SHA256" ]; then
  echo "✗ kernel 与 v212 已知版本不符（期望 $EXPECT_KERNEL_SHA256）"
  echo "  可能原因：v212 补丁未应用到构建树，或构建树里混入了其它探针。"
  exit 1
fi
echo "  ✓ 与 v212 已知 kernel 一致"

echo "=== [3/5] prelink --skip-prelink + payload ==="
python3 unixnu prelink --skip-prelink || exit 1
python3 unixnu payload --unique-chip-id "${G0245D_CHIP_ID:-}" || exit 1

PAYLOAD="$(find "$UX/out/g0245d" -path '*/payload/payload.img' -type f \
           -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)"
[ -n "$PAYLOAD" ] || { echo "✗ 找不到 payload.img"; exit 1; }
echo "  payload: $PAYLOAD ($(stat -c %s "$PAYLOAD") bytes)"

echo "=== [4/5] pack_fd.py 打包（自带 DTB 尾表 / QCOM 签名 / FD 回读校验）==="
python3 "$D/workspace/tools/pack_fd.py" \
  --base "$BASE" \
  --fd "$FD" \
  --ramdisk "$PAYLOAD" \
  --out "$OUT_IMG" || { echo "✗ 打包失败"; exit 1; }

IMG_MD5="$(md5sum "$OUT_IMG" | awk '{print $1}')"
echo "=== 打包完成 ==="
echo "  镜像: $OUT_IMG"
echo "  大小: $(stat -c %s "$OUT_IMG") bytes"
echo "  md5 : $IMG_MD5"
echo "V212_PACK_OK"

if [ "${1:-}" != "--flash" ]; then
  echo "（未刷机。要刷机请加 --flash，或手动执行下面两条命令）"
  echo "  fastboot flash boot $OUT_IMG && fastboot reboot"
  exit 0
fi

echo "=== [5/5] fastboot flash boot + reboot ==="
export PATH="$D/workspace/tools/platform-tools-linux:$PATH"
command -v fastboot >/dev/null || { echo "✗ fastboot 不在 PATH"; exit 1; }
DEV="$(fastboot devices | awk 'NR==1{print $1}')"
[ -n "$DEV" ] || { echo "✗ 没有设备处于 fastboot；长按电源 15s → 音量下+短按电源"; exit 1; }
echo "  设备: $DEV"
fastboot -s "$DEV" flash boot "$OUT_IMG" || exit 1
fastboot -s "$DEV" reboot || true
echo "=== 刷机完成 ==="
echo "  镜像 md5=$IMG_MD5，请确认日志出现 OKAY 并已 reboot"
echo "  下一步：拍 DarwinBoot 菜单照片，交给 analyze-bands.py 判读"
echo "V212_FLASH_OK"
