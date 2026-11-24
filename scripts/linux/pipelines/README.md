# G0245D bring-up 流水线脚本（v346–v354）

一条流水线 = 应用补丁 → 编译 → 两次 prelink 打包 → 探针门禁校验 → 产出
`boot.img` / `kernel.macho` / `payload.img` / `MD5.txt`。

## 换机器时必须核对/修改的硬编码路径

脚本里是绝对路径，先全局替换成新机器的对应值：

| 路径（本机示例） | 用途 |
|---|---|
| `/home/myth/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work` | XNU 源码工作树（补丁打在这里） |
| `/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/env.sh` | 构建环境（llvm/工具链变量） |
| `/home/myth/WorkBuddy/2026-11-18-16-21-42/G0245D/local-src/device/UniXNU-msm8996-common` | 设备层（DTB/ramdisk 合成） |
| `/home/myth/g0245d-auto/auto/vNNN` | 产物输出目录 |
| `/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios` | 本仓库工作区 |
| `/home/myth/.workbuddy/binaries/gitlocal/bin/` | fastboot / adb / llvm-nm / m4 / bison 所在目录 |

## 用法

```bash
# 1. 应用补丁到工作树（可重复执行，幂等）
XNU_WORK=<xnu-work 路径> python3 ../patch_vNNN.py

# 2. 跑流水线（STEP6 会等设备出现在 fastboot，最多 10 分钟；无设备时可 Ctrl-C，产物已生成）
./vNNN-pipeline.sh

# 3. 刷机（设备进 fastboot 后）
fastboot erase boot && fastboot flash boot <产物目录>/boot.img && fastboot reboot
```

## 探针门禁

流水线里的 `for p in '...'` 一行是**探针字符串门禁**：逐个用
`strings kernel.macho | grep -cF` 校验探针真的链进了镜像，缺一个就判失败。
注意标签是**跨版本累积**的（vm_map.c/sleh.c 里的探针可能仍是 v349/v352 标签），
门禁列表必须与工作树里实际存在的字符串一致。

## auto-grab-flash-latest.sh

设备一出现（fastboot 或 adb）就自动 erase + flash + reboot 的守护。
**注意：bash 逐行读脚本，改完脚本必须 kill 并重启守护进程，改动才生效。**

## 关键经验（2026-11-24 实测）

- `MARK_AS_PMAP_TEXT` 不是空宏（`XNU_MONITOR=1`，定义在
  `pexpert/pexpert/arm64/board_config.h`）：`pmap_switch_internal()` /
  `pmap_switch_user_ttb()` 是 `__PPLTEXT` 段函数，**里面不能调 console 函数**。
- `vm_map.pmap` 是 ptrauth 签名指针：可解引用、不可与 NULL 比较。
- `pmap_destroy()` 会把 `pmap->ttep` 清零；v349 证明崩溃点 pmap 是活的
  （ttep 非零、ASID=1），真正的根因是**根表 2KB 切分未按 granule 对齐**（v354 修复）。
- 诊断探针放 `pmap_switch_user()`（普通段）；FAR/ESR/PC 从
  `sleh_synchronous_sp1()` 抓。
