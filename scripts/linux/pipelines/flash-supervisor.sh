#!/bin/bash
# g0245d flash supervisor: stays running across versions.  Watches the
# newest staged version under $AUTO and flashes it (boot only) the
# moment a healthy fastboot device appears.  Every fastboot call is
# wrapped in timeout so a wedged device can never block this loop.
FB=/home/myth/.workbuddy/binaries/gitlocal/bin/fastboot
SERIAL=S002170002517
AUTO=/home/myth/g0245d-auto/auto
DONE_MARK="$AUTO/.supervisor-flashed"
touch "$DONE_MARK"
echo "$(date +%T) supervisor started"
while true; do
  LATEST=$(ls -1dv "$AUTO"/v*/ 2>/dev/null | tail -1)
  [ -n "$LATEST" ] || { sleep 3; continue; }
  TAG=$(basename "$LATEST")
  D="$AUTO/$TAG"
  grep -qx "$TAG" "$DONE_MARK" 2>/dev/null && { sleep 3; continue; }
  EXPECT=$(awk '$2=="boot.img"{print $1}' "$D/MD5.txt" 2>/dev/null | tr -d '*')
  [ -n "$EXPECT" ] || { sleep 3; continue; }
  SERIAL_NOW=$(timeout 10 "$FB" devices 2>/dev/null \
      | awk 'NF==2 && $2=="fastboot"{print $1; exit}')
  [ "$SERIAL_NOW" = "$SERIAL" ] || { sleep 5; continue; }
  ACTUAL=$(md5sum "$D/boot.img" 2>/dev/null | awk '{print $1}')
  if [ "$ACTUAL" != "$EXPECT" ]; then
    echo "$(date +%T) $TAG md5 mismatch actual=$ACTUAL -- skip"
    echo "$TAG" >> "$DONE_MARK"; sleep 5; continue
  fi
  PRODUCT=$(timeout 20 "$FB" -s "$SERIAL" getvar product 2>&1 | head -n 1)
  case "$PRODUCT" in
    *MSM8996*|*msm8996*) ;;
    *) echo "$(date +%T) $TAG product check failed: $PRODUCT -- retry"
       pkill -f "fastboot -s $SERIAL" 2>/dev/null; sleep 10; continue;;
  esac
  if timeout 60 "$FB" -s "$SERIAL" erase boot \
     && timeout 180 "$FB" -s "$SERIAL" flash boot "$D/boot.img" \
     && timeout 30 "$FB" -s "$SERIAL" reboot; then
    echo "$(date +%T) FLASH_DONE $TAG md5=$EXPECT serial=$SERIAL"
    echo "$TAG" >> "$DONE_MARK"
    sleep 5
    continue
  fi
  echo "$(date +%T) $TAG flash attempt failed -- killing hung fastboot, retry"
  pkill -f "fastboot -s $SERIAL" 2>/dev/null
  sleep 10
done
