#!/bin/bash
# Wait for the device to reappear (fastboot or adb), then flash v353.
export PATH=$PATH:/home/myth/.workbuddy/binaries/gitlocal/bin
SER=S002170002517
OUT=/home/myth/g0245d-auto/auto/v353
FB=/home/myth/.workbuddy/binaries/gitlocal/bin/fastboot
ADB=/home/myth/.workbuddy/binaries/gitlocal/bin/adb
LOG=/home/myth/g0245d-auto/auto-grab.log
: > $LOG
for i in $(seq 1 240); do
  if $FB devices 2>/dev/null | grep -q "$SER"; then
    echo "[$(date +%T)] fastboot seen -> flash v353" >> $LOG
    $FB -s $SER erase boot >>$LOG 2>&1
    $FB -s $SER flash boot $OUT/boot.img >>$LOG 2>&1
    $FB -s $SER reboot >>$LOG 2>&1
    echo "[$(date +%T)] done" >> $LOG
    exit 0
  fi
  if $ADB devices 2>/dev/null | grep -q "$SER"; then
    echo "[$(date +%T)] adb seen -> reboot bootloader" >> $LOG
    $ADB -s $SER reboot bootloader >>$LOG 2>&1
    sleep 10
  fi
  sleep 5
done
echo "[$(date +%T)] timeout" >> $LOG
