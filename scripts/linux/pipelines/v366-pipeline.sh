#!/bin/bash
# g0245d v366 -- move status probes out of protected pmap code.
set -o pipefail
: "${V365_BASE:?V365_BASE is required}"
: "${V365_DEV:?V365_DEV is required}"
: "${V365_SOC:?V365_SOC is required}"
: "${V366_OUT:?V366_OUT is required}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-$V365_BASE/.tools/share/bison}"
export M4="${M4:-$V365_BASE/.tools/bin/m4}"
UX=$V365_BASE/UniXNU-runtime
O=$UX/out/g0245d/ios-16.5-20F66/g0245d
W=$O/tree/.cache/xnu-work
mkdir -p "$V366_OUT"
cd "$UX" || exit 1
for v in 366; do XNU_WORK=$W python3 "$V365_DEV/scripts/linux/patch_v$v.py" || exit 1; done
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V366_OUT/kernel.log" 2>&1 || exit 1
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V366_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho
SZ=$(stat -c %s "$K"); [ "$SZ" -le 25000000 ] || { echo "STILL UNSTRIPPED"; exit 1; }
for p in 'v366 pre switch' 'v366 post switch' 'v354 ttep low' 'v352 switch done'; do N=$(strings "$K" | grep -cF "$p" || true); printf '%s %s\n' "$p" "$N"; [ "$N" -gt 0 ] || exit 1; done
if ! grep -q 'bool do_shared_region_flush = false;' "$W/osfmk/arm/pmap/pmap.c"; then echo "v365 noSR source check failed"; exit 1; fi
printf '%s %s\n' 'v365 noSR source' 'present'
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V366_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V366_OUT/boot.img" >"$V366_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V366_OUT/kernel.macho"; cp "$P" "$V366_OUT/payload.img"
(cd "$V366_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v366 boot.img md5=$(md5sum "$V366_OUT/boot.img" | cut -d' ' -f1)"
