# strip 回归警示（2026-11-28 21:10）

v457prb/v458prb 是坏镜像（md5 1d5603b4… / f85b63fb… 作废）：
payload 步骤用 `PATH=/usr/bin:/bin` 绕开工具链 clang 的 ptrauth 问题，
导致 `strip` 落到 GNU strip（不认 Mach-O）→ staged kernel 未剥离 19.5MB
→ unixnu.toml 越过设备 FAT 读取器 18MiB 边界（HANDOFF 14.55 已知问题）
→ 设备上 `config error: unixnu.toml line 1: expected a key`
→ UEFI 回退内置菜单，**内核不启动**。

正确做法见 `run-v459-460prb2.sh`：shim 目录同时放
`clang→/usr/bin/clang` 与 `strip→cctools strip`，`PATH=$SHIM:/usr/bin:/bin`，
并执行四重硬 gate（stripped 日志 / FAT 内 kernel<17MB / patch log / toml 可读）。

任何让 staged kernel 变大的改动都可能复发 FAT 18MiB 边界问题——
交付前必须 mcopy 校验 FAT 内 kernel.macho 尺寸。
