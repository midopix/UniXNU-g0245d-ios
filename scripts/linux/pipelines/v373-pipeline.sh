#!/bin/bash
# v373: guard AMFI entitlement dispatch when the AMFI kext is absent.
# Builds on the current tree (v372 applied), gates the new traces, packs boot.img.
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V373_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export PATH="/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
# cpo.json files already exist in this tree; do not invent a CCACHE wrapper.
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V373_OUT"; cd "$UX" || exit 1
XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v373.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V373_OUT/kernel.log" 2>&1 || { echo BUILD_FAILED; tail -30 "$V373_OUT/kernel.log"; exit 1; }
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V373_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
for p in 'v373 str' 'v373 has' 'v373 get' 'v372 dirtyflush' 'v371 lr' 'v370 a' 'v363 post'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V373_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V373_OUT/boot.img" >"$V373_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V373_OUT/kernel.macho"; cp "$P" "$V373_OUT/payload.img"; (cd "$V373_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v373 boot.img md5=$(md5sum "$V373_OUT/boot.img" | cut -d' ' -f1)"
