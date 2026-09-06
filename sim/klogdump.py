#!/usr/bin/env python3
"""仿真机内核日志取证：QEMU monitor 读 __log_buf 尾部（printk 环形缓冲区）。

用法： QEMU 带 `-monitor tcp:127.0.0.1:PORT,server,nowait` 运行中：
  python3 sim/klogdump.py [port] [grep-pattern]
地址依据：System.map __log_buf = ffff800082c98140，内核 KIMAGE 加载在
phys 0x0 + 偏移，实测 phys = 0x2c98140（战役二裁决）。
"""
import re
import socket
import sys
import time

# __log_buf 物理地址（KIMAGE 区：virt - ffff800080000000）
BASE = 0x2ca9140
TAIL_BYTES = 128 * 1024   # printk 环尾部 128KB


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4444
    pat = sys.argv[2] if len(sys.argv) > 2 else None
    sk = socket.create_connection(("127.0.0.1", port), timeout=5)
    sk.settimeout(0.4)

    def rd(sec):
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

    rd(1.5)
    # 分 16KB 块收，回显开销大，逐块拼
    buf = bytearray()
    for off in range(0, TAIL_BYTES, 16384):
        sk.sendall(f"xp /16384bx 0x{BASE + off:x}\n".encode())
        chunk = b""
        dl = time.time() + 12
        while time.time() < dl:
            try:
                d = sk.recv(262144)
                if not d:
                    break
                chunk += d
                m = re.findall(rb"0x([0-9a-f]{2})\b", chunk)
                if len(m) >= 16384:
                    break
            except Exception:
                pass
        m = re.findall(rb"0x([0-9a-f]{2})\b", chunk)
        buf += bytes(int(x, 16) for x in m[:16384])
    sk.close()

    txt = buf.decode(errors="replace")
    tail = txt.rstrip("\x00")[-40000:]
    lines = tail.splitlines()
    if pat:
        rx = re.compile(pat, re.I)
        lines = [l for l in lines if rx.search(l)]
    for l in lines[-60:]:
        print(l)


if __name__ == "__main__":
    main()
