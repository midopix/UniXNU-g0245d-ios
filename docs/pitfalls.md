# Build and flash pitfalls

> 中文摘要：这一页是本板移植过程中真实踩到并已修掉的坑，按"症状 → 根因 → 做法"记。
> 主要集中四类：工具链标签在四个地方各写一遍、EDK2 的 `cp -p` 在受限环境假失败、
> FD 被 LZMA 包起来导致 `strings` 永远搜不到新代码、以及没有 root 时怎么把依赖装到用户目录。

Each entry is a failure that actually happened on this port, with the fix. Commands are
for a Linux host.

## Toolchain

**Four places pin the toolchain tag, and only one of them wins.**
`switch-toolchain-linux.sh` edits three files, but `Platforms/Gree/g0245dPkg/DeviceBuild.py:166`
sets `TOOL_CHAIN_TAG` itself and overrides `Conf/target.txt`. Editing only `target.txt`
produces a build under `RELEASE_CLANGDWARF` while the packaging step reads
`RELEASE_CLANGPDB`, which looks like a failed build with a fresh timestamp. This port
uses `CLANGPDB` everywhere, matching v90 through v97.

`CLANGPDB` is also the only tag that works here: switching to `CLANGDWARF` trips
`RamManagerDxe`'s `-Werror,-Wsometimes-uninitialized` under clang 21.

**`cp -p` fails the build with `error 7000`.** EDK2 calls `cp -p` and the sandbox
refuses `utimensat`, so the copy succeeds but the command reports failure. Put a
wrapper early on `PATH` that strips `-p`. In this tree that is `workspace/tmp/bin/cp`,
added by `env.sh`.

**`mu_nasm` needs Mono.** The NuGet package is fetched by `DeviceBuild.py --update`;
without `mono-devel` the extraction dies. `apt-get install mono-devel` and rerun the
update.

## Verifying the firmware volume

**`strings` on `SILICIUM_UEFI.fd` can never find new C code.** `FVMAIN` is wrapped in
`FVMAIN_COMPACT` as an `EFI_SECTION_GUID_DEFINED` with GUID
`EE4E5898-3914-4259-9D6E-DC7BD79403CF` (LZMA), so the `.fd` holds compressed bytes
only. The working chain:

1. the top-level FV has exactly one `FV_IMAGE` FFS (`9E21FD93-9C72-4C15-8C4B-E77F1DB2D792`);
2. its section is GUIDed, `DataOffset` comes from the `u16` at `+20`;
3. `lzma.decompress(payload, format=lzma.FORMAT_ALONE)` yields the inner FV, whose first
   8 bytes are a leftover tail — locate the header by searching for `_FVH` instead of
   assuming offset 0;
4. the inner FV has an extension header: `HeaderLength=0x48` but `ExtHeaderOffset=0x60`,
   so the FFS area starts at `align(0x60 + u16@0x60, 8) = 0x4ce8`, not `0x48`.

Three parsing traps, all hit:

- **The FFS size lives at offset 20**: `Name[16] + IntegrityCheck[2] + Type@18 +
  Attributes@19 + Size@20..22 + State@23`. Reading offset 19 yields a nonsense size and
  the walk derails immediately.
- The inner FV contains free and erased blocks, so **a sequential walk goes wrong after
  the first bad entry**. Scan for the target GUID on 8-byte alignment and validate
  `Type` and the size instead.
- **`GenFds` does not always update the `.fd` mtime.** v99 finished building at 16:02 and
  the `.fd` mtime stayed at 15:59. Never judge freshness by mtime: decompress and compare
  content.

`scripts/linux/verify-fd-unixnu.py <FD> [--efi <UniXNU.efi>] [--dump out.efi]` implements
this chain; it exits non-zero unless the PE32 inside the FV matches the build output byte
for byte.

## Packaging and flashing

**`finish-build.sh` parsed only `$2`.** `finish-build.sh v99 --allow-same-fd --no-flash`
fell through to "run everything" and then called a non-existent
`tools/flash/auto-flash-watch.sh`, failing with 127 after a successful pack. The script now
walks `"$@"`.

**`pack-boot-linux.sh` defaulted the mode to a literal `--`.** `MODE="${2:---}"` produced
the string `--` instead of an empty default. Fixed.

**Two builds of identical sources produce different image md5s,** because
`SOURCE_DATE_EPOCH` is unset and the build stamps the current time. Compare the FD content,
not the md5, and let the flash script pin the md5 it expects rather than comparing two
builds against each other.

**`avb footer` warning on `fastboot boot` is normal.** This aboot prints it and proceeds.

## Vendor inputs

**`Binaries/g0245d` is a submodule, so a source-only checkout cannot build.** The build
stops at `SPMI.inf is not found`. Restore the vendor DXE images from the QFIL package into
`Binaries/g0245d` before building; `proprietary-files.txt` lists them by hash and they are
kept out of Git.

## Host dependencies without root

`sudo` fails in a restricted sandbox with `The "no new privileges" flag is set`, so apt
cannot be used directly. `apt-get download` does not need root:

```sh
cd /tmp && apt-get download flex bison tcsh libclang-21-dev libbsd-dev libssl-dev
```

**`dpkg -x` exits early on `utime` errors and silently loses the tail of the package.**
It died on `tar: ./usr/bin/bison: cannot utime` and left `bsd/unistd.h` missing. Extract
by hand instead:

```sh
ar x pkg.deb && unzstd -c data.tar.zst | tar -xmf - -C "$PREFIX"
```

`tar -m` (touch) skips mtime restoration, which is what avoids `utimensat`. Ubuntu 26.04
packages are `data.tar.zst`; older ones are `.xz`.

**The `libclang` probe needs three merged include trees.** `setup-toolchain.py --check`
compiles `clang-c/Index.h`, `bsd/unistd.h`, `uuid/uuid.h`, `openssl/ssl.h` and `zlib.h` and
links `-lclang -lbsd -luuid -lssl -lz`, with `-I/-L` pointing only at
`llvm-config --includedir/--libdir`. The system `llvm-config` ships `llvm/ llvm-c/`, the
`libclang-21-dev` package ships `clang/ clang-c/`, `bsd/` and `openssl/opensslconf.h` live
in the multiarch subdirectory, and `-lbsd` pulls `-lmd`. A `llvm-config` wrapper that
overrides only `--libdir/--includedir` plus symlinks for every library resolves it.

**`lzfse` is not packaged for a no-root install.** Build the pinned commit instead;
cmake 4 rejects the 2.x `cmake_minimum_required`, so pass
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5`.

## Downloads

**`unixnu fetch` fails with `git failed (128)` while every submodule actually succeeded.**
The log shows all 19 checkouts and then `error: waitpid for git-submodule failed`. The
parallel spawn does not work in this sandbox. Inject serial fetching for the single command
rather than editing any config:

```sh
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=submodule.fetchJobs GIT_CONFIG_VALUE_0=1
```

**`unixnu ipsw fetch` stalls on remote range reads.** It reached 3.08 GB with no progress
for eight minutes and has no timeout. Download the whole IPSW with `curl -C -` and pass
`--ipsw <local file>`; the extraction step then runs locally. The kernel materials alone
only need ~16 MB of range reads, so the whole file is only worth it for the two system
volumes.

**The documented `./unixnu payload` route does not produce a payload here.** Chasing
`[payload] tools = true` (https://unixnu.com/zh/porting/log-capture) stops twice:

```
$ ./unixnu payload --device ../UniXNU-g0245d --uefi ../uefi-g0245d
unixnu: kernel not found: .../kernel/kernel.macho; run "unixnu build kernel" or pass --kernel FILE
$ ... --kernel out/ipsw/21H461/kernelcache.decompressed --unique-chip-id 0123456789ABCDEF
unixnu: arm-io needs a non-zero base: an exported register lies below 16 MiB
```

The second is structural, not a porting bug: `scripts/unixnu/devicetree.py:192`
(`arm_io_window`) rounds the lowest exported register down to a 16 MiB boundary and
rejects `base == 0`, and MSM8996 keeps a large part of its peripheral space below
16 MiB (UFS at `0x624000`, BLSP1 at `0x75xxxx`, MDSS at `0x900000`). Every SoC the
upstream guide targets keeps peripherals above `0x1000000`.

It is also unnecessary. `UniXNULib/Config.c`'s `mBuiltinConfig` already lists the
Tools entry (`timeout = 10 / Return to firmware / Restart / Power off / Tools`), so
the menu shows Tools with no payload volume at all; the volume only replaces that
built-in menu. What was missing is the plugin behind Tools, and that is
`UniXNUPkg/Driver/AdvancedLogDxe` — it needs the Advanced Logger buffer, not a
payload. v101 wires the buffer (see uefi-g0245d `docs/advanced-logger.md`).

**`arm_io_window()`'s non-zero base assertion is wrong for MSM8996.** The packer
refused to build a payload because UFS sits at `0x624000`. XNU reads the SoC base
from arm-io's `ranges` parent address (`pexpert/arm/pe_identify_machine.c`,
`pe_arm_get_soc_base_phys`), and `0` is a legal value there: `gPicBase = soc_phys
+ offset` then yields the absolute physical address, which is exactly right for a
SoC whose address space starts at 0. The assertion conflated "window starts at 0"
with "no window found". Patch `patches/unixnu/0003-linux-host-without-root.patch`
drops it; `unixnu payload` then produces a 192 MiB `payload.img`.

**BootShim's ARM64 `image_size` must cover the shim itself.** `BootShim.S` wrote
`FD_SIZE`, so `unixnu bootimg` rejected the image ("the ARM64 image header does
not describe the shim plus the firmware volume"). aboot ignores the field, which
is why the local packer never noticed. The value must be `shim length + FD_SIZE`;
use a label difference `(_Payload - _Head)`, because an absolute `_Payload`
reference needs a relocation that `llvm-objcopy -O binary` cannot apply.
Patch: `uefi-g0245d/patches/mu/0002-bootshim-image-size.patch`.

## Framebuffer console

**A linear ring shown linearly is not a terminal.** `g0245d_con_putc()` wrapped its
cursor at `g0245d_con_nscroll` and overwrote rows in place, so once the ring turned
over the panel held the newest lines on top and stale lines below them. A boot log
then looks like two log fragments stitched together: v232's photo reads `42..63`,
then `32 sched_init .. 41 coalitions_init` underneath. Rotating the glyphs inside a
row (v231's 300 px fix) cannot repair that — it is an ordering bug, not a geometry
bug. Clear the ring when the cursor wraps, or scroll the display window; do not
blame the panel.

**Read the sequence number, never the screen order.** Every `g0245d_trace()` line
starts with a monotonic counter precisely so a wrapped ring stays readable. If the
numbers jump backwards, the ring turned over — it is not a second counter and not
a lost line.

**`early_random calls 0xNNN` is a heartbeat, not a loop.** `zalloc_random_mask64()`
is `early_random() & mask` on arm64, so every zone allocation bumps it. A single
number that stops climbing bounds how many allocations happened after the last
print; it does not mean the CPU is spinning.

## Build / instrumentation

**An `extern` declaration placed next to a `#include` may be inside a
conditionally compiled block.** Adding `extern "C" void g0245d_trace(...)` right
after `#include <ptrauth.h>` in `libkern/c++/OSRuntime.cpp` produced eleven
`use of undeclared identifier` errors: that include lives inside
`#if defined(HAS_APPLE_PAC)`, and this target builds without PAC, so the whole
block — declarations included — was compiled out. Put instrumentation
declarations above the conditional, and when a declaration "disappears", check
which `#if` it landed in before doubting the linker.

**A stripped kernel still names its own static constructors.** `llvm-nm` on
`kernel.macho` is enough to resolve every entry of `__mod_init_func`, so a probe
that prints the *index* of the constructor it is about to call can be turned
into a file name offline (`scripts/structor_map.py`). 98 entries here: 96 in
`__DATA_CONST`, then `_last_kernel_constructor`, then `bootstrap.cpp`.

## Constructors and section walks

**`_last_kernel_constructor` is a label, not a function.** It lives in
`__LASTDATA_CONST,__mod_init_func` and its address lands *inside*
`___llvm_profile_set_timestamp`, so `(*structor)()` on it executes a fragment of
profiling code that can return, or can store through whatever happens to be in
`x0`. Never read it as "a constructor that succeeded" — the machine reached the
next entry *despite* it, not because of it.

**Three `structors section` lines in one boot are correct.** The kernel has three
segments carrying `__mod_init_func`: `__DATA_CONST` (96 entries),
`__LASTDATA_CONST` (1) and `__KLDDATA` (1) — 98 in total, indices 0..97.
`OSRuntimeCallStructorsInSection()` prints once per segment it actually enters,
and `break`s after the first matching section inside the segment, so the count of
those lines is the count of segments, not a duplicated instrumentation.

**A four-instruction constructor cannot hang.** `__GLOBAL__sub_I_bootstrap.cpp`
is two `adr` + two `str` + `ret`: clang proved `this == &sBootstrapObject`, so the
`panic()` guard in `KLDBootstrap::KLDBootstrap()` is dead code and never emitted.
When the probe row names the *last* entry and the log stops there, the stop is
after the call, not inside it — bracket the call and the statements that follow
before rewriting the constructor.

## Two log channels that disagree

**Do the wrap arithmetic before believing either channel.** v235's panel showed
a pinned row that decodes to the last entry of `__mod_init_func` together with a
scrolling ring holding only the first two lines of the segment walk. Program
order says those cannot both be true: reaching the third section prints at least
eight more lines. The arithmetic that settles it is `nscroll = rows - 3 = 32`, so
a line sitting at row 0 is a wrap line, and the wrap line two lines back was
`71 - 32 = 39`; rows 0 and 1 therefore hold the *newest* output, not the oldest.

**Give the pinned row a sequence number.** A row that says only `97` cannot
distinguish "the walk finished" from "the console stopped advancing". A row that
says `97/98 s72` can: if the sequence is still 72 while the index is 97, the
console is frozen and the walk is fine; if it says `s87`, the screen is stale and
the device rebooted. Print the counter that the other channel increments.

## Instrumentation placement

**When only the first of two adjacent traces appears, the stop is between
them.** v236 printed `v234 structors done` and then nothing, while the very
next statement was `g0245d_trace_u("v236 walk done i", ...)`. That reduces the
search to one call, but it does not say which side of it died. Split them: put
a plain, known-good trace first and leave the suspect one last as a canary.
Getting the same treatment for free: every pairing added to `postModLoad()`
(`enter`/`done`, `dict enter`/`dict ok`, per-class counter on a pinned row) is
worth more than one clever guess about where a kernel hangs.

**A segment walk is verifiable offline.** `nextsegfromheader()` iterates
`LC_SEGMENT_64` load commands in order, so printing one line per segment and
then comparing the list with the Mach-O's own load commands proves whether the
walk finished or stopped early. Here the panel showed 12 segment lines and the
header has 18 segments, ordered `__TEXT, __DATA_CONST, __TEXT_EXEC, __KLD,
__LASTDATA_CONST, __LAST, __KLDDATA, __DATA, __BOOTDATA, __PRELINK_TEXT, ...,
__LINKINFO, __LINKEDIT`, so the visible run was exactly segments 6..17, i.e.
the last one was reached. Without that checksum "twelve lines" looks like a
partial walk.

**Anchor a patch on code, never on the first line of a block comment.**
Inserting a statement after `/* Scan the header for all destructor sections, in
any` produced `expected ';' after expression` hundreds of lines away: the
insertion landed between the comment's opening line and its continuation, so
`/* g0245d v237: ... */` became part of the comment and the `for` loop after it
lost its opening brace context. Anchor on the loop head or on a closing brace.

**A `%u`-taking trace needs the same re-arm path as the plain one.** v236 gave
`g0245d_trace()` a "console was disarmed, take it back" guard but left
`g0245d_trace_u()` calling `g0245d_con_printf()` directly, which returns
silently when the ready flag is clear. Two log functions with different
liveness rules is a trap: a missing line then means "this particular function"
rather than "the kernel stopped". Put the guard in the lowest layer
(`con_printf`) so every caller inherits it.

## Narrowing a silent stop

**Eliminate by data-structure state, not by intuition.** `OSMetaClass::postModLoad()`
does two passes over the stalled class array; the duplicate check in pass 1 calls
`sAllClassesDict->getObject(...)`, and `sAllClassesDict` is only populated in
pass 2. So during pass 1 the lookup is a lookup in an *empty* dictionary: it
cannot block, cannot allocate, cannot log. Reading the code around the call site
was not enough to see that -- reading the two loops together was. When a
candidate "obviously can hang", check whether it has anything to do at all.

**The only loop that can vanish silently is one that neither allocates nor
prints.** Every earlier stop in this bring-up left a breadcrumb, because
`early_random()` fires from `zalloc` and the trace calls print. A loop that
walks a linked list with `while ((p = p->next)) depth++;` does neither, so a
cycle in the list is indistinguishable from a dead CPU -- except that the pinned
row stops on one index. Bound such loops and print the step counter on the pinned
row; then the depth itself measures the cycle.

**A class count is not a constructor count.** 98 `__mod_init_func` entries and
`sStalled->count > 166` are both correct: constructors are per translation unit,
and one `.cpp` usually registers several `gMetaClass` objects. Comparing the two
numbers as if they should match costs a round.

## Patch placement, third variant

Inserting after `finish:` and before a block comment put the probe *inside* the
comment (`/* Don't call logError() ... */`), where it compiles cleanly and never
runs. Two builds earlier the same helper put a probe inside a comment's first
line and broke the file. Both are the same mistake: the anchor was a comment,
not code. Anchor on a statement that survives preprocessing, and after applying a
patch, `grep` the new string in the source to confirm it is not commented out.

## Prelinked symbols that point nowhere

**An `A` symbol can name an address that no segment covers.** `llvm-nm` printed
`__ZN16IOAESAccelerator10gMetaClassE` with type `A` at `0xfffffff006ae52d0`,
while this kernel's `__TEXT` starts at `0xfffffff007004000` and its
`__PRELINK_TEXT` has `vmsize = 0`. The symbol is a leftover from a prelinked
kext that was never linked into the image (the build skips prelink), so the
address is real to the linker and unmapped to the MMU. Dereferencing it is a
data abort, and with no exception vectors installed that is indistinguishable
from a hang: no output at all.

**Check the three things in this order** when a pointer dereference kills the
machine silently: the literal that produced it
(`llvm-objdump --disassemble` shows `ldr x2, <pool>` and the pool entry is the
8 bytes at that address), the symbol at its value (`llvm-nm -n` and take the
nearest symbol *at or below*), and whether that value falls inside any
`LC_SEGMENT_64` range from the Mach-O header. Two of the three are not enough:
a plausible-looking `0xfffffff0...` pointer passes every hand-written range test.

**Deriving a superclass pointer is not worth a hang.** `sDeepestClass` exists
only to size arrays in `applyToInstances()`; the walk that computes it
(`while ((p = p->superClassLink)) depth++`) touches every link in the chain, so
one bad link kills the boot for a statistic nobody reads. When instrumenting a
bring-up, ask what the value is *used for* before walking to compute it.

**The last element of a linked set is a fine suspect.** Here index 166 of 167
was the only class descending from a prelinked base class, which is exactly why
the loop survived 166 iterations and died on the last one. "It got through 166
elements, so the data is fine" is the wrong inference -- element order is link
order, and the pathological one is wherever its object file happened to land.
