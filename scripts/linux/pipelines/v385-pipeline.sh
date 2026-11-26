#!/bin/bash
# v385: C1a -- UFS register probe (CAP/VER/HCPID/HCMID at 0x624000, PHY at 0x627000).
# Builds on the v384 tree.  Only the boot partition is ever flashed (see watchdog).
set -o pipefail
: "${V365_BASE:?}"; : "${V365_DEV:?}"; : "${V365_SOC:?}"; : "${V385_OUT:?}"
[ -n "$V365_ENV" ] && source "$V365_ENV"
export PATH="/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d; W=$O/tree/.cache/xnu-work
mkdir -p "$V385_OUT"; cd "$UX" || exit 1

LAUNCHD="${G0245D_LAUNCHD:-/home/myth/g0245d-assets/ios-16.5-20F66/20F66__iPhone10,3/sbin/launchd}"
[ -f "$LAUNCHD" ] || { echo "NO_REAL_LAUNCHD: $LAUNCHD"; exit 1; }
LSHA=$(sha256sum "$LAUNCHD" | awk '{print $1}')
[ "$LSHA" = "4c61512d19b9a55a6ddad27e23b88fc5008fbf77d0c0b5e6bdd7c7d90cef3e06" ] || { echo "LAUNCHD_SHA_MISMATCH $LSHA"; exit 1; }
echo "real launchd sha256=$LSHA"

DYLD="${G0245D_DYLD:-/home/myth/g0245d-assets/ios-16.5-20F66/usr-lib/dyld}"
[ -f "$DYLD" ] || { echo "NO_REAL_DYLD: $DYLD"; exit 1; }
DSHA=$(sha256sum "$DYLD" | awk '{print $1}')
[ "$DSHA" = "82c650c5cabfa430aaa69495e260ccc07996f88ad56065d958952c3c4acfd931" ] || { echo "DYLD_SHA_MISMATCH $DSHA"; exit 1; }
echo "real dyld sha256=$DSHA"

XNU_WORK=$W G0245D_LAUNCHD="$LAUNCHD" python3 "$V365_DEV/scripts/linux/patch_v384.py" || exit 1
XNU_WORK=$W G0245D_LAUNCHD="$LAUNCHD" python3 "$V365_DEV/scripts/linux/patch_v385.py" || exit 1
# mockfs is NOT compiled by the kernel build: the kernel links
# build/mockfs-fixture/libmockfs_fixture.a, which scripts/build-mockfs-fixture.py
# compiles separately from .cache/xnu-work/bsd/miscfs/mockfs.  Rebuild it when the
# sources are newer, and force a kernel relink when it changed.
MOCKFS_ARCHIVE=$O/tree/build/mockfs-fixture/libmockfs_fixture.a
MOCKFS_SRC=$W/bsd/miscfs/mockfs
mkdir -p "$V385_OUT"
if [ ! -f "$MOCKFS_ARCHIVE" ] || [ "$MOCKFS_SRC/mockfs_vnops.c" -nt "$MOCKFS_ARCHIVE" ] \
   || [ "$MOCKFS_SRC/mockfs_fsnode.c" -nt "$MOCKFS_ARCHIVE" ] \
   || [ "$MOCKFS_SRC/mockfs_vfsops.c" -nt "$MOCKFS_ARCHIVE" ]; then
  export PATH="$UNIXNU_TOOLCHAIN/CommandLineTools/usr/bin:$UNIXNU_TOOLCHAIN/bin:$PATH"
  python3 "$O/tree/scripts/build-mockfs-fixture.py" >"$V385_OUT/mockfs-fixture.log" 2>&1 \
    || { echo MOCKFS_FIXTURE_FAILED; tail -20 "$V385_OUT/mockfs-fixture.log"; exit 1; }
  rm -f "$O/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped"
fi
grep -qF 'v319 lk enoent' "$MOCKFS_ARCHIVE" || { echo MOCKFS_FIXTURE_STALE; exit 1; }

./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V385_OUT/kernel.log" 2>&1 || { echo BUILD_FAILED; tail -40 "$V385_OUT/kernel.log"; exit 1; }
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V385_OUT/prelink.log" 2>&1 || exit 1
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || exit 1
# gate: C1a probes + all previous v384 labels
for p in 'v385 ufs enter' 'v385 cap' 'v385 ver' 'v385 hcpid' 'v384 pad' 'v384 pad bytes' 'v382 sp' 'v382 ktop' 'v381 lret' 'v380 sp1 esr' 'v319 lk launchd' 'v379 noamfi' 'v379 inval' 'v379 bladd' 'v378 pm%d' 'v378 pc' 'v377 nocrypto SHA256_Init' 'v377 nocrypto SHA256_Final' 'v376 root bytes' 'N4KROOT' 'v375 rv' 'v375 sig' 'v375 xstat' 'v374 c7' 'v373 str' 'v372 dirtyflush' 'v371 lr' 'v363 post'; do N=$(strings "$K" | grep -cF "$p" || true); echo "$p $N"; [ "$N" -gt 0 ] || exit 1; done
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V385_OUT/payload.log" 2>&1 || exit 1
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V385_OUT/boot.img" >"$V385_OUT/pack.log" 2>&1 || exit 1
cp "$K" "$V385_OUT/kernel.macho"; cp "$P" "$V385_OUT/payload.img"; (cd "$V385_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v385 boot.img md5=$(md5sum "$V385_OUT/boot.img" | cut -d' ' -f1)"
