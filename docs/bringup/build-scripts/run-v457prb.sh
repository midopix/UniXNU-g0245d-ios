#!/bin/bash
# v457prb: official Stage-5 panic-screen probe. Reuse the v456bp kernel
# (boot-progress instrumentation already compiled in) and only re-run payload
# so patch-xnu-entry-probe.py injects the panic screen into the payload kernel.
set -o pipefail
export V365_BASE=/home/myth
export V365_DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
export V365_SOC=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-msm8996-common
export V429_OUT=/home/myth/g0245d-auto/auto/v457prb
export UNIXNU_UEFI=/home/myth/g0245d-clean/Mu-Silicium
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
export PATH="$UNIXNU_TOOLCHAIN/CommandLineTools/usr/bin:$UNIXNU_TOOLCHAIN/bin:/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d
mkdir -p "$V429_OUT"; cd "$UX" || exit 1

echo "=== 0) ensure adapted probe tool is in the build tree ==="
grep -q 'kernel-version specific' "$O/tree/scripts/patch-xnu-entry-probe.py" || { echo TOOL_NOT_ADAPTED; exit 1; }
echo "probe tool adapted OK"

echo "=== 1) fresh prelink (skip-ipsw) so payload starts from a clean kernel ==="
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/prelink.log" 2>&1 || { echo PRELINK_FAILED; tail -20 "$V429_OUT/prelink.log"; exit 1; }
K=$O/kernel/kernel.macho
echo "prelinked kernel $(stat -c %s "$K") bytes"

echo "=== 2) payload with board.toml panic_screen probe injection ==="
rm -f "$O/logs/payload-patch.log"
# The panic-screen renderer is compiled by patch-xnu-entry-probe.py via tool('clang').
# The Apple toolchain clang injects -fptrauth-... which is invalid for aarch64-none-elf,
# so use the system LLVM (clang/ld.lld/llvm-*) for this step. python3 + ./unixnu are
# on the clean PATH too. prelink above keeps the toolchain clang (needed for the kernel).
PATH=/usr/bin:/bin ./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/payload.log" 2>&1
PRC=$?
echo "payload rc=$PRC"
tail -15 "$V429_OUT/payload.log"
if [ "$PRC" != 0 ]; then echo PAYLOAD_FAILED; exit 1; fi

echo "=== 3) verify probe injection (authoritative: payload-patch.log) ==="
PL=$O/logs/payload-patch.log
if [ ! -f "$PL" ]; then echo NO_PATCH_LOG; exit 1; fi
echo "--- payload-patch.log ---"; cat "$PL"
grep -q 'panic screen' "$PL" || { echo NO_PANIC_SCREEN_PATCH; exit 1; }
grep -q 'stage 1 blue bar, stage 2 magenta bar' "$PL" || { echo NO_STAGE_BARS; exit 1; }
echo "PROBE_INJECTED_OK (panic screen + stage bars confirmed in patch log)"

echo "=== 4) pack boot.img ==="
P=$O/payload/payload.img
[ -f "$P" ] || { echo NO_PAYLOAD_IMG; exit 1; }
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V429_OUT/boot.img" >"$V429_OUT/pack.log" 2>&1 || { echo PACK_FAILED; tail -20 "$V429_OUT/pack.log"; exit 1; }
# Preserve the patched (unstripped) kernel from stage before it is discarded on next payload run.
# Extract it now from a fresh dry-run of the tool on the prelink kernel for the record.
cp "$K" "$V429_OUT/kernel-preprobe.macho"
cp "$P" "$V429_OUT/payload.img"
(cd "$V429_OUT" && md5sum boot.img payload.img kernel-preprobe.macho > MD5.txt)
echo "BUILD_DONE v457prb boot.img md5=$(md5sum "$V429_OUT/boot.img" | cut -d' ' -f1)"
grep -ao 'boot-progress=[0-9]' "$P" | head -2 || true
