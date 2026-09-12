#!/usr/bin/env python3
"""连 QEMU gdbstub（tcp:1234），halt 全部 vCPU 并打印每核 PC/LR（addr2line 解析）。
用法： 先起 `qemu ... -gdb tcp::1234`，冻结后另终端跑本脚本。"""
import re
import socket
import subprocess
import sys
import time

VMLINUX = "third_party/src/rk3588-topeet/linux/vmlinux"


def pkt(s, csum=True):
    data = s.encode()
    if csum:
        c = sum(data) & 0xFF
        return b"$" + data + b"#" + f"{c:02x}".encode()
    return data


class Buf:
    def __init__(self, sk):
        self.sk = sk
        self.b = bytearray()

    def read1(self):
        while not self.b:
            self.sk.settimeout(3)
            d = self.sk.recv(4096)
            if not d:
                raise EOFError
            self.b += d
        c = self.b[:1]
        del self.b[:1]
        return c


def recv_pkt(f):
    while f.read1() != b"$":
        pass
    out = bytearray()
    while True:
        b = f.read1()
        if b == b"#":
            f.read1(); f.read1()
            return bytes(out)
        out += b


def cmd(f, s):
    f.sk.sendall(pkt(s))
    return recv_pkt(f)


def main():
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1234
    sk = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    f = Buf(sk)
    sk.sendall(b"\x03")                      # halt
    time.sleep(0.5)
    try:
        recv_pkt(f)
    except Exception:
        pass
    ids = [str(i) for i in range(1, 9)]   # QEMU vCPU thread ids 1..8
    for t in ids:
        cmd(f, f"Hg{t}")
        regs = cmd(f, "g")
        if not regs or len(regs) < 32:
            print(f"cpu{t}: regs unreadable ({len(regs) if regs else 0})")
            continue
        # aarch64: x0..x30 各 8 字节 hex（小端字节序），PC=reg32, LR=x30
        raw = regs.decode()
        def reg(i):
            h = raw[i * 16:(i + 1) * 16]
            b = bytes.fromhex(h)[::-1]
            return int.from_bytes(b, "big")
        pc, lr = reg(32), reg(30)
        sp = reg(31)
        print(f"cpu{t}: PC=0x{pc:x} LR=0x{lr:x} SP=0x{sp:x}")
        for name, addr in (("PC", pc), ("LR", lr)):
            r = subprocess.run(["addr2line", "-e", VMLINUX, "-f", hex(addr)],
                               capture_output=True, text=True)
            sym = r.stdout.splitlines()[0] if r.stdout else "?"
            print(f"       {name} -> {sym}")
    sk.close()


if __name__ == "__main__":
    main()
