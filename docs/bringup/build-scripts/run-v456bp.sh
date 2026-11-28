#!/bin/bash
# v456bp: same official boot-progress kit as v455bp, but FIX the compile gate.
#
# ROOT CAUSE of v455bp: build-xnu-4k-baseline.sh takes -DXNU_BOOT_PROGRESS from
# the env var XNU_BOOT_PROGRESS (default 0), NOT from CONFIG_XNU_BOOT_PROGRESS=y
# in .config for the incremental make.  The boot_progress_*.o objects had been
# compiled earlier with 0; make does not track CFLAGS changes, so even though
# .config said y, the kernel-side call sites stayed as ((void)0) empty macros.
# Evidence: kernel.macho had the kit's own strings but NOT the instrumentation
# strings ("arm_vm_init enter", "vfs_mountroot enter", ... all count 0).
#
# FIX: export XNU_BOOT_PROGRESS=1 explicitly AND delete every translation unit
# that hosts a boot_progress_* call site so make recompiles them with the macro
# enabled, then STRICTLY gate on the instrumentation strings before packing.
set -o pipefail
export V365_BASE=/home/myth
export V365_DEV=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios
export V365_SOC=/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-msm8996-common
export V429_OUT=/home/myth/g0245d-auto/auto/v456bp
export G0245D_LAUNCHD=/home/myth/g0245d-assets/ios-16.5-20F66/sbin/launchd
export UNIXNU_TOOLCHAIN="${UNIXNU_TOOLCHAIN:-/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/workspace/tmp/unixnu-toolchain}"
export PATH="$UNIXNU_TOOLCHAIN/CommandLineTools/usr/bin:$UNIXNU_TOOLCHAIN/bin:/home/myth/.workbuddy/binaries/gitlocal/bin:/home/myth/.workbuddy/binaries/python/envs/default/bin:$PATH"
export BISON_PKGDATADIR="${BISON_PKGDATADIR:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/share/bison}"
export M4="${M4:-/home/myth/.workbuddy/binaries/gitlocal/root/usr/bin/m4}"
# ---- THE FIX: the legacy kernel build script reads this env var directly ----
export XNU_BOOT_PROGRESS=1
UX=$V365_BASE/UniXNU-runtime; O=$UX/out/g0245d/ios-16.5-20F66/g0245d
OBJ=$O/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837
mkdir -p "$V429_OUT"; cd "$UX" || exit 1
UK=$OBJ/mach.development.bcm2837.unstripped

echo "=== 0) force recompile of boot_progress instrumentation with macro=1 ==="
echo "XNU_BOOT_PROGRESS=$XNU_BOOT_PROGRESS"
for n in arm_init startup bsd_init kern_exec kern_exit video_console; do
  find "$OBJ" -name "$n.o" -type f -print -delete 2>/dev/null
done
rm -f "$UK" "$OBJ/.boot-progress-mode" "$O/tree/build/boot-progress/libBootProgress.a"

echo "=== 1) build kernel ==="
./unixnu build kernel -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" >"$V429_OUT/kernel-build.log" 2>&1 || echo BUILD_PRELINK_IPSW_IGNORED
RC=$?
echo "build kernel rc=$RC (prelink IPSW step is expected to fail here)"
if [ ! -f "$UK" ]; then
  echo NO_KERNEL
  tail -80 "$V429_OUT/kernel-build.log"
  exit 1
fi
if [ "$RC" != 0 ]; then
  echo "BUILD_RC_NONZERO_BUT_KERNEL_EXISTS"
  grep -n -iE 'error|undefined|failed' "$V429_OUT/kernel-build.log" | tail -30
fi
N=$(grep -c '^ld: symbol' "$V429_OUT/kernel-build.log" 2>/dev/null || true)
echo "link_symbol_errors=$N"
stat -c 'kernel relinked: %s bytes mtime=%y' "$UK"
cat "$OBJ/.boot-progress-mode" 2>/dev/null; echo

echo "=== 2) prelink --skip-prelink ==="
./unixnu prelink --skip-prelink -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/prelink.log" 2>&1 || { echo PRELINK_FAILED; tail -20 "$V429_OUT/prelink.log"; exit 1; }
K=$O/kernel/kernel.macho; [ "$(stat -c %s "$K")" -le 25000000 ] || { echo KERNEL_TOO_BIG; exit 1; }

echo "=== 3) STRICT instrumentation gates (these were 0 in v455bp) ==="
for p in 'PE initialized; early native mappings' 'arm_vm_init enter' 'arm_vm_init returned' 'vfs_mountroot enter' 'load_init_program enter' 'monitor continuous' 'boot_progress' 'boot-progress'; do
  N=$(strings "$K" | grep -cF "$p" || true)
  echo "  [$N] $p"
  [ "$N" -gt 0 ] || { echo "GATE_FAILED: $p not in kernel -> instrumentation still empty"; exit 1; }
done
echo "ALL_INSTRUMENTATION_GATES_PASS"

echo "=== 4) payload + pack ==="
./unixnu payload -D "$V365_DEV" --os ios-16.5-20F66 --local-module "soc:msm8996=$V365_SOC" --unique-chip-id 0x47403234 >"$V429_OUT/payload.log" 2>&1 || { echo PAYLOAD_FAILED; tail -20 "$V429_OUT/payload.log"; exit 1; }
P=$O/payload/payload.img
python3 "$V365_DEV/tools/pack_fd.py" --base "$V365_BASE/assets/stock-boot-trimmed.img" --fd "$V365_BASE/assets/GOOD-fd-bootshim-v195.bin" --ramdisk "$P" --out "$V429_OUT/boot.img" >"$V429_OUT/pack.log" 2>&1 || { echo PACK_FAILED; tail -20 "$V429_OUT/pack.log"; exit 1; }
cp "$K" "$V429_OUT/kernel.macho"; cp "$P" "$V429_OUT/payload.img"
(cd "$V429_OUT" && md5sum boot.img kernel.macho payload.img > MD5.txt)
echo "PIPELINE_BUILD_DONE v456bp boot.img md5=$(md5sum "$V429_OUT/boot.img" | cut -d' ' -f1)"

echo "=== 5) payload boot args ==="
grep -o 'boot-progress=[0-9]' "$P" | head -3 || true
