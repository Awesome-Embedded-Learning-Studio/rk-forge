#!/usr/bin/env python3
"""从 stage 的 rootfs 抽 busybox 最小集打冒烟 initramfs。

纯 Python cpio(newc) 写出：不需要 fakeroot/cpio（设备节点直接写元数据），
Windows 原生可跑；mtime 固定为 0、条目按名字排序——同输入同输出。

用法: build-initramfs.py [rootfs_dir]    默认 out/rk3568-atk/rootfs
"""
import gzip
import os
import stat
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parent
ROOT = SIM.parents[2]
ROOTFS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/rk3568-atk/rootfs"
OUT = SIM / "initramfs-rk3568.cpio.gz"

INIT = """#!/bin/sh
mount -t proc none /proc 2>/dev/null
mount -t sysfs none /sys 2>/dev/null
mount -t devtmpfs none /dev 2>/dev/null
echo "RK3568-M0-SHELL-OK"
uname -a
grep -q "rk.smoke=1" /proc/cmdline 2>/dev/null && poweroff -f
exec /bin/sh    # 兜底交互 shell（无 cttyhack applet，job control 会警告但可用）
"""


def collect():
    """(name, mode, typ, data) 清单；typ: file/link/dir/node"""
    out = []

    def add_tree(base: Path):
        for p in sorted(base.iterdir(), key=lambda x: x.name):
            rel = p.relative_to(ROOTFS).as_posix()
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                out.append((rel, 0o777, "link", os.readlink(p)))
            elif stat.S_ISDIR(st.st_mode):
                out.append((rel, 0o755, "dir", None))
                add_tree(p)
            else:
                out.append((rel, st.st_mode & 0o7777, "file", p.read_bytes()))

    for top in ("bin", "sbin", "lib", "etc"):
        if (ROOTFS / top).is_dir():
            out.append((top, 0o755, "dir", None))
            add_tree(ROOTFS / top)

    # busybox applet 符号链接零成本补全（clear/vi/top 等在 usr/bin）：
    # 只摘指向 busybox 的链接，真文件不抄——防止包再膨胀（65 号笔记 20MB 教训）
    usr_added = False
    for top in ("usr/bin", "usr/sbin"):
        base = ROOTFS / top
        if not base.is_dir():
            continue
        if not usr_added:
            out.append(("usr", 0o755, "dir", None))
            usr_added = True
        out.append((top, 0o755, "dir", None))
        for p in sorted(base.iterdir(), key=lambda x: x.name):
            st = p.lstat()
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(p)
                if "busybox" in target:
                    out.append((p.relative_to(ROOTFS).as_posix(),
                                0o777, "link", target))

    for d in ("proc", "sys", "root", "home", "mnt", "run", "dev"):
        out.append((d, 0o1777 if d == "tmp" else 0o755, "dir", None))
    out.append(("tmp", 0o1777, "dir", None))
    out.append(("lib64", 0o777, "link", "lib"))
    # loader 默认搜索路径是 /lib64（buildroot glibc slibdir），console 缺它 init 没有 stdio
    out.append(("dev/console", 0o600, "node", (5, 1)))
    out.append(("dev/null", 0o666, "node", (1, 3)))
    out.append(("init", 0o755, "file", INIT.encode()))
    return out


def cpio_stream(entries):
    def header(ino, mode, size, rmaj, rmin, namesize):
        f = (ino, mode, 0, 0, 1, 0, size, 0, 0, rmaj, rmin, namesize, 0)
        return ("070701" + "".join(f"{x:08x}" for x in f)).encode()

    for ino, (name, mode, typ, data) in enumerate(entries, 1):
        payload = {"link": lambda: data.encode(), "node": lambda: b"",
                   "file": lambda: data, "dir": lambda: b""}[typ]()
        rmaj, rmin = data if typ == "node" else (0, 0)
        nameb = name.encode() + b"\0"
        head = header(ino, mode | {"dir": stat.S_IFDIR, "link": stat.S_IFLNK,
                                   "node": stat.S_IFCHR, "file": stat.S_IFREG}[typ],
                      len(payload), rmaj, rmin, len(nameb))
        yield head + nameb
        yield b"\0" * (-(len(head) + len(nameb)) % 4)
        yield payload
        yield b"\0" * (-len(payload) % 4)

    nameb = b"TRAILER!!!\0"
    head = header(0, 0, 0, 0, 0, len(nameb))
    yield head + nameb
    yield b"\0" * (-(len(head) + len(nameb)) % 4)


if not (ROOTFS / "bin").is_dir():
    sys.exit(f"rootfs 不存在: {ROOTFS}（先跑 forge stage）")

with gzip.GzipFile(OUT, "wb", mtime=0) as gz:
    for chunk in cpio_stream(collect()):
        gz.write(chunk)
print(f"OK: {OUT} ({OUT.stat().st_size // 1024}K)")
