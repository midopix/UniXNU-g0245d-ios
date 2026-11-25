#!/bin/bash
# g0245d v367 -- DABORT register capture and vm_map_switch return marker.
set -o pipefail
: "${V365_BASE:?V365_BASE is required}"
: "${V365_DEV:?V365_DEV is required}"
: "${V365_SOC:?V365_SOC is required}"
: "${V367_OUT:?V367_OUT is required}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V365_BASE/.tools/share/bison}"
export M4="${M4:-$V365_BASE/.tools/bin/m4}"
UX=$V365_BASE/UniXNU-runtime
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
W=$O/tree/.cache/xnu-work
mkdir -p "$V367_OUT"
cd "$UX" || exit 1
XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v367.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V367_OUT/kernel.log" 2>&1 || exit 1
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V367_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K"); [ "$SZ" -le 25000000 ] || { echo "STILL UNSTRIPPED"; exit 1; }
for p in 'v367 esr' 'v367 far' 'v367 pc' 'v367 x0' 'v367 x1' 'v367 vmsw returned' 'v366 pre switch' 'v366 post switch' 'v354 ttep low'; do N=$(strings "$K" | grep -cF "$p" || true); printf '%s %s\n' "$p" "$N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V367_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V367_OUT/boot.img" >"$V367_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V367_OUT/kernel.macho"; cp "$P" "$V367_OUT/payload.img"
(cd "$V367_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v367 boot.img md5=$(md5sum "$V367_OUT/boot.img" | cut -d' ' -f1)"
