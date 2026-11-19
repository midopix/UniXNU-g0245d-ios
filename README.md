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

## Firmware inputs

`proprietary-files.txt` lists the QFIL images consumed by the port. The stock
serial console runs on BLSP2 UART2 (0x75b0000) at 115200 8n1
(`console=ttyHSL0,115200,n8`).
