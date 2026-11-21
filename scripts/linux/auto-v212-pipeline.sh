#!/usr/bin/env bash
# G0245D v212+ 全自动流水线：构建/打包/照片判读/按判读自动出下一版镜像。
# 在 WSL 中执行：
#   bash scripts/linux/auto-v212-pipeline.sh build [TAG]
#   bash scripts/linux/auto-v212-pipeline.sh photo <照片> [TAG]
#   bash scripts/linux/auto-v212-pipeline.sh watch <目录>
set -euo pipefail

# 路径全部走环境变量/推导，仓库里不留本机绝对路径
WORKSPACE=${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}
BASE=${G0245D_BASE:-$HOME/g0245d-clean}
UX=$BASE/UniXNU-runtime
DEV=$BASE/ios-device
MU=$BASE/Mu-Silicium
ANALYZER=$WORKSPACE/scripts/linux/read_ladder.py
MANIFEST=$WORKSPACE/scripts/linux/band-manifests/v215.json
PATCHDIR=$WORKSPACE/patches/xnu
VENV=$BASE/venv
OUTROOT=${G0245D_OUT:-$HOME/g0245d-auto}/auto
XNUSRC=$UX/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

pack_all() {
  local tag="$1" outdir="$2"
  log "build kernel ($tag)"
  (cd "$UX" && ./unixnu build kernel -D "$DEV" --os ios-16.5-20F66) >"$outdir/kernel.log" 2>&1
  log "skip-prelink + payload"
  (cd "$UX" && ./unixnu prelink --skip-prelink -D "$DEV" --os ios-16.5-20F66 --unique-chip-id 0x47403234 &&
              ./unixnu payload -D "$DEV" --os ios-16.5-20F66 --unique-chip-id 0x47403234) >"$outdir/payload.log" 2>&1
  local K=$UX/out/g0245d/ios-16.5-20F66/g0245d/kernel/kernel.macho
  local P=$UX/out/g0245d/ios-16.5-20F66/g0245d/payload/payload.img
  local FD=$MU/Build/g0245dPkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd-bootshim
  # 本机自编的 FD 里 SPMI DXE 是空桩（源码替换件），点不亮屏。
  # 原构建机的 v195 那份是真的厂商 SPMI，md5 5441ef72de8bd459e5ecb4a182dc9e36。
  # 存在就用它，绝不回退到自编版。
  local GOODFD=$BASE/assets/GOOD-fd-bootshim-v195.bin
  if [[ -f "$GOODFD" ]]; then
    FD=$GOODFD
    log "FD: GOOD v195 ($(md5sum "$FD" | cut -d' ' -f1))"
  else
    log "FD: 自编版（SPMI 为空桩，出不了画面）"
  fi
  local STOCK=$BASE/assets/stock-boot-trimmed.img
  log "pack boot.img"
  python3 "$DEV/tools/pack_fd.py" --base "$STOCK" --fd "$FD" --ramdisk "$P" \
      --out "$outdir/boot.img" >"$outdir/pack.log" 2>&1
  cp "$K" "$outdir/kernel.macho"
  cp "$P" "$outdir/payload.img"
  (cd "$outdir" && sha256sum * > SHA256SUMS.txt && md5sum boot.img > MD5.txt)
  log "DONE $outdir/boot.img $(stat -c %s "$outdir/boot.img") bytes md5=$(cut -d' ' -f1 "$outdir/MD5.txt")"
}

new_outdir() {
  local tag="$1"
  local outdir="$OUTROOT/$tag"
  mkdir -p "$outdir"
  echo "$outdir"
}

apply_candidate() {
  local patch="$1" name
  name=$(basename "$patch")
  if git -C "$XNUSRC" apply --reverse --check "$patch" >/dev/null 2>&1; then
    log "$name already applied"
    return
  fi
  # 反掉另一套候选，保证一次只有一个 bisect 修复
  local other
  for other in "$PATCHDIR"/v213*.patch; do
    [[ "$other" == "$patch" ]] && continue
    if git -C "$XNUSRC" apply --reverse --check "$other" >/dev/null 2>&1; then
      git -C "$XNUSRC" apply --reverse "$other"
      log "reverted $(basename "$other")"
    fi
  done
  git -C "$XNUSRC" apply --check "$patch"
  git -C "$XNUSRC" apply "$patch"
  echo "$name" > "$BASE/applied-v213.txt"
  log "applied $name"
}

photo_flow() {
  local photo="$1" tag="${2:-$(date +%m%d-%H%M)}"
  local outdir; outdir=$(new_outdir "$tag")
  cp "$photo" "$outdir/photo.jpg"
  log "analyze $photo"
  # 判读器在「证据不足」时会以非零码退出，但 JSON 仍然有效，不能让 set -e 中断
  "$VENV/bin/python" "$ANALYZER" "$photo" --manifest "$MANIFEST" >"$outdir/verdict.stdout" 2>&1 || true
  "$VENV/bin/python" "$ANALYZER" "$photo" --manifest "$MANIFEST" --json >"$outdir/verdict.json" 2>"$outdir/verdict.stderr" || true
  cat "$outdir/verdict.stdout"
  if [[ ! -s "$outdir/verdict.json" ]]; then
    log "没有生成 verdict.json，放弃本轮"; return 0
  fi
  local last next geo decision=manual
  read -r last next geo < <("$VENV/bin/python" -c '
import json, sys
d = json.load(open(sys.argv[1]))
lc = d.get("last_contiguous_checkpoint") or {}
nc = d.get("next_checkpoint") or {}
print(lc.get("row") or 0, nc.get("row") or 0, int(bool(d.get("geometry_valid"))))
' "$outdir/verdict.json")
  log "判读: 最后连续通过=$last  下一个缺失=$next  几何标定=$geo"

  if [[ "$geo" != "1" ]]; then
    log "几何标定失败（照片角度/距离不对），不自动改代码；请正对屏幕重拍"
    return 0
  fi
  if [[ "$last" == "0" ]]; then
    log "一条色带都没读到，不自动改代码；请拍 DarwinBoot 菜单"
    return 0
  fi

  # 只有「已备案的夹逼窗口」才自动选补丁；其余情况一律留给人判断
  case "$last:$next" in
    1680:1780)
      log "窗口: configure_timer_apple_regs 已返回，wfe_timeout_configure 尚未进入"
      log "这一窗口没有预置补丁，等人工决定（v214 应从 wfe_timeout_configure 入口打点）"
      decision=manual ;;
    1520:1540|1540:1560|1560:1580|1580:1600|1600:1620|1620:1640|1640:1700)
      log "窗口: 卡在 wfe_timeout_configure 内部，精确到 $last → $next"
      decision=manual ;;
    *)
      log "窗口 $last → $next 没有预置补丁；保持现状，等人工决定"
      decision=manual ;;
  esac

  if [[ "$decision" == manual ]]; then
    echo "manual $last->$next" > "$outdir/decision.txt"
    log "decision=manual（不改代码、不重编）"
    return 0
  fi

  log "decision=$decision"
  apply_candidate "$PATCHDIR/$decision-g0245d-"*.patch
  echo "$decision" > "$outdir/decision.txt"
  pack_all "$decision-$tag" "$outdir"
}

process_dir_once() {
  local dir="$1"
  local marker="$dir/.auto-processed"
  touch "$marker"
  local f
  while IFS= read -r -d '' f; do
    local base; base=$(basename "$f")
    grep -Fxq "$base" "$marker" && continue
    case "$base" in *.jpg|*.JPG|*.jpeg|*.JPEG|*.png|*.PNG)
      log "new photo: $f"
      if photo_flow "$f" "auto-$(date +%m%d-%H%M%S)"; then
        echo "$base" >> "$marker"
      fi
      ;;
    esac
  done < <(find "$dir" -maxdepth 1 -type f -print0)
}

watch_dir() {
  local dir="$1"
  log "watching $dir (每 10 秒检查新照片; Ctrl-C 停止)"
  while true; do
    process_dir_once "$dir"
    sleep 10
  done
}

case "${1:-}" in
  build)  outdir=$(new_outdir "${2:-v212-rebuild}"); pack_all "${2:-v212-rebuild}" "$outdir" ;;
  photo)  photo_flow "$2" "${3:-}" ;;
  poll)   process_dir_once "$2" ;;
  watch)  watch_dir "$2" ;;
  *) echo "usage: $0 build [TAG] | photo <file> [TAG] | poll <dir> | watch <dir>" >&2; exit 2 ;;
esac
