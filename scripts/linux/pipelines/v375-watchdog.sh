#!/bin/bash
# v375 flash watchdog: wait for the built image, then flash only when the
# device reappears in fastboot.  A hung kernel does not enumerate on USB, so
# the user only has to reboot the phone into fastboot; everything else is auto.
set -o pipefail
OUT=${V375_OUT:?V375_OUT required}
FB=/home/myth/.workbuddy/binaries/gitlocal/bin/fastboot
mkdir -p "$OUT"
LOG="$OUT/watchdog.log"
exec >>"$LOG" 2>&1
echo "=== watchdog started $(date '+%F %T') ==="

IMG="$OUT/boot.img"
while [ ! -f "$OUT/MD5.txt" ] || [ ! -f "$IMG" ]; do sleep 3; done
# MD5.txt is created (truncated) before md5sum fills it; wait for a non-empty
# boot.img digest instead of racing the writer.
EXPECT=""
while [ -z "$EXPECT" ]; do
  EXPECT=$(awk '$2=="boot.img"{print $1}' "$OUT/MD5.txt" 2>/dev/null | tr -d '*')
  [ -n "$EXPECT" ] || sleep 2
done
echo "image ready, expected md5=$EXPECT"

while true; do
  SERIAL=$($FB devices 2>/dev/null | awk 'NF==2 && $2=="fastboot"{print $1; exit}')
  if [ -n "$SERIAL" ]; then
    ACTUAL=$(md5sum "$IMG" | cut -d' ' -f1)
    if [ "$ACTUAL" != "$EXPECT" ]; then
      echo "md5 mismatch actual=$ACTUAL expected=$EXPECT -- refuse to flash"; sleep 10; continue
    fi
    PRODUCT=$($FB -s "$SERIAL" getvar product 2>&1 | sed -n 's/^product: *//p' | tr -d '\r')
    echo "device=$SERIAL product=$PRODUCT md5=$ACTUAL"
    if [ "$PRODUCT" != "MSM8996" ]; then
      echo "unexpected product -- refuse to flash"; sleep 10; continue
    fi
    $FB -s "$SERIAL" erase boot && \
    $FB -s "$SERIAL" flash boot "$IMG" && \
    $FB -s "$SERIAL" reboot && \
    { echo "FLASH_DONE v375 $(date '+%F %T') md5=$ACTUAL"; exit 0; }
    echo "flash attempt failed, retry in 10s"
  fi
  sleep 3
done
