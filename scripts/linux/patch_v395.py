#!/usr/bin/env python3
"""g0245d v395: remove v394's unaligned UPIU byte access.

v394 boot photo (2026-11-27 09:43) showed no v394 pinned row; instead:

    Unaligned kernel data abort. at pc 0xfffffff007b06914
    v329 pc 0xfffffff007b12f08 (panic_with_thread_kernel_state)

Symbolising pc against the exact v394 kernel.macho gives:

    fffffff007b0685c <v394QueryDevice>:
    fffffff007b06914: b800a049   stur   w9, [x2, #0xa]

That is the compiler merging `ucd[10] = 0; ucd[11] = 64;` (plus the
following query opcode bytes) into one 32-bit store at offset 10, which is
not 4-byte aligned.  The UCD is an uncached MMU mapping, so ARM64 alignment
checking faults immediately.

v395 changes exactly one suspect point: force every UPIU header byte store
and every UPIU response byte read through a `volatile uint8_t *`, so the
compiler must emit byte accesses instead of merging them.  UTRD setup, MMIO
registers, UIC commands, clocks and PHY are untouched.

The pinned row keeps the same value layout but is relabelled:

    v395 o=0 r=00 a=0000 b=0000 d=00 s=9

Idempotent via "g0245d v395" markers.
"""
import os
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
DEV = Path(os.environ.get(
    "G0245D_DEV",
    str(Path(__file__).resolve().parents[2]),
))
CPP = DEV / "drivers" / "NativeUfs8996" / "NativeUfs8996.cpp"
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
for f in (CPP, BSD):
    if not f.is_file():
        sys.exit("required file not found: %s" % f)

# ------------------------------------------------------------------ driver
src = CPP.read_text(encoding="utf-8")
if "g0245d v395" not in src:
    write_anchor = """  // Query Request UPIU header (network byte order).
  ucd[0] = 1u;                       // task tag
  ucd[1] = 0u;                       // LUN
  ucd[2] = 0u;                       // flags: no data
  ucd[3] = 0x16u;                    // QUERY REQUEST
  ucd[5] = 0x01u;                    // standard read request
  ucd[10] = 0u; ucd[11] = 64u;       // data segment length
  // Query Request fields at offset 12.
  ucd[12] = 0x01u;                   // READ_DESC
  ucd[13] = 0x00u;                   // DEVICE descriptor
  ucd[14] = 0u; ucd[15] = 0u;
  ucd[18] = 0u; ucd[19] = 64u;       // descriptor buffer length
"""
    write_new = """  // g0245d v395: the UCD is an uncached MMU mapping.  v394's adjacent
  // byte writes at ucd[10..13] were merged into `stur w9, [x2, #0xa]`,
  // an unaligned 32-bit store that faulted at pc 0xfffffff007b06914.
  // A volatile byte pointer forbids the merge; every access stays 1 byte.
  volatile uint8_t *v395_ucd = ucd;
  v395_ucd[0] = 1u;                  // task tag
  v395_ucd[1] = 0u;                  // LUN
  v395_ucd[2] = 0u;                  // flags: no data
  v395_ucd[3] = 0x16u;               // QUERY REQUEST
  v395_ucd[5] = 0x01u;               // standard read request
  v395_ucd[10] = 0u;                 // data segment length (hi)
  v395_ucd[11] = 64u;                // data segment length (lo)
  v395_ucd[12] = 0x01u;              // READ_DESC
  v395_ucd[13] = 0x00u;              // DEVICE descriptor
  v395_ucd[14] = 0u;
  v395_ucd[15] = 0u;
  v395_ucd[18] = 0u;                 // descriptor buffer length (hi)
  v395_ucd[19] = 64u;                // descriptor buffer length (lo)
"""
    n = src.count(write_anchor)
    if n != 1:
        sys.exit("patch_v395: UPIU write anchor found %d times" % n)

    read_anchor = """  out.response = ucd[512 + 5];
  out.data_len = ((uint32_t)ucd[512 + 10] << 8) | ucd[512 + 11];
  out.bytes01 = ((uint32_t)ucd[512 + 32] << 8) | ucd[512 + 33];
  out.bytes23 = ((uint32_t)ucd[512 + 34] << 8) | ucd[512 + 35];
"""
    read_new = """  // g0245d v395: same no-merge rule for response bytes.
  out.response = v395_ucd[512 + 5];
  out.data_len =
      ((uint32_t)v395_ucd[512 + 10] << 8) | v395_ucd[512 + 11];
  out.bytes01 =
      ((uint32_t)v395_ucd[512 + 32] << 8) | v395_ucd[512 + 33];
  out.bytes23 =
      ((uint32_t)v395_ucd[512 + 34] << 8) | v395_ucd[512 + 35];
"""
    m = src.count(read_anchor)
    if m != 1:
        sys.exit("patch_v395: UPIU read anchor found %d times" % m)

    src = src.replace(write_anchor, write_new, 1)
    src = src.replace(read_anchor, read_new, 1)
    CPP.write_text(src, encoding="utf-8")
    print("patch_v395: volatile UPIU byte accesses installed")
else:
    print("patch_v395: driver already patched -- skip")

# ------------------------------------------------------------- bsd_init.c
bs = BSD.read_text(encoding="utf-8")
if "g0245d v395" not in bs:
    anchor = 'static char v394_buf[] = "v394 o=0 r=00 a=0000 b=0000 d=00 s=9";'
    n = bs.count(anchor)
    if n != 1:
        sys.exit("patch_v395: v394 row anchor found %d times" % n)
    bs = bs.replace(
        anchor,
        '/* g0245d v395: same row, relabelled after the alignment fix. */\n'
        '\t\tstatic char v394_buf[] =\n'
        '\t\t    "v395 o=0 r=00 a=0000 b=0000 d=00 s=9";',
        1,
    )
    BSD.write_text(bs, encoding="utf-8")
    print("patch_v395: bsdinit pinned row relabelled v395")
else:
    print("patch_v395: bsd_init.c already patched -- skip")

print("patch_v395: done")
