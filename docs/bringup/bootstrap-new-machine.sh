#!/usr/bin/env bash
# Bootstrap a fresh Ubuntu machine to continue G0245D XNU bring-up builds.
# Sets up: runtime tree (+overlay patches), device repo, soc repo, os-profile
# symlink, pack assets, minimal UEFI dir for the panic-screen probe tool.
# Usage: BASE=/path/to/workdir ./bootstrap-new-machine.sh
set -e
BASE=${BASE:-$HOME}
REPO=https://github.com/midopix
UPSTREAM=https://github.com/UniXNU/UniXNU.git

echo "== 0. system packages =="
for t in git python3 clang lld llvm ar strip; do
  command -v $t >/dev/null 2>&1 || MISSING="$MISSING $t"
done
if [ -n "$MISSING" ]; then
  echo "installing missing:$MISSING"
  sudo apt-get update && sudo apt-get install -y git python3 clang lld llvm
fi

echo "== 1. clone trees under $BASE =="
[ -d "$BASE/UniXNU-runtime/.git" ] || git clone "$UPSTREAM" "$BASE/UniXNU-runtime"
[ -d "$BASE/UniXNU-g0245d-ios/.git" ] || git clone "$REPO/UniXNU-g0245d-ios.git" "$BASE/UniXNU-g0245d-ios"
[ -d "$BASE/UniXNU-msm8996-common/.git" ] || git clone "$REPO/UniXNU-msm8996-common.git" "$BASE/UniXNU-msm8996-common"

echo "== 2. apply runtime overlay patches =="
cd "$BASE/UniXNU-runtime"
for p in "$BASE/UniXNU-g0245d-ios/docs/bringup/runtime-overlays/"*.patch; do
  git apply --check "$p" 2>/dev/null && git apply "$p" && echo "applied $(basename "$p")" || echo "skip $(basename "$p") (already applied)"
done

echo "== 3. os profile symlink into runtime =="
ln -sfn "$BASE/UniXNU-g0245d-ios/profiles/os/ios-16.5-20F66" "$BASE/UniXNU-runtime/profiles/os/ios-16.5-20F66"

echo "== 4. pack assets =="
ln -sfn "$BASE/UniXNU-g0245d-ios/assets" "$BASE/assets"

echo "== 5. minimal UEFI dir for panic-screen Font.h =="
FDIR="$BASE/uefi-min/Silicon/Silicium/SiliciumPkg/Library/FrameBufferSerialPortLib"
mkdir -p "$FDIR"
ln -sfn "$BASE/UniXNU-g0245d-ios/kits/g0245d/Font.h" "$FDIR/Font.h"

echo "== 6. build scripts =="
SDIR="$BASE/g0245d-scripts"
mkdir -p "$SDIR"
cp "$BASE/UniXNU-g0245d-ios/docs/bringup/build-scripts/"*.sh "$SDIR/" 2>/dev/null || true
cp "$BASE/UniXNU-g0245d-ios/docs/bringup/build-scripts/edit_board.py" "$SDIR/" 2>/dev/null || true
for f in "$SDIR"/*.sh "$SDIR"/*.py; do
  [ -f "$f" ] && sed -i "s#/home/myth#$BASE#g; s#/mnt/c/Users/Admin/WorkBuddy/2026-11-28-18-27-04#$SDIR#g" "$f"
done

echo "== done =="
cat <<EOF
Next steps:
  export UNIXNU_UEFI=$BASE/uefi-min
  cd $BASE/UniXNU-runtime
  bash $SDIR/run-v456bp.sh   # boot-progress kernel (first build is long)
  bash $SDIR/run-v457prb.sh  # panic-screen probe image
  bash $SDIR/run-v458prb.sh  # stage-4 reset-probe image
Images land in \$BASE/g0245d-auto/auto/<ver>/. Board.toml probe toggles:
  python3 $SDIR/edit_board.py panic|reset4   (board.toml is restored after builds)
EOF
