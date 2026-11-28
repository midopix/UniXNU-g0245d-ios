# 在新 Ubuntu 机器上重建 G0245D 构建环境

目标：clone 完后一条命令把环境拉起来，接着推进构建（v456bp 线及之后的探针镜像）。

## 快速开始

```bash
BASE=~/g0245d   # 或任意工作目录
git clone https://github.com/midopix/UniXNU-g0245d-ios.git $BASE/setup
bash $BASE/setup/docs/bringup/bootstrap-new-machine.sh   # BASE 需先 export
```

脚本做的事：
1. `apt install git python3 clang lld llvm`（构建只用系统 LLVM，**不需要 Apple 工具链**——本机
   runtime 的 `UNIXNU_TOOLCHAIN` 目录实际是空的，PATH 落到系统 clang 21）。
2. clone 三个树：
   - `UniXNU/UniXNU` → runtime（构建引擎）
   - `midopix/UniXNU-g0245d-ios` → 设备仓库（board.toml、os profile、patches/xnu/series、kits、assets 全部入库）
   - `midopix/UniXNU-msm8996-common` → SoC 仓库（`--local-module soc:msm8996=...` 用）
3. 对 runtime 应用 `docs/bringup/runtime-overlays/` 的 4 个补丁
   （baseline CFLAGS 传递 bug 修复——**这个必须打**，否则 boot-progress 调用点编译成空宏；
   entry-probe 工具的 iOS 16.5 MMU 序列适配——探针镜像必需；payload strip best-effort；
   NativeUfs8996 输出路径）。
4. 把 os profile 软链进 runtime `profiles/os/ios-16.5-20F66`（仓库里已带 profile.toml/
   ios.config；`patches/xnu/series` **有意为空**，真实补丁序列由设备仓库 `patches/xnu/series`
   承载）。
5. 打包资产软链：`~/assets` → 设备仓库 `assets/`（stock-boot-trimmed.img 45MB +
   GOOD-fd-bootshim-v195.bin 3MB，pack_fd.py 用）。
6. 最小 UEFI 目录（只含 Font.h 软链）给 panic screen 探针工具用——完整 Mu-Silicium
   (1.1GB) 只在重编 UEFI 固件时才需要，内核/探针工作用不到。
7. 收编的构建脚本复制到 `~/g0245d-scripts/` 并把 `/home/myth`、会话路径 sed 成本机路径。

## 仓库里的构建脚本（docs/bringup/build-scripts/）

| 脚本 | 作用 |
|---|---|
| `run-v456bp.sh` | boot-progress 内核全量构建。**含严格 gate**：删旧 .o 强制重编（make 不追踪 CFLAGS 变化）、校验 `arm_vm_init enter` 等插桩字符串>0 |
| `run-v457prb.sh` | panic screen 探针镜像（board.toml 临时写 panic_screen，payload 后恢复） |
| `run-v458prb.sh` | stage4 复位探针镜像（`--reset-after _arm_vm_init --in _arm_init`） |
| `finish_v457prb.sh` | payload 已生成时的 pack + 复制收尾 |
| `edit_board.py` | board.toml 探针开关（`panic` / `reset4`），构建后用备份恢复 |

## 已知坑（都写在 runtime-overlays/README.md）

- `CFLAGS_EXTRA` 是死路，personality/开关宏必须走 `<obj>.o_CFLAGS_ADD`。
- 改 CFLAGS 后必须删相关 `.o`，否则增量构建静默复用旧目标文件。
- panic screen 与任何 reset cave 共存会超 padding——**panic screen 只能单独 `--no-reset`**。
- payload 编译探针渲染器用 `PATH=/usr/bin:/bin`（workbuddy 自带 clang 会注入
  ptrauth flag，对 freestanding aarch64-none-elf 非法）。

## 本机（WSL Ubuntu-26.04, /home/myth）与本仓库的对应关系

- runtime 实际路径 `/home/myth/UniXNU-runtime`，构建输出 `/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/`
- 镜像产物 `/home/myth/g0245d-auto/auto/<ver>/`，最终复制到 Windows `D:\G0245D\auto\<ver>\`
- 已刷版本状态以 `D:\G0245D\auto-flash\state.json` + `flash-status.py` 为权威
