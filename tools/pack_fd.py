#!/usr/bin/env python3
"""把新构建的 SILICIUM_UEFI.fd-bootshim 塞进一份已有的 boot.img。

为什么要这样打
--------------
g0245d 的 boot.img（v0 头）kernel 槽的内容是：

    [ gzip(fd-bootshim) ][ 原厂 90 条 DTB 表 ~30.9 MB ]

LK 只认原厂那张 90 条表，而 BootShim+UEFI FD 又必须是被 gzip 压缩的。
所以每换一版 FD，只需要：
  1. 解开旧 img 的 kernel 槽，拿到 gzip 流结束的位置（= 解压时产生的 unused_data）
  2. 新 payload = gzip(新 FD-bootshim) + 旧表的尾部字节（原样保留）
  3. 改 header 的 kernel_size，按 page_size 重新补齐

【重要·2026-11-02 修的 bug】
旧版本只写出 header + kernel 两段，把 ramdisk 和文件尾部的 QCOM 签名整段丢了。
header 里的 ramdisk_size 仍保留原厂值，于是 LK 按 header 找 ramdisk 时越界，
fastboot 直接报 `bootimage: incomplete or not signed`。

原厂 boot.img 的完整布局（page=4096）：
    [ header 4096 ]
    [ kernel : kernel_size，按 page 对齐 ]
    [ ramdisk: ramdisk_size，按 page 对齐 ]
    [ second : second_size，按 page 对齐 ]
    [ extra  : 文件尾部的 QCOM boot signature（X.509 证书，5416 字节）]

本脚本现在按这个布局原样搬运 ramdisk / second / extra，只替换 kernel 段。

用法
----
  pack_fd.py --base <旧 boot.img> --fd <SILICIUM_UEFI.fd-bootshim> \
             --out <新 boot.img> [--gz <现成的 .gz>] [--ramdisk <payload.img>]

不带 --gz 时自己用 gzip 压（mtime=0，保证可复现）。
--ramdisk（2026-11-09 v107 起可选）：把 boot.img 的 ramdisk 槽整体换成
payload.img（UniXNU FAT 卷），并更新 header 的 ramdisk_size。LK 会把它
加载到 ramdisk_offset 并把 initrd-start/end 写进 /chosen，交给
UniXNURamDiskDxe 发布成 BlockIo。不传时维持原状（搬运原厂 ramdisk）。

打包后会回读校验：解压结果必须与 --fd 字节一致，尾部表 / ramdisk / 签名必须原样一致。
"""
import argparse
import gzip
import hashlib
import io
import struct
import sys

PAGE_DEFAULT = 4096
KSIZE_OFF = 8
RSIZE_OFF = 16
SSIZE_OFF = 24


def md5(b):
    return hashlib.md5(b).hexdigest()


def align(n, page):
    return (n + page - 1) // page * page


def parse_header(blob):
    magic = blob[:8]
    if magic != b'ANDROID!':
        raise SystemExit('不是 Android boot.img：magic=%r' % magic)
    ksize, kaddr = struct.unpack_from('<II', blob, KSIZE_OFF)
    rsize = struct.unpack_from('<I', blob, RSIZE_OFF)[0]
    ssize = struct.unpack_from('<I', blob, SSIZE_OFF)[0]
    page = struct.unpack_from('<I', blob, 36)[0] or PAGE_DEFAULT
    return dict(ksize=ksize, kaddr=kaddr, rsize=rsize, ssize=ssize, page=page)


def split_layout(blob, page, ksize, rsize, ssize):
    """按 Android boot image v0 布局切出各段（含对齐后的真实边界）。"""
    k_start = page
    k_end = k_start + align(ksize, page)
    r_end = k_end + align(rsize, page)
    s_end = r_end + align(ssize, page)
    return {
        'k_start': k_start,
        'k_end': k_end,
        'r_end': r_end,
        's_end': s_end,
        'kernel_raw': blob[k_start:k_start + ksize],
        'kernel_pad': blob[k_start:k_end],
        'ramdisk_seg': blob[k_end:r_end],
        'second_seg': blob[r_end:s_end],
        'extra': blob[s_end:],
    }


def split_kernel_slot(kernel_raw):
    """返回 (gzip 流长度, 解压出的 FD, 尾部 DTB 表)

    注意：不能用 gzip.GzipFile —— 它会继续读第二个 member，撞到后面
    ~30.9 MB 的 DTB 表就报 BadGzipFile。decompressobj 只解第一个 member，
    剩下的字节留在 unused_data 里，正好是表的起点。
    """
    import zlib
    dobj = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = dobj.decompress(kernel_raw)
    out += dobj.flush()
    gz_len = len(kernel_raw) - len(dobj.unused_data)
    return gz_len, out, kernel_raw[gz_len:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--fd', required=True, help='SILICIUM_UEFI.fd-bootshim')
    ap.add_argument('--gz', help='现成的 .gz（可选，省一次压缩）')
    ap.add_argument('--ramdisk', help='替换 ramdisk 槽的 payload.img（可选）')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    base = open(a.base, 'rb').read()
    h = parse_header(base)
    page, ksize, rsize, ssize = h['page'], h['ksize'], h['rsize'], h['ssize']
    lay = split_layout(base, page, ksize, rsize, ssize)

    print('base   : %s  (%d bytes)' % (a.base, len(base)))
    print('  page=%d  kernel_size=%d  kernel_addr=0x%08x' % (page, ksize, h['kaddr']))
    print('  ramdisk_size=%d  second_size=%d  extra(QCOM签名)=%d'
          % (rsize, ssize, len(lay['extra'])))

    gz_len, old_fd, tail = split_kernel_slot(lay['kernel_raw'])
    print('  gzip 流 %d 字节 -> 解压 %d 字节' % (gz_len, len(old_fd)))
    print('  尾部 DTB 表 %d 字节' % len(tail))

    if a.ramdisk:
        ramdisk = open(a.ramdisk, 'rb').read()
        if len(ramdisk) % 512:
            raise SystemExit('payload.img 大小不是 512 的倍数：%d' % len(ramdisk))
        print('payload: %s  (%d bytes, md5 %s)' % (a.ramdisk, len(ramdisk), md5(ramdisk)))
    else:
        ramdisk = lay['ramdisk_seg'][:rsize] if rsize else b''
        print('ramdisk: 原样搬运 %d 字节' % rsize)

    fd = open(a.fd, 'rb').read()
    print('新 FD  : %s  (%d bytes, md5 %s)' % (a.fd, len(fd), md5(fd)))

    if a.gz:
        gz = open(a.gz, 'rb').read()
        if gzip.decompress(gz) != fd:
            raise SystemExit('--gz 与 --fd 内容不一致')
    else:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=9, mtime=0) as f:
            f.write(fd)
        gz = buf.getvalue()
    print('gzip   : %d 字节' % len(gz))

    new_payload = gz + tail
    new_ksize = len(new_payload)
    new_rsize = len(ramdisk)

    hdr = bytearray(base[:page])
    struct.pack_into('<I', hdr, KSIZE_OFF, new_ksize)   # 只改 kernel_size
    struct.pack_into('<I', hdr, RSIZE_OFF, new_rsize)   # ramdisk_size（原样搬运时不变）
    # second_size 原样保留，因为下面把整段原样搬过去

    new_ramdisk_seg = ramdisk + b'\0' * ((-len(ramdisk)) % page)
    img = (bytes(hdr)
           + new_payload + b'\0' * ((-len(new_payload)) % page)
           + new_ramdisk_seg
           + lay['second_seg']
           + lay['extra'])

    open(a.out, 'wb').write(img)
    print('写出   : %s  (%d bytes)' % (a.out, len(img)))

    # ---- 回读校验 ----
    chk = open(a.out, 'rb').read()
    h2 = parse_header(chk)
    lay2 = split_layout(chk, h2['page'], h2['ksize'], h2['rsize'], h2['ssize'])
    gz2_len, fd2, tail2 = split_kernel_slot(lay2['kernel_raw'])

    ok = True
    if fd2 != fd:
        print('!! 校验失败：解压出的 FD 与新 FD 不一致'); ok = False
    if tail2 != tail:
        print('!! 校验失败：尾部 DTB 表不一致 (len %d vs %d)' % (len(tail2), len(tail))); ok = False
    if lay2['ramdisk_seg'] != new_ramdisk_seg:
        print('!! 校验失败：ramdisk 段不一致'); ok = False
    if h2['rsize'] != new_rsize:
        print('!! 校验失败：header ramdisk_size 不符'); ok = False
    if lay2['extra'] != lay['extra']:
        print('!! 校验失败：QCOM 签名段不一致'); ok = False
    if h2['ksize'] != new_ksize or h2['kaddr'] != h['kaddr']:
        print('!! 校验失败：header 字段不符'); ok = False

    # 结构自洽性：按 header 推算的大小必须等于实际文件大小
    calc = (h2['page'] + align(h2['ksize'], h2['page'])
            + align(h2['rsize'], h2['page']) + align(h2['ssize'], h2['page'])
            + len(lay2['extra']))
    if calc != len(chk):
        print('!! 校验失败：header 推算 %d != 实际 %d' % (calc, len(chk))); ok = False

    print('校验   : %s   md5=%s' % ('OK' if ok else 'FAIL', md5(chk)))
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
