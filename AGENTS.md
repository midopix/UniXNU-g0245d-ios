# Agent instructions

This repository owns g0245d board configuration, peripherals, firmware
selection, partition layout, power policy, and packaging. Shared MSM8996
resources and operations belong to `UniXNU-msm8996-common`. The documentation
site, component catalog, and common build tools belong to `UniXNU`.

Read the following before editing:

| Task | Required reading |
| --- | --- |
| Every port | [Porting](https://unixnu.com/porting/), [repository format](https://unixnu.com/porting/device-repository), [component catalog](https://unixnu.com/reference/components) |
| Hardware | [Device trees](https://unixnu.com/porting/device-tree), [matching](https://unixnu.com/drivers/device-tree-matching), selected SoC README and DTSI |
| Components | Selected component README, catalog metadata, build interface, relevant source |
| Kernel | Selected OS profile, XNU source, [patch reference](https://unixnu.com/xnu/source-and-patches), ordered patch series |
| Images | [Prelink](https://unixnu.com/concepts/prelink), [payload](https://unixnu.com/concepts/payload), [UEFI firmware](https://unixnu.com/porting/uefi-firmware) |
| Verification | [Building](https://unixnu.com/building), [bring-up](https://unixnu.com/porting/bring-up) |
| Migration | [Migration guide](https://unixnu.com/porting/migration) |

Search UniXNU's `components.toml` and read existing implementations before
adding a capability. Select components by interface, hardware scope, OS
ABI, and board dependencies. Use canonical component names in sources,
paths, build commands, and dependencies. Preserve source filenames,
runtime classes, bundle IDs, plugin filenames, symbols, and protocol IDs.

Use `dts/g0245d.dts` for board hardware and include the selected SoC DTSI.
Keep GPU votes and signed ZAP firmware inputs with the board. Inspect
`local.toml` and CLI overrides before changing source pins.

Run from the UniXNU checkout:

```sh
./unixnu defconfig g0245d_defconfig --device ../UniXNU-g0245d
./unixnu status --device ../UniXNU-g0245d --json
./unixnu tree --device ../UniXNU-g0245d
./unixnu build kernel --device ../UniXNU-g0245d
```

Use the README for firmware and payload inputs. Run existing checks
relevant to the change. Report commands, outputs, missing inputs, and
hardware observations separately. Record device boot, storage, display,
input, and GPU checkpoints.

Update relevant English and Chinese site pages in UniXNU. Write concise
English for this repository. Describe current behavior with direct
statements and ordinary punctuation.

## Porting record

Read the device's `porting.toml` and the
[record guide](https://unixnu.com/porting/records) before implementation.
For storage, also read the [UFS guide](https://unixnu.com/porting/ufs).
Update each affected area's findings or evidence with its code change.
The documentation site renders this same record. Follow its schema and
completion levels for both maintainer and agent work.

## MSM8996 specifics

- GICv3 uses `#interrupt-cells = <3>` (SM8550 uses 4): verify the ArmCpu
  3-cell path before enabling `cpu1..cpu3` in `dts/g0245d.dts`.
- The display is MDP5 + DSI 0 video mode with the FocalTech ft8716 panel;
  the decoded DCS sequence lives in `dts/panel-ft8716.txt`.
- The touch controller is Synaptics DSX on BLSP2 I2C (`i2c@75ba000`, SPI 106);
  the fingerprint sensor is a Goodix GF part on SPI.
- Wi-Fi/BT is QCA6174 over CNSS/PCIe; regulators and GPIOs are recorded in
  the network area of `porting.toml`.
- Reverse-engineering tasks follow `REA-WORKFLOW.md`; record every result
  with its command and output in the matching `porting.toml` area.

## Publishing after every build

Each G0245D build (`vNNN`) must end with the same two uploads. Do not skip
either one, and do not wait to be asked.

| Target | Repository | Contents | Sanitising |
|---|---|---|---|
| public | `midopix/UniXNU-g0245d-ios` | sources, patches, scripts, manifests, docs | **required**: run `scripts/desensitize.py .` first |
| private | `midopix/G0245D-xnu-bringup` | everything, including binaries, photos, raw logs, device serials, absolute paths | **none**: full upload |

- `github.com:443` is blocked here; every push goes through `api.github.com`.
  Use `scripts/push_tree.py <dir> <owner/repo> --branch main` (compares blob
  shas against the remote tree, so a rewritten remote history is fine).
  `scripts/push_via_api.py` fails with `lacks remote base commit` after such a
  rewrite.
- Files above 30 MB cannot go through the blob API (`boot.img`); use a release
  asset tagged `vNNN`.
- `HANDOFF.md` in the private repository is the single source of truth. Update
  it (sections 0, 2, 6, 8, 10 and 12) **before** uploading, every build.
