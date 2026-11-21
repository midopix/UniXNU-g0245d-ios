# 同赛道项目扫描（2026-11-21）

以 GitHub 公开仓库为样本，检索词覆盖 `UniXNU`、`ios 16.5 bring-up`、`xnu msm8996/8998`、
`ios-sweet` 等，共 40 余个仓库。这里只记录**进度位置**与**可复用的具体产物**，不做质量评价。

## 一、进度分层

### A. 已到 iOS/iPadOS 主屏（有 userland）

| 项目 | 设备 / SoC | 到达点 | 备注 |
|---|---|---|---|
| `dipa-studio/ios-sweet` ★1377 | Redmi Note 10 Pro / SM7150 | iOS 16.7.16 主屏、设置、控制中心、触摸 | 元祖项目；CPU 渲染，UFS + HFS+ root，iPhone X 身份 |
| `leafall903/ios-sweet-umi` | 小米 10 / SM8650 | iOS 16.5 v6 锁屏 + SpringBoard | Mesa/freedreno GL 路径 |
| `Fcaing/hakios-venus` | 小米 11 / SM8350 | iOS 16.5 主屏 + 设置 + HFS+ 持久化 | 卡在 Wi-Fi：QCA6490 IPCR 通道固件不认领 |
| `XRC111/unixnu-fuxi-full` | 小米 13 / SM8550 | iPadOS 17.7.11 + NativeUfs + **NativeMetal/Adreno 740** | 少见的有 GPU 硬件呈现 |
| `jerry-2009/UNIXNU_elden` ★7 | Legion Y700 Gen4 / SM8750 | iPadOS 17.7.11，Settings 可开 | 有帧缓冲映射优化实测（整屏 CPU 拷贝 716→134 ms） |
| `Droid-VM/UniXNU-droidvm` ★22 | Gunyah/crosvm 虚拟机 | iPadOS 17 on 4 KiB XNU | 完整 build 脚本 + Metal 插件（Mesa Turnip） |

### B. 到 BSD/IOKit、root 已挂载

| 项目 | 设备 / SoC | 到达点 |
|---|---|---|
| `lss717/UniXNU-cheeseburger` | OnePlus 5 / **MSM8998** | 4 KiB XNU 到 BSD/IOKit；UFS + APFS root 挂载；launchd exec、dyld cache 诊断中 |

### C. 平台专家 / 早期

| 项目 | 设备 / SoC | 到达点 |
|---|---|---|
| **本项目** | 格力 G0245D / MSM8996 | `PE_create_console()` 内（v225 待判读） |
| `Yuanchu000I/UniXUN-g0345d` ★2 | 格力 G0345D / MSM8996 | Stage 5 WFE/clock（timebase=0），v10 ADT 补丁未上机 |
| `lvyufeng/ios-le-pro3` | 乐视 Le Pro 3 / MSM8996 Pro | 只有硬件事实 + 只读探针，尚无内核 |
| `Floppikrob/ios-galaxy-s8` ★51 | Galaxy S8 / Exynos 8895 | 锁屏（ARMv8.0、4 KiB 页、S-Boot framebuffer） |

## 二、我们在坐标系里的位置

- 在 **MSM8996 家族**里排第一：G0345D 还卡在我们要已经越过的 WFE/clock，Le Pro 3 连内核都没有。
- 在 **老 ARMv8.0 设备**里排第二：Galaxy S8 已到锁屏，但它是 Exynos，没有 UEFI 移植负担。
- 在 **MSM8998（同代高通、4 KiB、ARMv8.0）** 后面：cheeseburger 已到 launchd exec。

结论：MSM8996 的难点不在 XNU，而在**引导链要自己造**（Mu-Silicium 的 86 个 platform package
里没有 MSM8996，`uefi-g0245d` 是我们自己的产物）。

## 三、可直接复用的东西

### 1. 日志手段（价值最高）

`Floppikrob/ios-galaxy-s8`（源自 ios-sweet 系列）带了一整套"不拍屏"的观测补丁：

| 补丁 | 作用 |
|---|---|
| `xnu/patches/0003-sweet-framebuffer-serial-console.patch` | 把 kprintf 同时输出到 framebuffer 与串口 |
| `0010-sweet-early-framebuffer-debug.patch` | 极早期（PE 之前）的 framebuffer 输出 |
| `0047-sweet-persistent-console-log.patch` | console 落到存储，重启后仍可读 |
| `0077-sweet-usb-live-log.patch` | **通过 USB 实时读内核日志** |
| `tools/dreamlte/pull-log.ps1` | Windows 侧把日志拉下来 |

我们的色带 ladder 是"离散、一次性、靠拍照"，一旦跨过 console 初始化就应该换成长文本日志。
G0245D 有 BLSP2 UART2（`0x75b0000`），串口是首选，USB live log 是次选。

### 2. 帧缓冲映射

`jerry-2009/UNIXNU_elden` 的 `docs/FRAMEBUFFER-WC.md`：写合并（write-combining）映射后，
整屏 CPU 拷贝从 716 ms 降到 134 ms。正好对应我们 `640/660` 探针暴露的问题
（帧缓冲 PA 不在 `[gPhysBase, +real_phys_size)`，`phystokv` 换算不出来）。

### 3. ADT / board 生成方式

`XRC111/unixnu-fuxi-full` 明确：board file 与 ADT generator 的数值**取自 stock firmware 与
stock device tree**，不是手写常量。我们的 ADT 是 UniXNU 缺省生成 + 手工补丁，缺 `arm-io`
节点就是这个原因。G0345D 那边的做法（改 `arm-io/ranges` 到 64 KiB 对齐）也印证了这条路。

### 4. 页大小与原子指令

- 我们 `ios-device/board.toml` 是 **page_size 4096**，与 MSM8996 一致（MSM8996 不支持 16 KiB 页）。
- `lvyufeng/ios-le-pro3` 指出 XNU 8796 期待 LSE 原子指令，而 ARMv8.0 没有；
  `Floppikrob/ios-galaxy-s8` 有 `tools/dreamlte/lse-scan.sh` 用于确认二进制里是否残留 LSE。
  等过了 PE 段、进 pmap/IOKit 时需要用这个脚本扫一遍内核镜像。

### 5. payload 体积坑

`keyfan/UniXNU-enchilada-bringup` 记录：Mu-Silicium 自带的 `Mu-enchilada.img` ramdisk
只有 5 字节、没有 payload 卷，设备掉 EDO 9008。这与我们 v215 的"FAT 卷类型不匹配导致
UniXNU 找不到 boot entry"是同一类问题，方向一致。

## 四、不建议照搬的

- **iOS 16.7.16 用户态（20H392）**：ios-sweet 系全部基于 iPhone X 的 16.7.16；
  我们的目标是 16.5 / 20F66，root 与 shared cache 不能混用。
- **CPU 软件渲染**：ios-sweet / galaxy-s8 都是 CPU 渲染 20–30 fps，属可接受的最小验证；
  真要可用还是得走 NativeMetal（fuxi 路线）。
- **改 ADT 治 timebase**：G0345D 的方向可行但绕；直接 `mrs cntfrq_el0` 更快（本项目 v219 已验证）。

## 五、扫描时的仓库快照

- 生成时间：2026-11-21 21:0x（UTC+8）
- 方法：GitHub REST API（`/search/repositories`、`/repos/{r}/readme`、`/git/trees`）
- 未收录：私有仓库、仅存档无 README 的仓库、与本目标无关的 iPadOS 27 试验仓
