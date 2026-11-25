#!/bin/bash
# v376: put the REAL iOS 16.5 /sbin/launchd into the mockfs N4KROOT container.
# ONE嫌疑点: real Mach-O as PID1 (dyld/dylibs come in v377, expected to fail).
# Builds on v375 tree.  Only the boot partition is ever flashed (see watchdog).
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V376_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export PATH="/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V376_OUT"; cd "$UX" || exit 1

# real launchd asset must exist; pipeline refuses to build a fake v376
LAUNCHD="${G0245D_LAUNCHD:-/home/myth/g0245d-assets/ios-16.5-20F66/20F66__iPhone10,3/sbin/launchd}"
[ -f "$LAUNCHD" ] || { echo "NO_REAL_LAUNCHD: $LAUNCHD"; exit 1; }
LSHA=$(sha256sum "$LAUNCHD" | awk '{print $1}')
[ "$LSHA" = "4c61512d19b9a55a6ddad27e23b88fc5008fbf77d0c0b5e6bdd7c7d90cef3e06" ] || { echo "LAUNCHD_SHA_MISMATCH $LSHA"; exit 1; }
echo "real launchd sha256=$LSHA"

XNU_WORK=$W G0245D_LAUNCHD="$LAUNCHD" python3 "$V365_DEV/scripts/linux/patch_v376.py" || exit 1
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V376_OUT/kernel.log" 2>&1 || { echo BUILD_FAILED; tail -40 "$V376_OUT/kernel.log"; exit 1; }
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V376_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
# gate: all previous probes + the new v376 labels + N4KROOT magic
for p in 'v376 real launchd' 'v376 root bytes' 'v376 launch size' 'N4KROOT' 'v375 rv' 'v375 sig' 'v375 xstat' 'v374 c7' 'v373 str' 'v372 dirtyflush' 'v371 lr' 'v363 post'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V376_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V376_OUT/boot.img" >"$V376_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V376_OUT/kernel.macho"; cp "$P" "$V376_OUT/payload.img"; (cd "$V376_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v376 boot.img md5=$(md5sum "$V376_OUT/boot.img" | cut -d' ' -f1)"
