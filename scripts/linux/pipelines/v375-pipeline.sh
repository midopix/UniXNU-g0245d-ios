#!/bin/bash
# v375: read out the real wait-status at the initproc panic.
# Builds on the current tree (v374 applied), gates the new trace labels,
# packs boot.img.  Only the boot partition is ever flashed (see watchdog).
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V375_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export PATH="/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V375_OUT"; cd "$UX" || exit 1
XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v375.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V375_OUT/kernel.log" 2>&1 || { echo BUILD_FAILED; tail -30 "$V375_OUT/kernel.log"; exit 1; }
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V375_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
for p in 'v375 rv' 'v375 sig' 'v375 xstat' 'v375 pid' 'v375 spawn' 'v375 exitdiag' 'v374 c7' 'v373 str' 'v373 has' 'v373 get' 'v372 dirtyflush' 'v371 lr' 'v370 a' 'v363 post'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V375_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V375_OUT/boot.img" >"$V375_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V375_OUT/kernel.macho"; cp "$P" "$V375_OUT/payload.img"; (cd "$V375_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v375 boot.img md5=$(md5sum "$V375_OUT/boot.img" | cut -d' ' -f1)"
