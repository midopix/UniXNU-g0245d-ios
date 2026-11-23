# UniXNU g0245d

Device support for Gree G0245D（格力手机·色界，2017）, codename `g0245d`, with
Qualcomm MSM8996 (Snapdragon 820). The device profile selects
[UniXNU-msm8996-common](https://github.com/UniXNU/UniXNU-msm8996-common) and the
`ios-16.5-20F66` OS profile in UniXNU.

## Target: iOS 16.5 (XNU 8796.101.5)

This repository is the **iOS 16.5** port of UniXNU for the G0245D. The target was
moved from the earlier `ipados-17.7.11-21H461` (XNU 10063) bring-up line to
**iOS 16.5 build 20F66 / Darwin 22.5.0 / XNU 8796.101.5**, following the upstream
`Asultop/UniXNU-NX769J` 8796 port and the `Yuanchu000I/UniXUN-g0345d`
`device/g0245d-ios16.5` proposal.

The iOS 16.5 setup here is self-contained:

- `profiles/os/ios-16.5-20F66/` — OS profile with IPSW SHA256 pins, config and
  the rebased `patches/xnu/series`. Point UniXNU's profile resolver here.
- `patches/xnu/series` — 64 patches rebased onto XNU 8796.101.5 (device-local
  series selected via `board.toml`'s `device:patches/xnu/series`).
- `patches/libpthread/` — libpthread fix for the missing
  `proc_get_jit_entitled` symbol on XNU 8796.
- `scripts/` — helpers for IPSW pin extraction, prelink storage bindings and
  boot image packaging.

A **skip-prelink** kernel was built successfully from this tree; see the board
config for the payload/boot partitioning. Full prelink is not qualified for the
20F66 restore yet. Keep the iPadOS 17 line in the separate
`midopix/UniXNU-g0245d` repository if it is needed again.

## Structure

| Path | Contents |
| --- | --- |
| `porting.toml` | Subsystem inputs, findings, evidence and completion criteria |
| `board.toml` | Device configuration and component selection |
| `feeds.toml` | Pinned SoC source |
| `configs/g0245d_defconfig` | Device kernel settings |
| `dts/g0245d.dts` | Memory, CPU selection, and peripheral configuration |
| `dts/panel-ft8716.txt` | ft8716 DSI panel mode and decoded DCS init sequence |
| `patches/xnu/series` | Board patches |
| `proprietary-files.txt` | Firmware input paths |
| `REA-WORKFLOW.md` | REA reverse-engineering procedure and per-blob task cards |
| `scripts/` | QFIL extraction and device inspection tools |

Stage 1 selects `ArmDTPlatform`, `ArmCpu`, `SoftwareAES`, `XnuPrelink` and
`DarwinBoot` only. No SM8550-specific component (ShengUfs, Adreno740,
AdrenoMetal, DPU, GENI) covers MSM8996: the port needs `NativeUfs8996`,
`Adreno530`, `Mdp5` and `BlspI2c` before the matching peripherals can be
enabled. See [PORTING-PLAN.md](../PORTING-PLAN.md) for the stage schedule.

Hardware facts come from the stock QFIL package (`G0245D_Gree_user_QFIL_images`):
the board device tree (`board.dtb`), the boot image header, the UFS rawprogram
XML and the firmware blobs. `dts/g0245d.dts` carries the real
`cont_splash_mem` range (0x83401000, 0x23ff000) that the stock ABL uses for
the ft8716 panel framebuffer; stage 1 adopts it through `GopFramebuffer`.

## Development record

Maintain [porting.toml](porting.toml) with every subsystem change. It records
hardware, configuration, procedures, findings, evidence and completion criteria.
The [device page](https://unixnu.com/devices/g0245d) renders this record.
Maintainers and agents follow the [same guide](https://unixnu.com/porting/records).
The required `Porting record` CI check validates structure, component coverage
and updates to findings or evidence for changed code.

## Build

Run from the UniXNU checkout:

```sh
./unixnu defconfig g0245d_defconfig --device ../UniXNU-g0245d
./unixnu status --device ../UniXNU-g0245d --json
./unixnu build kernel --device ../UniXNU-g0245d
```

`feeds.toml` pins `REQUIRED_SOC_COMMIT` until the SoC repository reaches a
reviewed commit; the resolver falls back to the local checkout through
`local.toml` / `--local-module` until then.

### Reproducing the bring-up builds (Linux host)

Linux is a first-class host here: `scripts/linux/setup-toolchain.py` installs
the Mach-O toolchain plus an `xcrun(1)` shim (`xcrun ar` -> `ar`, `xcrun nm` ->
`llvm-nm`, `-show-sdk-path` -> the build tree's fakeroot), so every macOS-only
tool call resolves on Ubuntu. The pipeline is plain bash + python3 — no
Windows-only tooling is involved.

```sh
# 1. base tree (UniXNU runtime + device profile + Mu-Silicium + assets)
export G0245D_BASE=~/g0245d-clean    # holds UniXNU-runtime, ios-device, Mu-Silicium, assets
export G0245D_OUT=~/g0245d-auto     # build output root

# 2. toolchain (Linux): clang/llvm + the xcrun shim
python3 "$G0245D_BASE/UniXNU-runtime/scripts/linux/setup-toolchain.py"

# 3. device kernel config (CONFIG_XNU_SOURCE_MOCKFS=y is line 15 of the defconfig)
cd "$G0245D_BASE/UniXNU-runtime"
./unixnu defconfig g0245d_defconfig -D "$G0245D_BASE/ios-device" --os ios-16.5-20F66

# 4. apply the board patches to the xnu work tree
export XNU_WORK="$G0245D_BASE/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work"
#    either the single consolidated patch ...
git -C "$XNU_WORK" apply /path/to/UniXNU-g0245d-ios/patches/xnu/zzz900-CONSOLIDATED-v290.patch
#    ... or the incremental scripts in order (each one is idempotent)
for f in $(ls /path/to/UniXNU-g0245d-ios/scripts/linux/patch_v*.py | sort -V); do
  python3 "$f" || { echo "failed: $f"; break; }
done

# 5. build + pack (the "FD: GOOD" line means success)
cd /path/to/UniXNU-g0245d-ios
bash scripts/linux/auto-v212-pipeline.sh build v291
```

Two binary inputs are **not** redistributable and are therefore not in this
repository; copy them into `$G0245D_BASE/assets/` (the pipeline picks them up
automatically and refuses to fall back to a locally built FD):

| Asset | Size | MD5 | Used for |
| --- | --- | --- | --- |
| `GOOD-fd-bootshim-v195.bin` | 3145968 | `5441ef72de8bd459e5ecb4a182dc9e36` | vendor UEFI FD — a locally built FD has an empty SPMI DXE and cannot light the panel |
| `stock-boot-trimmed.img` | 47218688 | `e54a55f308d9ed9849edd64e77c2319b` | stock boot image used as the packing base |

Flashing needs no Windows either: `scripts/linux/flash-boot.sh` runs the
environment self-check, verifies md5 and serial, and flashes the `boot`
partition only (aboot/xbl/rpm/tz/system/userdata are never touched).
`scripts/linux/flash-watcher.sh` plus `g0245d-flash.service` provide the
same "plug it in and it flashes" behaviour as a systemd unit.

### Mockfs memory root (v290+)

`CONFIG_XNU_SOURCE_MOCKFS=y` in `configs/g0245d_defconfig` enables XNU's
offline mockfs: `archive-07-build-mockfs-fixture.py` builds
`libmockfs_fixture.a`, the build links it with `-Wl,-force_load`, and
`vfs_conf.o` is compiled with `-DMOCKFS=1`. That gives the kernel a memory
root device whose whole content is the `/sbin/launchd` Mach-O — no storage
driver needed. The board side (an in-memory disk holding a hand-built arm64
Mach-O, `mdevadd`, `rd=md0`) lives in
`scripts/linux/patch_v289.py`.

Two things to keep in mind when touching the build inputs:

- `CONFIG_XNU_*` switches are read from the generated `work/.config`; that
  file is regenerated by `unixnu defconfig`, so **edit the defconfig source**,
  never the generated file.
- XNU's `bsd/conf/files` parser wants exactly two tokens per line
  (`path standard` / `path optional <opt>`); a trailing comment is a syntax
  error. After editing `files` or the config fragments, delete
  `build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/Makefile` so
  `doconf` regenerates the filelist.

## Firmware inputs

`proprietary-files.txt` lists the QFIL images consumed by the port. The stock
serial console runs on BLSP2 UART2 (0x75b0000) at 115200 8n1
(`console=ttyHSL0,115200,n8`).

## Progress log and handoff

This repository holds **reproducible artefacts only**: board patches, the
consolidated kernel patch, the build and flash scripts, the device kernel
config, the device tree and the technical notes needed to redo the work.

The running log — per-version judgement, the photo-by-photo reading notes,
the hardware fact dump, the full rebuild guide and the boot images — is kept
outside this repository and is intentionally not mirrored here.

