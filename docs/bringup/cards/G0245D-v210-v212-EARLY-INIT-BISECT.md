# G0245D v210–v212 判读卡 —— 早期初始化分段夹逼（1500 有 / 1520 无）

日期：2026-11-20
镜像：`g0245d-ios165-v210.img` md5 `3c9edc764acdeb8688aac7e0d50029de`（14:43:52 已刷）
　　　`g0245d-ios165-v211.img` md5 `81cf3d3dc51e5511032e40be51b28938`（15:15:50 已刷）
内核：v210 sha256 `125b24fe…` / v211 sha256 `49bb0f19af822891…` / v212 sha256 `870dd404469d7a64…`（已编译，镜像未打）
状态：**v210、v211 已刷入并判读完毕；v212 待打包刷入**

---

## 一、一句话结论

内核执行到 `arm_init()` 里 `boot_progress_init()` 返回之后、`wfe_timeout_configure()` 返回之前停住。
区间内另外三个 `configure_*_apple_*()` **在本构建里是空函数**，所以真正的可执行嫌疑只剩
`wfe_timeout_configure()` 与 `wfe_timeout_init()`（v212 就是为这四步装的夹逼点）。

---

## 二、打点机制为什么改成"从 C 里画"

v207/v209 的带用汇编宏 `FB_MARK207` 画在 `start.s` 里，最靠后那条（1420 红）画在 `ret` **之前**。
它能证明"准备返回了"，但**不能证明返回后真的进了 C**。v210 起改用 `arm_init.c` 里的
`g0245d_fb_band(args, row, g, r, b)`：

- 地址取 `args->Video.v_baseAddr` / `v_rowBytes`（偏移 `0x28` / `0x38`），与汇编宏同源；
- 每点画 8 行满宽；`v_rowBytes` 实测 **3248**（不是 1080×3=3240，每行 8 字节填充），所以无对角偏移；
- 画完必须 `dsb sy` → 逐 64B `dc civac` → `dsb sy`。`ARM_TTE_BOOT_BLOCK` 是 write-back cacheable，
  面板直接读 DRAM，**不清到 PoC 就会出现"画了但看不见"**；
- 所有点都放在 `arm_vm_init()` 之前：那时 TTBR0 还是引导期 V=P 表，v209 加的 `0x83400000` 8MiB
  恒等窗口有效。切表之后同址不再保证可用，别越过这条线打点。

---

## 三、读色规则（唯一正确版本，别再算错）

宏参数顺序是 **(G, R, B)**，屏幕显示按 **(r, g, b)** 念。即：

```
屏幕 r = 第 2 个参数   屏幕 g = 第 1 个参数   屏幕 b = 第 3 个参数
```

完整对照表（按执行顺序）：

| raw 行 | 补丁参数 (G,R,B) | 屏幕读色 (r,g,b) | 颜色 | 含义 | 来源 |
|---|---|---|---|---|---|
| 1300 | `00 FF FF` | (255,0,255) | 品红 | `start_first_cpu` 入口，MMU 关 | v207 |
| 1320 | `FF FF 00` | (255,255,0) | 黄 | `common_start`，引导页表已建 | v207 |
| 1340 | `FF 00 FF` | (0,255,255) | 青 | TCR 编程完 | v207 |
| 1360 | `FF 00 00` | (0,255,0) | 绿 | TTBR0/1 编程完 | v207 |
| 1380 | `00 00 FF` | (0,0,255) | 蓝 | 开 MMU 前最后一笔 | v207 |
| 1400 | `FF FF FF` | (255,255,255) | 白 | MMU + 缓存已开 | v209 |
| 1420 | `00 FF 00` | (255,0,0) | 红 | `start.s` 的 `ret` 即将执行 | v209 |
| 1440 | `00 FF 80` | (255,0,128) | 玫红 | 进入 `arm_init` 函数体 | v210 |
| 1460 | `80 00 FF` | (0,128,255) | 天蓝 | `PE_init_platform` 返回 | v210 |
| 1480 | `FF 80 00` | (128,255,0) | 黄绿 | 早期 init 全过，`arm_vm_init` 前 | v210 |
| 1500 | `80 FF 00` | (255,128,0) | 橙 | `boot_progress_init` 返回 | v211 |
| 1520 | `00 80 FF` | (128,0,255) | 紫 | Apple timer/wfe/misc 全过 | v211 |
| 1540 | `C0 FF 00` | (255,192,0) | 金 | CPU 拓扑就绪，`thread_bootstrap` 前 | v211 |
| 1560 | `C0 00 FF` | (0,192,255) | 天青 | `thread_bootstrap` 返回 | v211 |
| 1580 | `FF 00 80` | (0,255,128) | 春绿 | `cpu_bootstrap` 返回 | v211 |
| 1600 | `80 00 80` | (0,128,128) | 青绿 | `timer_call_init` 返回 | v211 |
| 1640 | `80 80 FF` | (128,128,255) | 淡蓝紫 | `processor_bootstrap` 返回 | v211 |
| 1660 | `FF FF FF` | (255,255,255) | 白 | 进 Apple 初始化前（`configure_timer_apple_regs` 前） | v212 |
| 1680 | `00 FF 00` | (255,0,0) | 红 | `configure_timer_apple_regs` 返回 | v212 |
| 1700 | `FF 00 FF` | (0,255,255) | 青 | `wfe_timeout_configure` 返回 | v212 |
| 1720 | `FF FF 00` | (255,255,0) | 黄 | `wfe_timeout_init` 返回 | v212 |
| 1740 | `00 FF FF` | (255,0,255) | 品红 | `configure_misc_apple_boot_args` 返回 | v212 |
| 1760 | `FF 00 00` | (0,255,0) | 绿 | `configure_misc_apple_regs` 返回 | v212 |

⚠️ **颜色有重复**（v212 的 6 条与 v207 的 5 条同色），判读必须靠**行位置**，不能只认颜色。
用 `workspace/tools/analyze-bands.py` 自动按校准位置判，别肉眼猜。

---

## 四、v210 判读结果：进入 C 已被证实，1480 缺失

照片 `IMG_20261120_1448*`（DarwinBoot 菜单，显存跨重启不清，上一轮色带原样透出）。
逐色扫描结果：1440 玫红、1460 天蓝**都在**，1480 黄绿**缺失**，下方 1300–1420 七条全在。

结论：`ret` 成功落进 `arm_init`，`PE_init_platform()` 返回了，**死在 `PE_init_platform` 返回之后、
`arm_vm_init` 之前**——区间从"整个 `arm_init`"缩到约 160 行。

## 五、v211 判读结果：卡在 1500 与 1520 之间

v211 在 1460–1480 之间插了 7 条（1500/1520/1540/1560/1580/1600/1640）。
照片 `IMG_20261120_151717.jpg`（`$HOME/Pictures/`）实拍判读：

```
raw 1300–1500  present（9 条全在）
raw 1520       absent
raw 1540–1640  absent
raw 1480       absent
```

**最高存在点 = 1500 橙（`boot_progress_init()` 返回后）**，下一个点 1520 紫没有。
所以死点严格夹在下面这 5 个调用之间：

```c
boot_progress_init();          // ← 1500 橙（活着）
configure_timer_apple_regs();  // ← 空函数
wfe_timeout_configure();
wfe_timeout_init();
configure_misc_apple_boot_args(); // ← 空函数
configure_misc_apple_regs();      // ← 空函数
                               // ← 1520 紫（没画）
```

## 六、关键事实：三个 Apple 函数是空的，嫌疑只剩 wfe

`osfmk/arm/machine_routines_apple.c` 第 49–61 行，实测：

```c
void configure_misc_apple_boot_args(void) { }
void configure_misc_apple_regs(void)       { }
void configure_timer_apple_regs(void)      { }
```

也就是说"苹果专用 sysreg trap"这个假设**当前没有证据支撑**——它们根本不写寄存器。
真正会执行的只有 `osfmk/arm64/machine_routines.c` 里的：

- `wfe_timeout_configure()`（第 2275 行）：解析 `wfe_events_sec` boot-arg + 算 ticks，主要是算术与 `PE_parse_boot_argn`；
- `wfe_timeout_init()`（第 2253 行）：`_enable_timebase_event_stream(arm64_eventi)`，写 **CNTKCTL_EL1** 的事件流位
  （`EL0VCTEN` / `EVNTEN`）。

如果 1700 缺失，说明挂在 `wfe_timeout_configure()`；如果 1700 有、1720 无，那就是
`_enable_timebase_event_stream()` 写 `CNTKCTL_EL1` 之后出的事（EL2/EL3 未放行或事件流行为异常）。

## 七、v212：在这 5 步之间插 6 个点（待刷）

补丁 `patches/xnu/zzz212-g0245d-ios165-timer-wfe-marks.patch`（6 hunk，只加打点、不改调用）：

| 顺序 | raw 行 | 颜色 | 卡在 |
|---|---|---|---|
| 1 | 1660 | 白 | 进 Apple 初始化前 |
| 2 | 1680 | 红 | `configure_timer_apple_regs()` 返回 |
| 3 | 1700 | 青 | `wfe_timeout_configure()` 返回 |
| 4 | 1720 | 黄 | `wfe_timeout_init()` 返回 |
| 5 | 1740 | 品红 | `configure_misc_apple_boot_args()` 返回 |
| 6 | 1760 | 绿 | `configure_misc_apple_regs()` 返回 |

全部落在既有 1500 与 1520 之间（raw 行更靠上 = 更晚执行），1480 仍是"整段过了"的判据。

**当前状态（未完成）**：内核已编译，`kernel.macho` sha256 `870dd404469d7a643d6d686edd78dffaf42a227f1817e8ec58cb650962c404ee`，
payload 已生成（24 MiB，已验证含该内核）。但 `linux/ios-pipeline.py` 在回读
`payload/stage/EFI/UniXNU/Payloads/kernel.macho` 时 `FileNotFoundError` 中断（第 190 行），
**boot 镜像还没打、也没刷**。下一轮直接走手工三步（kernel → payload → `pack_fd.py`）绕过该检查，
打包后按 v210/v211 的同一套自校验（FD md5 = GOOD、DTB 尾表与 v206 逐字节同、QCOM 签名尾保留）再刷。

## 八、判读方法（每轮照抄）

```bash
cd $HOME/WorkBuddy/G0245D
$HOME/.workbuddy/binaries/python/envs/default/bin/python \
  workspace/tools/analyze-bands.py $HOME/Pictures/<照片>.jpg
```

脚本按 HSV 分类 + 带宽 4–18px 过滤（排除菜单 UI 色块）+ 相邻带间距链式校验，
输出每条带 present/absent 与照片 y 坐标，最后给出"执行顺序最高点 → 下一个点"。
已用 v210、v211 两张实拍照自校准，结论与手工判读一致。

拍 **DarwinBoot 菜单**即可：显存跨重启不清，菜单只画字形不填背景，上一轮色带会原样透出，
不必赌 handoff 后那几秒。

## 九、这一轮踩到的坑（新窗口必读）

1. **参数顺序 (G,R,B)**，屏幕按 (r,g,b) 读。已经错两次：1300 是品红、1340 是青（不是反过来）。
2. **必须 `dc civac` 清到 PoC**，否则脏缓存行让色带"画了看不见"，会误判成"没执行"。
3. **必须在 `arm_vm_init()` 切页表之前打点**，之后 `0x83400000` 恒等窗口不再保证有效。
4. `XNU_BOOT_PROGRESS` 默认关闭，`.boot-progress-mode` 实测 `0:disabled`，
   `boot_progress_stage()` 是**空宏**——别指望文字进度，那是死路。
5. 色带**颜色会重复**，判读靠行位置，不靠颜色名。
6. `ios-pipeline.py` 的 staged-kernel 回读会无谓中断（v212 已复现），手工三步更稳。
7. 补丁落地前跑 `patch -p1 --dry-run` + `git apply --check` 双校验；
   想确认"构建树里到底是哪一版"，对当前 `arm_init.c` 反向 `patch -R` 即可。
