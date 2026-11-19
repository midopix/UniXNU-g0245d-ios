#!/usr/bin/env python3
"""解码 G0245D 固件 CrashLogDxe 写到 userdata 尾部的 CRSH 崩溃记录。

用法:
  python3 linux/decode-crashlog.py <dump.bin>          # dump = 从 userdata 尾部读回的 64KiB
  python3 linux/decode-crashlog.py <dump.bin> --scan   # 在整个 dump 里搜 CRSH magic（偏移未知时）

结构对应 CrashLogDxe.c 的 CRASH_RECORD（小端，自然对齐，无 packed）：
  UINT32 Magic/Version/RegionBlocks/BlockSize; UINT64 WriteLba; ...
"""
import argparse
import struct
import sys

MAGIC = 0x48535243  # 'CRSH'

# 手工按字段算偏移（对齐到自然边界），与 C struct 布局一致
FIELDS = [
    ('Magic', 'I'), ('Version', 'I'), ('RegionBlocks', 'I'), ('BlockSize', 'I'),
    ('WriteLba', 'Q'), ('ExceptionType', 'I'), ('Reserved0', 'I'), ('Timestamp', 'Q'),
]
OFF = {}
o = 0
for name, fmt in FIELDS:
    size = struct.calcsize('<' + fmt)
    align = size
    o = (o + align - 1) // align * align
    OFF[name] = o
    o += size
# X[0..28]
X_OFF = o
o += 8 * 29
FP_OFF, LR_OFF, SP_OFF = o, o + 8, o + 16
ELR_OFF, SPSR_OFF, FPSR_OFF, ESR_OFF, FAR_OFF = o + 24, o + 32, o + 40, o + 48, o + 56
o += 64
BT_COUNT_OFF, RES1_OFF = o, o + 4
o += 8
BT_OFF = o
o += 8 * 32
IMG_COUNT_OFF, RES2_OFF = o, o + 4
o += 8
# CRASH_IMAGE = {UINT64 Base; UINT64 Size; CHAR16 Path[64]} = 8+8+128 = 144
IMG_OFF = o
o += 144 * 32
LOG_SIZE_OFF = o
o += 4
LOG_OFF = o
REC_SIZE = o + 1536

EXC_NAMES = {
    0: 'ARM64_AArch64', 1: 'ARM64_AArch32', 2: 'ARM64_SError',
    3: 'ARM64_FIQ', 6: 'ARM64_IRQ',
}


def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def decode(buf, base=0):
    try:
        magic = u32(buf, base)
    except struct.error:
        return None
    if magic != MAGIC:
        return None
    rec = {}
    rec['version'] = u32(buf, base + OFF['Version'])
    rec['region_blocks'] = u32(buf, base + OFF['RegionBlocks'])
    rec['block_size'] = u32(buf, base + OFF['BlockSize'])
    rec['write_lba'] = u64(buf, base + OFF['WriteLba'])
    rec['exception'] = u32(buf, base + OFF['ExceptionType'])
    rec['elr'] = u64(buf, base + ELR_OFF)
    rec['spsr'] = u64(buf, base + SPSR_OFF)
    rec['esr'] = u64(buf, base + ESR_OFF)
    rec['far'] = u64(buf, base + FAR_OFF)
    rec['sp'] = u64(buf, base + SP_OFF)
    rec['lr'] = u64(buf, base + LR_OFF)
    bt_count = min(u32(buf, base + BT_COUNT_OFF), 32)
    rec['backtrace'] = [u64(buf, base + BT_OFF + 8 * i) for i in range(bt_count)]
    img_count = min(u32(buf, base + IMG_COUNT_OFF), 32)
    imgs = []
    for i in range(img_count):
        p = base + IMG_OFF + 144 * i
        ibase, isize = u64(buf, p), u64(buf, p + 8)
        path = buf[p + 16:p + 144].decode('utf-16-le', 'replace').split('\0', 1)[0]
        imgs.append((ibase, isize, path))
    rec['images'] = imgs
    log_size = u32(buf, base + LOG_SIZE_OFF)
    log_size = min(log_size, 1536)
    rec['log'] = buf[base + LOG_OFF:base + LOG_OFF + log_size].decode('utf-8', 'replace').rstrip('\0')
    return rec


def show(rec, label):
    print(f"=== {label} ===")
    print(f"  version      : {rec['version']}")
    print(f"  exception    : {rec['exception']} ({EXC_NAMES.get(rec['exception'], '?')})")
    print(f"  ELR          : 0x{rec['elr']:016x}")
    print(f"  ESR          : 0x{rec['esr']:016x}   FAR: 0x{rec['far']:016x}")
    print(f"  SPSR         : 0x{rec['spsr']:016x}   SP: 0x{rec['sp']:016x}  LR: 0x{rec['lr']:016x}")
    print(f"  write LBA    : 0x{rec['write_lba']:x}  block={rec['block_size']}  region_blocks={rec['region_blocks']}")
    if rec['backtrace']:
        print("  backtrace    :")
        for i, a in enumerate(rec['backtrace']):
            print(f"    #{i:02d} 0x{a:016x}")
    if rec['images']:
        print("  images       :")
        for ib, sz, path in rec['images']:
            print(f"    0x{ib:016x} +0x{sz:x}  {path}")
    if rec['log']:
        print("  log          :")
        for line in rec['log'].splitlines():
            print("    | " + line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dump')
    ap.add_argument('--scan', action='store_true', help='dump 里全量搜索 CRSH magic')
    args = ap.parse_args()
    data = open(args.dump, 'rb').read()
    print(f"dump: {args.dump}  ({len(data)} bytes)")

    offsets = []
    if args.scan:
        i = 0
        while True:
            i = data.find(b'CRSH', i)
            if i < 0:
                break
            offsets.append(i)
            i += 4
    else:
        offsets = [0]

    found = False
    for off in offsets:
        rec = decode(data, off)
        if rec is None:
            continue
        found = True
        show(rec, f"CRSH @ 0x{off:x}")
    if not found:
        print("未发现有效 CRSH 记录。")
        print("  可能原因：固件没跑到 CrashLogDxe（白条=ABL遗留），或 userdata 尾部尚未被写过。")
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
