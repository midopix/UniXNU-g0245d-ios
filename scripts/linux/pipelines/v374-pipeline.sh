#!/bin/bash
# v374: bisect the s1b -> s9a window inside pmap_switch_internal().
# Builds on the current tree (v373 applied), gates the new status labels,
# packs boot.img.  Only the boot partition is ever flashed (see watchdog).
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V374_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export PATH="/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V374_OUT"; cd "$UX" || exit 1
XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v374.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V374_OUT/kernel.log" 2>&1 || { echo BUILD_FAILED; tail -30 "$V374_OUT/kernel.log"; exit 1; }
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V374_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
for p in 'v374 c0' 'v374 c1' 'v374 c2' 'v374 c3' 'v374 c4' 'v374 c5' 'v374 c6' 'v374 c7' 'v373 str' 'v373 has' 'v373 get' 'v372 dirtyflush' 'v371 lr' 'v370 a' 'v363 post'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V374_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V374_OUT/boot.img" >"$V374_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V374_OUT/kernel.macho"; cp "$P" "$V374_OUT/payload.img"; (cd "$V374_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v374 boot.img md5=$(md5sum "$V374_OUT/boot.img" | cut -d' ' -f1)"
