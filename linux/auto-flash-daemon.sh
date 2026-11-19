#!/bin/bash
# 自动刷机守护：设备一进 fastboot 就自动刷入"最新"镜像（按 md5 去重，一个镜像只刷一次）。
#
# 用法:
#   bash linux/auto-flash-daemon.sh start   # 后台启动守护（默认自动选最新镜像）
#   bash linux/auto-flash-daemon.sh stop    # 停止守护
#   bash linux/auto-flash-daemon.sh status  # 查看状态
#   bash linux/auto-flash-daemon.sh rearm   # 清除全部"已刷"标记，允许重刷当前镜像
#   bash linux/auto-flash-daemon.sh once    # 前台跑一次检测（调试）
#   bash linux/auto-flash-daemon.sh start --img <path>   # 固定刷某个镜像
#
# 自动选镜像规则：在 $IMG_DIR 下找 g0245d-ios165-v*.img，取 mtime 最新的那个。
# 去重规则：以镜像 md5 命名 done 标记；同 md5 只刷一次，换了新 md5（新镜像）自动再刷。
# 铁律：只刷 boot 分区，其余分区一律不动；刷前必校验 md5。
set -uo pipefail

D=$HOME/WorkBuddy/G0245D
export PATH="$D/workspace/tools/platform-tools-linux:$HOME/.workbuddy/binaries/gitlocal/bin:$PATH"

SERIAL=S002170002517
IMG_DIR="$D/workspace/tmp"
IMG_GLOB="g0245d-ios165-v*.img"
# 可由 --img 覆盖（固定镜像模式）
FIXED_IMG=""

RUN_DIR="$D/workspace/tmp/autoflash"
LOG="$RUN_DIR/daemon.log"
PIDFILE="$RUN_DIR/daemon.pid"
POLL_SEC=3

mkdir -p "$RUN_DIR"
# 终端里跑（stdout 是 tty）时 tee 到日志；_loop 后台跑时 stdout 已重定向到 LOG，直接 echo 即可，避免重复写
log() {
  local line="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
  if [ -t 1 ]; then echo "$line" | tee -a "$LOG"; else echo "$line"; fi
}
is_running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

# 选当前要刷的镜像（全局变量 TARGET_IMG / TARGET_MD5）
pick_image() {
  local img=""
  if [ -n "$FIXED_IMG" ]; then
    img="$FIXED_IMG"
  else
    # shellcheck disable=SC2086
    img=$(ls -t "$IMG_DIR"/$IMG_GLOB 2>/dev/null | head -1)
  fi
  if [ -z "$img" ] || [ ! -f "$img" ]; then
    TARGET_IMG=""; TARGET_MD5=""; return 1
  fi
  TARGET_IMG="$img"
  TARGET_MD5=$(md5sum "$img" | awk '{print $1}')
  return 0
}

done_mark() { echo "$RUN_DIR/flashed-$(basename "$1" .img)-$2.done"; }

do_flash() {
  local img="$1" expect="$2" mark actual
  [ -f "$img" ] || { log "✗ 镜像不存在: $img"; return 1; }
  actual=$(md5sum "$img" | awk '{print $1}')
  if [ "$actual" != "$expect" ]; then
    log "✗ md5 变了或被篡改: $actual ≠ $expect（重选）"; return 2
  fi
  mark=$(done_mark "$img" "$actual")
  log "✓ 校验通过 $actual ($(stat -c %s "$img") bytes) → flash boot ($(basename "$img"))"
  if fastboot -s "$SERIAL" flash boot "$img" >>"$LOG" 2>&1; then
    log "✓ flash boot OKAY"
    fastboot -s "$SERIAL" reboot >>"$LOG" 2>&1 || true
    log "✓ reboot 已发送"
    echo "flashed at $(date '+%F %T') img=$(basename "$img") md5=$actual" > "$mark"
    log "✓ 已刷并写标记: $(basename "$mark")"
    return 0
  else
    log "✗ flash boot 失败，详见 $LOG"; return 3
  fi
}

# 单次检测（_loop 和 once 共用）
watch_once() {
  local dev_fs
  dev_fs=$(awk '$5=="/dev"{fs="";for(i=1;i<=NF;i++)if($i=="-"){fs=$(i+1);break} v=fs} END{print v}' /proc/self/mountinfo)
  if [ "$dev_fs" != "devtmpfs" ] || [ ! -d /dev/bus/usb ]; then
    log "✗ 沙箱环境（/dev=$dev_fs），fastboot 看不到手机"; return 4
  fi
  if ! pick_image; then
    log "· 未找到镜像（$IMG_DIR/$IMG_GLOB）"; return 5
  fi
  local mark; mark=$(done_mark "$TARGET_IMG" "$TARGET_MD5")
  if [ -f "$mark" ]; then
    # 当前最新镜像已刷过 → 静默等待新镜像
    return 0
  fi
  if fastboot devices 2>/dev/null | grep -qw "$SERIAL"; then
    log "★ 设备 $SERIAL 在 fastboot，自动刷最新镜像 $(basename "$TARGET_IMG")"
    do_flash "$TARGET_IMG" "$TARGET_MD5"
  fi
}

# 解析 --img
shift_once=0
if [ "${1:-}" = "start" ] || [ "${1:-}" = "once" ]; then
  if [ "${2:-}" = "--img" ] && [ -n "${3:-}" ]; then FIXED_IMG="$3"; fi
fi

case "${1:-}" in
  start)
    if is_running; then echo "守护已在运行 (PID $(cat "$PIDFILE"))"; exit 0; fi
    dev_fs=$(awk '$5=="/dev"{fs="";for(i=1;i<=NF;i++)if($i=="-"){fs=$(i+1);break} v=fs} END{print v}' /proc/self/mountinfo)
    if [ "$dev_fs" != "devtmpfs" ] || [ ! -d /dev/bus/usb ]; then
      echo "✗ 沙箱环境，无法启动守护（/dev=$dev_fs）"; exit 4
    fi
    nohup bash "$0" _loop ${FIXED_IMG:+--img "$FIXED_IMG"} >>"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    log "守护启动 PID=$! 模式=$([ -n "$FIXED_IMG" ] && echo "固定:$FIXED_IMG" || echo "自动最新:$IMG_DIR/$IMG_GLOB") 轮询=${POLL_SEC}s"
    echo "守护已启动 PID=$(cat "$PIDFILE")，日志: $LOG"
    ;;
  _loop)
    if [ "${2:-}" = "--img" ] && [ -n "${3:-}" ]; then FIXED_IMG="$3"; fi
    log "守护循环开始（自动最新镜像模式）"
    last_note=""
    while true; do
      pick_image && {
        note="待刷=$(basename "$TARGET_IMG") md5=$TARGET_MD5"
        if [ "$note" != "$last_note" ]; then log "· 当前目标: $note"; last_note="$note"; fi
      }
      watch_once || true
      sleep "$POLL_SEC"
    done
    ;;
  stop)
    if is_running; then kill "$(cat "$PIDFILE")" 2>/dev/null && log "守护已停止"; rm -f "$PIDFILE"; else echo "守护未运行"; fi
    ;;
  status)
    if is_running; then echo "● 守护运行中 PID=$(cat "$PIDFILE")"; else echo "○ 守护未运行"; fi
    if pick_image; then
      mark=$(done_mark "$TARGET_IMG" "$TARGET_MD5")
      echo "目标镜像: $(basename "$TARGET_IMG")  md5=$TARGET_MD5"
      [ -f "$mark" ] && echo "✓ 该镜像已刷过: $(cat "$mark")" || echo "· 该镜像尚未刷（插上即刷）"
    else
      echo "未找到镜像"
    fi
    echo "fastboot 当前设备: $(fastboot devices 2>/dev/null | awk '{print $1}' | tr '\n' ' ')"
    echo "--- 最近日志 ---"; tail -12 "$LOG" 2>/dev/null
    ;;
  rearm)
    rm -f "$RUN_DIR"/flashed-*.done && log "已清除全部完成标记，插上将重刷当前最新镜像" && echo "rearm 完成"
    ;;
  once)
    watch_once; echo "once 退出码=$?"
    ;;
  *)
    echo "用法: $0 {start|stop|status|rearm|once} [--img <path>]"; exit 1
    ;;
esac
