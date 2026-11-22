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

## Reading a clearing ring

**Absence of a line is not evidence that the code did not run.** The ring holds
32 rows and clears on wrap, so a boot that is now at `175 v232 InitIOKit done`
has already scrolled `pml enter` and the whole 167-entry pass 2 off the top.
Before concluding "postModLoad never finished", check whether its own follow-on
traces (`ConfigureIOKit done`) are in the *tail* -- they are the ones that should
be there. The failure signature is always "the next expected line is missing
while the preceding one is present", never "these lines are absent from the
screen".

**Sequence numbers let you reconstruct what scrolled away.** `167..175` in a
32-row ring that clears on wrap means the ring wrapped at `167 - 32 = 135`, so
the visible window is contiguous and nothing was lost in the middle. That is a
two-line check that turns a photograph into a monotonic log.

## Instrument the caller and the callee separately

`ConfigureIOKit()` is `assert(gRootNub != NULL); gRootNub->configureDefaults();`.
A stop between those two has three very different explanations -- a failed
assert whose panic never reached the panel, a bad vtable, or something inside
the callee -- and one trace before the assert, one after it, and one after the
call separates them without another round trip. Whenever a stop is "somewhere in
this call", bracket the call *and* the statements around it.

## Read the shipped device tree before instrumenting a device-tree consumer

`dtc -I dtb -O dts device-tree/hardware.dtb` takes a second and lists the five
top-level nodes this platform ships (`cpus`, `psci`, `timer`, `soc`,
`reserved-memory`). That immediately predicts the behaviour of
`IOPlatformExpertDevice::configureDefaults()`: `fromPath("/options")` returns
NULL, `getProperty("serial-number")` returns NULL, `/chosen` exists but has no
`unique-chip-id`, so the function should be three cheap no-ops. Instrumenting
anyway is still right -- but now the expected trace sequence is known in
advance, and any deviation is the finding.

## The device tree you can dump is not the ADT the kernel sees

`dtc -I dtb -O dts` on the shipped blob showed five top-level nodes and no
`/options`, so `createNVRAM()` "obviously" returns at its first statement. It
did not: the panel printed `options found` and went on to build, init, attach
and start an `IODTNVRAM`. The runtime that loads the kernel adds nodes to the
device tree before handing it over -- `/chosen` *and* `/options` both come from
there. An offline dump predicts the behaviour of the *blob*, not of the *ADT*;
use it to form a hypothesis and let the instrumentation settle it.

## One-bit experiments beat finer instrumentation

When a stop sits inside a two-statement function, the cheapest next build is
not "trace every line" but "delete the call and see whether the next trace
appears". Here `generatePlatformUUID()` contains exactly one risky call
(`IORegistryEntry::fromPath("/chosen")`), so skipping the whole function answers
"is it this function or is it the console?" in one photo. Design the build so
that both answers are informative, and leave the skipped call in a comment with
its reason, so restoring it is one edit.

## A half-drawn line means the flush did not finish

A console line whose glyphs survive only as isolated horizontal strokes -- while
the line above it is dim but complete -- was written to the framebuffer and then
lost, because only some cache lines were written back before the machine died.
That is a different signature from "the code after this line never ran": it says
the death is inside the drawing or the `dc civac` flush, not after the next
statement. Read the tail of the ring with that in mind before blaming the code
that was about to execute.

## Trace function pointers when the table has no names

`kernel_startup_initialize_upto()` walks a table of `{ subsystem, rank, func,
arg }` and only logs the subsystem, so a stop inside a subsystem of forty
routines is anonymous. Logging `cur->func` before each call turns every entry
into an address, and `llvm-nm -n kernel.macho` turns the address back into a
file and a symbol -- no need for the table to carry strings.

## The startup table on disk is not in boot order

`__init_entry_set` holds 3917 `{subsystem, rank, func, arg}` records in **link
order**; the boot order only exists after `bootstrap_init()` calls
`qsort(startup_entries, n, ..., startup_entry_cmp)`. Reading the section and
assuming index order gives nonsense (consecutive records had subsystems
`7,1,7,3,16,7,3,…`). To turn a boot index into a name, replay the sort:
parse the section, compile the kernel's own `bsd/kern/qsort.c` on the host
(rename `qsort` with `-Dqsort=bsd_qsort`, drop `sys/kpi_private.h` and
`__private_extern__`), and run the same comparator. `scripts/startup_order.py`
does exactly that; four consecutive addresses from one photograph then matched
the replay exactly, which is what makes the fifth entry trustworthy.

## Never read the last line of a dying console

The final line of a console that dies mid-flush survives as isolated horizontal
strokes: some 64-byte cache lines were written back, the rest were lost. An
address read from such a line looked like `...ae57?` when the truth was
`...aa978`. Two rules follow. First, judge by the *sequence number* plus an
offline table, not by the fuzzy last line. Second, keep the important value
short: `su 8` stays legible where a 38-character address line does not, and
duplicate it on a pinned row that is redrawn whole.

## A NULL function table that nobody registers

`kmem_crypto_init()` is three short statements, yet the machine stopped there
with no output. Both of its crypto calls go through one global pointer:

```c
return g_crypto_funcs->random_kmem_ctx_size_fn();
g_crypto_funcs->random_kmem_init_fn(ctx);
```

The linker put a zero in `__DATA_CONST` for `g_crypto_funcs`, and a full
disassembly of the kernel showed that `register_crypto_functions()` is never
called -- its only mentions are its own symbol and an internal branch. The
registrar lives in a corecrypto kext that this skip-prelink build never links.
When a call site is a single indirect load through a global, check the global's
initial value **and** the number of call sites of the function that sets it.
One `llvm-nm`, one 8-byte read, one disassembly grep: three offline checks that
find the answer without another boot.

## When two independent sources agree, stop investigating

The pinned row read `su 3915 079ade90`, and replaying the kernel's startup sort
said entry #3915 is `_kmem_crypto_init` at exactly `0xfffffff0079ade90`. Two
different channels -- panel text and an offline simulation of `qsort()` on the
Mach-O -- agreed on both the index and the address. That is enough: do not keep
trying to read a fuzzy line or to invent a third explanation. Use the
agreement to move to the *next* question, which here was "what does this
function call?"

## Fix the family, not just the member

`g_crypto_funcs` was NULL and three unrelated-looking boot stages died on it:
`kmem_crypto_init`, then the trust-cache loader, and later still the code
signing paths. Skipping one consumer at a time costs one reboot per consumer.
Once the shared dependency is identified, grep for the other users of the same
global and skip all the non-essential ones in one build. The opposite also
holds: a known landmine that is *about to* be detonated should be removed
before the code path reaches it -- here the `NativeAES` personality in
`KernelConfigTables.cpp` was deleted the same build that first bracketed
`StartIOKitMatching()`, because its superclass pointer was already proven to
be an unmapped prelink symbol.

## Do not assume the screen grab steals your console

`initialize_screen(NULL, kPEAcquireScreen)` sounds like it must take over the
display, but the v244 panel printed `screen init enter` and `screen init done`
and kept working. Bracket a suspicious transition with two traces and let the
panel answer; rewriting the console's framebuffer base beforehand would have
been work for a problem that did not exist. The same applies to `spllo()`:
enabling interrupts did not kill this bring-up either, so both fears were
removed by one photograph instead of two preemptive patches.

## Disassemble before blaming the feature

`machine_lockdown()` on arm64 *looks* like an Apple-security minefield: KTRR,
CTRR, Watchtower, a PPL lockdown and an HMAC invalidation callback. The
compiled function is four instructions: one call to `arm_vm_prot_finalize`, one
optional indirect callback, and `lockdown_done = 1`. Every Apple-specific
block was compiled out. Reading the source alone would have sent us after a
register write that does not exist in the image. A one-screen `llvm-objdump`
settles which of the `#if` branches are real.

## A stack switch and the free of the old stack are one operation

`arm_vm_prot_finalize()` switches SP_EL1 to a fresh exception stack and then
frees the old BOOTDATA pages. Disabling only the switch leaves the kernel
running on pages it has just given back to the VM; disabling only the free
leaks a few pages but is harmless for bring-up. Treat the two as one edit,
keep both under the same `#if 0`, and restore them as a pair.

## Old probes can light up again

After `OSKextRemoveKextBootstrap()` the panel suddenly showed `v234/v235`
constructor traces and a fresh `28/98` on the constructor probe row. That is
not a rewind: tearing down the bootstrap segments runs the C++ constructor
walk a second time, and the instrumentation from twenty builds earlier is
still there. Keep instrumentation idempotent and version-tagged -- old labels
become free evidence when an unrelated late-boot path re-enters the function.

## Skip what the skipped step needed

v246 removed the boot stack switch; its very next call, `cpu_stack_alloc()`,
then became the stop. The two stacks that call allocates exist *only* for the
switch that was just disabled. When removing a mechanism, follow its
dependencies one step in both directions -- the setup right after the removed
step is often the next thing to hang, and often equally unnecessary.

Keep the removed call verbatim under `#if 0` with a comment naming the
mechanism it served. Three builds later it is still obvious why it is off and
what has to be restored together.

## One small change moves the stop, and that is progress

Each version from v242 to v247 removed exactly one suspect and the panel
moved a few lines further: pgz_init, kmem_crypto_init, trust cache, the LOCKDOWN
routines, machine_lockdown's stack switch, cpu_stack_alloc. None of those was
the "real bug" in the sense of a fix to upstream code -- they are all pieces
of an Apple-platform kernel that have no meaning on this SoC. The useful unit
of work here is "prove one more stage is not the wall", not "find the single
root cause".

## Reuse the stage names the kernel already has

`bsd_init()` is 1200 lines, but it calls `bsd_init_kprintf()` at 47 named
points; with `DEBUG_BSDINIT == 0` the macro threw those names away into
`boot_progress_stage()`, which a bring-up console cannot see. Extending the
macro to also feed the framebuffer bought 47 labelled breadcrumbs without
touching the function body. Before instrumenting a large function, look for
an existing stage-log macro, assert helper or progress callback: it already
has the interesting names and call sites picked out.

The helper must truncate at the newline, though: the existing literals end
in `\n`, and passing them straight to a printf-style trace doubles the number
of rows in a 32-row ring.

## The declaration is still too late if it is below the call

One build failed with `call to undeclared function 'g0245d_trace'` because the
new extern was added next to the macro definition, while the first call was
three lines *above* it. This is the same mistake that cost rounds at v229,
v232 and v234; it keeps recurring because each new file has a different
"natural" place to put an extern. The rule that actually works: after adding
a trace call, search the file for that identifier and verify the declaration
appears at a lower line number than every use.

## Same name, different call site

`kperf_init_early()` and `kperf_init()` are different functions at different
points in the boot. The first waits for every advertised CPU and hung here;
the second runs from `ktrace_startup()` (a STARTUP(KTRACE) routine) and had
already completed successfully among the 3917 startup entries. Before
disabling a family of calls, check *each* call site: skipping both here would
have removed working timer initialisation for no reason.

## A wait for "all CPUs" is a bring-up deadlock

`ml_wait_max_cpus()` assumes the platform has already discovered its real CPU
topology. On a bring-up kernel with the boot CPU only but a stale
`machine_info.max_cpus`, it is an infinite wait with no allocation and no
output -- the same silent signature as the prelink and NULL-table faults.
Skipping the consumer gets the boot moving, but the real fix is to correct
where `max_cpus` comes from before any CPU-hotplug path uses it.

## The next trace is not necessarily the next function

After `vfsinit()` the panel showed no further stage name, so it was tempting
to blame `vfsinit()` itself. But between that call and the next labelled
stage there is an entire `#if DEVELOPMENT || DEBUG` block of native probes
(APFS, graphics, iogpu, ...). A "stop after line X" only localises the failure
to everything between X and the next line of output, which can include many
untraced calls. Bracket the whole gap, not just the obvious callee.

## A passing stage rules out a whole family

`bsd calling kmem_suballoc` appeared on the v249 panel, which proves
`kmem_alloc(kernel_map, ...)` works in general. That retroactively explains
the earlier `cpu_stack_alloc()` stop as something specific to its flags or
its lock window, rather than a broken allocator. Keep earlier conclusions provisional: later
breadcrumbs frequently tell you which of two explanations was right without
another experiment.
