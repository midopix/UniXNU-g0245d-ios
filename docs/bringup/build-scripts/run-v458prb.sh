#!/bin/bash
# v458prb: official Stage-5 stage-4 reset probe. Reuse the v456bp kernel and
# inject a timed PSCI reset after the 1st _arm_vm_init call via board.toml.
set -o pipefail
export V365_BASE=/home/myth
export V365_DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
export V365_SOC=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-msm8996-common
export V429_OUT=/home/myth/g0245d-auto/auto/v458prb
export UNIXNU_UEFI=/home/myth/g0245d-clean/Mu-Silicium
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
export PATH="$UNIXNU_TOOLCHAIN/CommandLineTools/usr/bin:$UNIXNU_TOOLCHAIN/bin:/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d
mkdir -p "$V429_OUT"; cd "$UX" || exit 1

echo "=== 0) probe tool adapted check ==="
grep -q 'kernel-version specific' "$O/tree/scripts/patch-xnu-entry-probe.py" || { echo TOOL_NOT_ADAPTED; exit 1; }
echo "probe tool adapted OK"

echo "=== 1) prelink clean kernel ==="
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/prelink.log" 2>&1 || { echo PRELINK_FAILED; tail -20 "$V429_OUT/prelink.log"; exit 1; }
K=$O/kernel/kernel.macho
echo "prelinked kernel $(stat -c %s "$K") bytes"

echo "=== 2) payload with stage-4 reset probe ==="
rm -f "$O/logs/payload-patch.log"
PATH=/usr/bin:/bin ./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/payload.log" 2>&1
PRC=$?
echo "payload rc=$PRC"
tail -8 "$V429_OUT/payload.log"
if [ "$PRC" != 0 ]; then echo PAYLOAD_FAILED; exit 1; fi

echo "=== 3) verify probe injection ==="
PL=$O/logs/payload-patch.log
[ -f "$PL" ] || { echo NO_PATCH_LOG; exit 1; }
cat "$PL"
grep -q 'stage 4 reset after call' "$PL" || { echo NO_STAGE4_RESET; exit 1; }
grep -q '_arm_vm_init in _arm_init' "$PL" || { echo WRONG_TARGET; exit 1; }
echo "PROBE_INJECTED_OK (stage-4 reset after _arm_vm_init)"

echo "=== 4) pack ==="
P=$O/payload/payload.img
[ -f "$P" ] || { echo NO_PAYLOAD_IMG; exit 1; }
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V429_OUT/boot.img" >"$V429_OUT/pack.log" 2>&1 || { echo PACK_FAILED; tail -20 "$V429_OUT/pack.log"; exit 1; }
cp "$P" "$V429_OUT/payload.img"; cp "$PL" "$V429_OUT/payload-patch.log"
(cd "$V429_OUT" && md5sum boot.img payload.img > MD5.txt)
echo "BUILD_DONE v458prb boot.img md5=$(md5sum "$V429_OUT/boot.img" | cut -d' ' -f1)"
grep -ao 'boot-progress=[0-9]' "$P" | head -2 || true

echo "=== 5) copy to Windows ==="
WIN=/mnt/d/G0245D/auto/v458prb
mkdir -p "$WIN"; cp "$V429_OUT"/* "$WIN"/
md5sum "$WIN/boot.img"
