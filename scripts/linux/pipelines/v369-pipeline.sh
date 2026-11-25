#!/bin/bash
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V369_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V365_BASE/.tools/share/bison}"; export M4="${M4:-$V365_BASE/.tools/bin/m4}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V369_OUT"; cd "$UX" || exit 1
XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v369.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V369_OUT/kernel.log" 2>&1 || exit 1
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V369_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
for p in 'v369 sp1 esr' 'v369 sp1 far' 'v369 sp1 pc' 'v368 esr' 'v367 vmsw returned' 'v366 post switch' 'v354 ttep low'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V369_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V369_OUT/boot.img" >"$V369_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V369_OUT/kernel.macho"; cp "$P" "$V369_OUT/payload.img"; (cd "$V369_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v369 boot.img md5=$(md5sum "$V369_OUT/boot.img" | cut -d' ' -f1)"
