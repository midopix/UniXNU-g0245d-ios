# Runtime overlays — local fixes in /home/myth/UniXNU-runtime

These are patches of local modifications we made to the UniXNU runtime tree
(`/home/myth/UniXNU-runtime`, a clone of UniXNU/UniXNU). The runtime repo has
no push access (it is the upstream), so the fixes are recorded here.

Apply with `git apply <patch>` from the runtime tree root.

## build-xnu-4k-baseline-boot-progress.patch
Two fixes, both needed to make the official boot-progress component actually
compile into the G0245D kernel (v455bp/v456bp work):

1. **UFS interlock relaxation** — G0245D is an eMMC/NonShengUfs board, so the
   strict `XNU_NATIVE_UFS` interlock that gates `XNU_BOOT_PROGRESS` was relaxed,
   following the sirius board baseline.
2. **CFLAGS delivery fix** — the baseline script passed
   `-DXNU_BOOT_PROGRESS=$BOOT_PROGRESS` via `CFLAGS_EXTRA="$EXTRA_CFLAGS"`,
   but the XNU makefiles never consume `CFLAGS_EXTRA`. Every personality macro
   in the script uses the `<obj>.o_CFLAGS_ADD=` make-override channel instead.
   `-DXNU_BOOT_PROGRESS=1` is now appended to the existing
   `bsd_init.o_CFLAGS_ADD` / `kern_exec.o_CFLAGS_ADD` / `startup.o_CFLAGS_ADD`
   definitions and added for `arm_init.o`, `kern_exit.o`, `video_console.o`.
   Without this the boot_progress call sites compile to `((void)0)` empty
   macros even with `CONFIG_XNU_BOOT_PROGRESS=y` in .config.

Also note: after changing CFLAGS, delete the previously compiled objects of the
affected files — make does not track CFLAGS changes, so incremental builds
silently reuse objects compiled with `XNU_BOOT_PROGRESS=0`.

## patch-xnu-entry-probe-g0245d-mmu-adapt.patch
The official `patch-xnu-entry-probe.py` hard-codes the SCTLR→ISB→MOV→CPACR
entry sequence at offsets +0x20/+0x24. On iOS 16.5 / XNU 8796 (G0245D), a
TTBR/TCR page-table setup block is inserted between SCTLR and the
MOV/CPACR pair, shifting them to +0x68/+0x6c, so the tool rejected the kernel
with `Require one verified SCTLR/ISB/CPACR entry sequence`. The patch widens
the MOV/CPACR search to a bounded window while keeping all strict checks
(`msr SCTLR_EL1, x0` is unique in the kernel, instructions verified).

Verified on the v456bp kernel: stage-3 (MMU-off) probe, stage-4
(`--reset-before/--reset-after _arm_vm_init --in _arm_init`) probe and
`--panic-screen` all apply; panic screen together with any reset cave exceeds
the padding (use panic screen alone with `--no-reset`).

## payload-strip-best-effort-v414.patch
`payload.py` unconditionally stripped the staged kernel; for a fully
prelinked candidate cctools strip rejects the layout. Make strip best-effort
and keep the kernel intact (v414-era fix).

## components-toml-nativeufs8996-output-path.patch
NativeUfs8996 component output dir rename
`build/nativeufs8996` → `build/native-ufs-8996` (v413-era fix).

## Probe images produced with these overlays (not committed, 56 MB each)

| image | md5 | purpose |
|---|---|---|
| v456bp | `c04936e276c0969eede5e0b1c2a97a47` | boot-progress instrumented kernel (flashed 20:04:07) |
| v457prb | `1d5603b425acafc80af09d4021fdd996` | panic screen (`--no-reset --panic-screen`) |
| v458prb | `f85b63fb0490ad11f04bee77f22860cd` | stage-4 reset probe after `_arm_vm_init` |
