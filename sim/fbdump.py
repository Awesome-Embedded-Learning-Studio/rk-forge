#!/usr/bin/env python3
"""仿真屏幕截图：QEMU monitor 读 VOP 导出的扫描输出参数，dump framebuffer 存 PNG。

用法： QEMU 需带 `-monitor tcp:127.0.0.1:4444,server,nowait` 运行中，然后
  python3 sim/fbdump.py [输出.png]
读取链：qom-get /machine vop-fb-mst / vop-fb-dsp → xp dump fb → PNG（纯标准库）。
"""
import re
import socket
import struct
import sys
import time
import zlib

MON = ("127.0.0.1", 4444)


def rd(sk, sec):
    out = b""
    dl = time.time() + sec
    while time.time() < dl:
        try:
            d = sk.recv(65536)
            if not d:
                break
            out += d
        except Exception:
            pass
    return out


def mon(sk, cmd, wait=2.5):
    sk.sendall(cmd.encode() + b"\n")
    out = rd(sk, wait)
    return out.decode(errors="replace")


def qom_get(sk, prop):
    txt = mon(sk, f"qom-get /machine {prop}")
    # 回复是裸数字行（readline 回显后 "0\r\n(qemu)"），取最后一个纯数字行
    for ln in reversed(txt.splitlines()):
        s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", ln).strip()
        if re.fullmatch(r"\d+", s):
            return int(s)
    return None


def read_mem(sk, addr, n):
    sk.sendall(f"xp /{n}bx 0x{addr:x}\n".encode())
    buf = b""
    dl = time.time() + 10
    while time.time() < dl:
        try:
            d = sk.recv(262144)
            if not d:
                break
            buf += d
        except Exception:
            pass
        m = re.findall(r"0x([0-9a-f]{2})\b", buf.decode(errors="replace"))
        if len(m) >= n:
            return bytes(int(x, 16) for x in m[:n])
    m = re.findall(r"0x([0-9a-f]{2})\b", buf.decode(errors="replace"))
    return bytes(int(x, 16) for x in m[:n])


def png_write(path, w, h, pixels):
    """XRGB8888（4 字节/像素）→ PNG。"""
    rows = []
    for y in range(h):
        row = bytearray()
        row.append(0)  # filter none
        base = y * w * 4
        for x in range(w):
            px = pixels[base + x * 4:base + x * 4 + 4]
            row += bytes((px[2], px[1], px[0]))  # BGR→RGB little-endian XRGB
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))
    return w * h


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sim-screen.png"
    sk = socket.create_connection(MON, timeout=5)
    sk.settimeout(0.4)
    rd(sk, 1.5)
    mst = qom_get(sk, "vop-fb-mst")
    dsp = qom_get(sk, "vop-fb-dsp")
    if not mst or not dsp or mst < 0x100000:
        print(f"扫描输出未就绪：mst={mst} dsp={dsp}")
        sys.exit(1)
    width = dsp & 0x1FFF
    height = (dsp >> 16) & 0x1FFF
    print(f"fb @ 0x{mst:x}  {width}x{height}")
    if width < 16 or height < 16 or width * height > 16 * 1024 * 1024:
        print("尺寸不合理")
        sys.exit(1)
    fb = read_mem(sk, mst, width * height * 4)
    if len(fb) < width * height * 4:
        print(f"dump 不足：{len(fb)}/{width * height * 4}")
        sys.exit(1)
    n = png_write(out, width, height, fb)
    print(f"OK: {out} ({n} px)")
    sk.close()


if __name__ == "__main__":
    main()
