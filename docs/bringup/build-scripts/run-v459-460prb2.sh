#!/bin/bash
# 修复重建 v459prb / v460prb：
# shim 目录同时提供 clang(→系统) 与 strip(→cctools)，置于 PATH 最前。
set -e
SHIM=/tmp/g0245d-strip-bin
TC=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain/CommandLineTools/usr/bin
rm -rf "$SHIM"; mkdir -p "$SHIM"
ln -sf "$TC/strip" "$SHIM/strip"
ln -sf /usr/bin/clang "$SHIM/clang"
export PATH="$SHIM:/usr/bin:/bin"
echo "=== resolution check ==="
which clang strip
# 用真 Mach-O 试 strip，必须成功
K0=/home/myth/g0245d-auto/auto/v456bp/kernel.macho
cp "$K0" /tmp/strip-test.macho
strip /tmp/strip-test.macho && echo "STRIP_TEST_OK size=$(stat -c%s /tmp/strip-test.macho)"

export UNIXNU_TOOLCHAIN=/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain
V365_DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
V365_SOC=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-msm8996-common
O=/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d
cd /home/myth/UniXNU-runtime
export UNIXNU_UEFI=/home/myth/g0245d-clean/Mu-Silicium

build_one() {
  local MODE=$1 VER=$2
  echo "=== edit_board.py $MODE ==="
  python3 /mnt/c/Users/Admin/WorkBuddy/2026-11-28-18-27-04/edit_board.py "$MODE"
  local OUT=/home/myth/g0245d-auto/auto/$VER
  rm -rf "$OUT"; mkdir -p "$OUT"
  echo "=== payload $VER ==="
  ./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$OUT/payload.log" 2>&1
  RC=$?
  echo "payload rc=$RC"
  grep -E "strip" "$OUT/payload.log"
  # 硬校验 1：payload.log 必须出现 "staged kernel stripped to"
  grep -q "staged kernel stripped to" "$OUT/payload.log" || { echo GATE_FAIL_NOT_STRIPPED; exit 1; }
  # 硬校验 2：FAT 里的 kernel.macho 实际尺寸 <17MB
  rm -f /tmp/kchk.macho
  mcopy -n -i "$O/payload/payload.img" ::/EFI/UniXNU/Payloads/kernel.macho /tmp/kchk.macho
  KSZ=$(stat -c%s /tmp/kchk.macho)
  echo "staged kernel in FAT = $KSZ"
  [ "$KSZ" -lt 17000000 ] || { echo GATE_FAIL_KERNEL_TOO_BIG; exit 1; }
  # 硬校验 3：探针注入
  cp "$O/logs/payload-patch.log" "$OUT/payload-patch.log"
  cat "$OUT/payload-patch.log"
  # 硬校验 4：unixnu.toml 完整可读
  rm -f /tmp/chk.toml
  mcopy -n -i "$O/payload/payload.img" ::/EFI/UniXNU/unixnu.toml /tmp/chk.toml
  grep -c "entry" /tmp/chk.toml
  echo "=== pack $VER ==="
  python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_DEV/assets/stock-boot-trimmed.img" --fd "$V365_DEV/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$O/payload/payload.img" --out "$OUT/boot.img" >"$OUT/pack.log" 2>&1
  (cd "$OUT" && md5sum boot.img > MD5.txt && cat MD5.txt)
  mkdir -p "/mnt/d/G0245D/auto/$VER"
  cp "$OUT"/* "/mnt/d/G0245D/auto/$VER/"
  echo "DONE $VER"
}

build_one panic v459prb
build_one reset4 v460prb
echo "=== restore clean board.toml ==="
cp /home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios/board.toml.v456bp-bak /home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios/board.toml
grep -c "panic_screen\|entry_probe" /home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios/board.toml || echo "  clean"
echo "ALL_DONE"
