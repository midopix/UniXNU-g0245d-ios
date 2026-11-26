#!/bin/bash
# v379 flash watchdog: wait for a non-empty MD5, then only flash 'boot'.
# Idempotent; product guard; refuses to flash a mismatched image.
OUT=${V379_OUT:?V379_OUT required}
FB=/home/myth/.workbuddy/binaries/gitlocal/bin/fastboot
[ -x "$FB" ] || FB=fastboot
mkdir -p "$OUT"
IMG="$OUT/boot.img"

# MD5.txt is created (truncated) before md5sum fills it: wait for a NON-EMPTY digest.
EXPECT=""
while [ -z "$EXPECT" ]; do
  EXPECT=$(awk '$2=="boot.img"{print $1}' "$OUT/MD5.txt" 2>/dev/null | tr -d '*')
  [ -n "$EXPECT" ] || sleep 2
done
echo "image ready, expected md5=$EXPECT"

while true; do
  SERIAL=$($FB devices 2>/dev/null | awk 'NF==2 && $2=="fastboot"{print $1; exit}')
  if [ -n "$SERIAL" ]; then
    ACTUAL=$($FB -s "$SERIAL" getvar md5 boot.img 2>&1 | head -n 1 || true)
    # device cannot report our host-side md5; compare the local file only
    ACTUAL=$(md5sum "$IMG" 2>/dev/null | awk '{print $1}')
    if [ "$ACTUAL" != "$EXPECT" ]; then
      echo "md5 mismatch actual=$ACTUAL expected=$EXPECT -- refuse to flash"; sleep 10; continue
    fi
    PRODUCT=$($FB -s "$SERIAL" getvar product 2>&1 | head -n 1)
    case "$PRODUCT" in *MSM8996*) ;; *) echo "unexpected product -- refuse to flash"; sleep 10; continue;; esac
    $FB -s "$SERIAL" erase boot && \
    $FB -s "$SERIAL" flash boot "$IMG" && \
    $FB -s "$SERIAL" reboot && \
    echo "FLASH_DONE v379 md5=$EXPECT serial=$SERIAL" && exit 0
    echo "flash attempt failed, retry in 10s"
  fi
  sleep 5
done
