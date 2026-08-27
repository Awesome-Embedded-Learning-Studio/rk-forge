#!/usr/bin/env python3
"""rk3568-lite / rk3588-lite 一键拉起。纯 Python，Windows 原生可跑。

用法: boot-smoke.py [板] [模式] [--check]
  板（默认 rk3568-lite）: rk3568-lite | rk3588-lite
  模式: uboot | fit | linux | rootfs | board | virt（板级默认见下）

  rk3568-lite 默认 uboot：U-Boot shell；--check = booti 接力挂整块真根
  rk3588-lite 默认 linux：initramfs shell；--check = 8 核异构三断言

--check 走冒烟断言（喂命令+超时+正则）；不带则 stdio 直连串口交互，
退出 Ctrl-A x。SMP=1 降单核；QEMU 自动发现（third_party/qemu/build 优先）。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
ROOT = SIM.parents[2]

BOARDS = {
    "rk3568-lite": dict(
        sim_dir=SIM,
        image=ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/Image",
        initrd=SIM / "initramfs-rk3568.cpio.gz",
        rootfs=ROOT / "out/rk3568-atk/rootfs.ext4",
        uboot=ROOT / "third_party/src/rk3568-atk/uboot/u-boot.bin",
        fit=ROOT / "out/rk3568-atk/boot.img",
        real_dtb=ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dtb",
        mem="1G", console="ttyS2", default_mode="uboot",
    ),
    "rk3588-lite": dict(
        sim_dir=ROOT / "boards/rk3588-topeet/sim",
        image=ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/Image",
        initrd=SIM / "initramfs-rk3568.cpio.gz",  # busybox 包板无关，共用
        rootfs=ROOT / "out/rk3588-topeet/rootfs.ext4",
        uboot=None,  # U-Boot 线待课题（真板控制台是 ttyFIQ0，需先解决）
        fit=None,
        real_dtb=ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/dts/rockchip/rk3588-topeet.dtb",
        mem="2G", console="ttyS2", default_mode="linux",
    ),
}

argv = sys.argv[1:]
check = "--check" in argv
args = [a for a in argv if not a.startswith("--")]
board = args[0] if args and args[0] in BOARDS else "rk3568-lite"
if args and args[0] in BOARDS:
    args = args[1:]
mode = args[0] if args else BOARDS[board]["default_mode"]

B = BOARDS[board]
SIM_DTB = B["sim_dir"] / f"{board}.dtb"
SIM_DTS = B["sim_dir"] / f"{board}.dts"
INITRD = B["initrd"]


def find_qemu():
    env = os.environ.get("QEMU")
    if env:
        return env
    local = ROOT / "third_party/qemu/build/qemu-system-aarch64"
    if os.name == "nt":
        local = local.with_suffix(".exe")
    return str(local) if local.exists() else "qemu-system-aarch64"


def die(msg):
    sys.exit(msg)


def ensure_dtb():
    """dtb 缺失或比 dts 旧时自动重编（需 dtc + 对应内核 include 树）"""
    if SIM_DTB.exists() and SIM_DTB.stat().st_mtime >= SIM_DTS.stat().st_mtime:
        return
    inc = ROOT / f"third_party/src/{'rk3588-topeet' if board == 'rk3588-lite' else 'rk3568-atk'}/linux/include"
    if not shutil.which("dtc") or not (inc / "dt-bindings").is_dir():
        die(f"{SIM_DTB.name} 需要从 {SIM_DTS.name} 重编：请安装 dtc 并确保内核树存在")
    with open(SIM_DTB, "wb") as f:
        pre = subprocess.Popen(
            ["cpp", "-nostdinc", "-I", str(inc), "-undef",
             "-x", "assembler-with-cpp", str(SIM_DTS)], stdout=subprocess.PIPE)
        post = subprocess.Popen(
            ["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", "-", "-"],
            stdin=pre.stdout, stdout=f)
        pre.stdout.close()
        post.communicate()
        if pre.wait() or post.returncode:
            die("dtb 重编失败")
    print(f"[boot-smoke] {SIM_DTB.name} 已从 dts 重新生成")


def ensure_initramfs():
    busybox = ROOT / "out/rk3568-atk/rootfs/bin/busybox"
    if INITRD.exists() and busybox.is_file() \
            and INITRD.stat().st_mtime >= busybox.stat().st_mtime:
        return
    subprocess.run([sys.executable, str(SIM / "build-initramfs.py")], check=True)


if not B["image"].is_file():
    die(f"内核 Image 缺失: {B['image']}（跑 forge build）")

cmd = [find_qemu(), "-M", board, "-smp", os.environ.get("SMP", "8" if board == "rk3588-lite" else "4"),
       "-m", B["mem"], "-nographic", "-no-reboot"]
dtb = ["-dtb", str(SIM_DTB)]
smoke_pats = [rb"Linux version 7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]

if mode == "virt" and board == "rk3568-lite":
    cmd[cmd.index("-M") + 1] = "virt"
    cmd += ["-cpu", "cortex-a55", "-kernel", str(B["image"]),
            "-initrd", str(INITRD),
            "-append", "console=ttyAMA0 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "linux":
    cmd += ["-kernel", str(B["image"]), "-initrd", str(INITRD), *dtb,
            "-append", f"console={B['console']} rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "board" and board == "rk3588-lite":
    # 真板 DTS：FIQ 调试器被 modify_dtb 挪走、uart2 还给 8250；显式 earlycon
    # 不依赖 chosen；cpuidle.off=1 规避 TCG 异构下的 hard lockup（笔记 68）
    cmd += ["-kernel", str(B["image"]), "-initrd", str(INITRD),
            "-dtb", str(B["real_dtb"]),
            "-append", "console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 "
                       "rdinit=/init rk.smoke=1 panic=-1 cpuidle.off=1"]
    tmo, pats, feed = 420, smoke_pats, None
elif mode == "board" and board == "rk3568-lite":
    cmd += ["-kernel", str(B["image"]), "-initrd", str(INITRD),
            "-dtb", str(B["real_dtb"]),
            "-append", "console=ttyS2 earlycon rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 420, smoke_pats, None
elif mode == "rootfs":
    if not B["rootfs"].is_file():
        die(f"rootfs 缺失: {B['rootfs']}（跑 forge stage）")
    if board == "rk3588-lite":
        # 真板 DTS + Ubuntu 真根合体：modify_dtb 补种 virtio（真板无此节点）
        cmd += ["-kernel", str(B["image"]),
                "-drive", f"if=none,id=hd,file={B['rootfs']},format=raw",
                "-device", "virtio-blk-device,drive=hd",
                "-dtb", str(B["real_dtb"]),
                "-append", "console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 "
                           "root=/dev/vda rw rootwait init=/bin/sh panic=-1 "
                           "cpuidle.off=1"]
        feed = [(25, b"echo ROOTFS-SHELL-OK\n"), (3, b"poweroff -f\n")]
        tmo = 600
    else:
        cmd += ["-kernel", str(B["image"]),
                "-drive", f"if=none,id=hd,file={B['rootfs']},format=raw",
                "-device", "virtio-blk-device,drive=hd", *dtb,
                "-append", f"console={B['console']} root=/dev/vda rw rootwait "
                           "init=/bin/sh rk.smoke=1 panic=-1"]
        feed = [(8, b"echo ROOTFS-SHELL-OK\n"), (2, b"poweroff -f\n")]
        tmo = 300
    pats = [rb"VFS: Mounted root \(ext4 filesystem\)", rb"ROOTFS-SHELL-OK"]
elif mode == "systemd" and board == "rk3588-lite":
    # Ubuntu 全量开机：systemd 259 → 图形目标排队 → 串口 login（TCG 下约
    # 4-5 分钟到提示符）。GNOME 不可用（无 GPU，见 68 号前分析）。
    if not B["rootfs"].is_file():
        die(f"rootfs 缺失: {B['rootfs']}（跑 forge stage）")
    cmd += ["-kernel", str(B["image"]),
            "-drive", f"if=none,id=hd,file={B['rootfs']},format=raw",
            "-device", "virtio-blk-device,drive=hd",
            "-dtb", str(B["real_dtb"]),
            "-append", "console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 "
                       "root=/dev/vda rw rootwait init=/sbin/init panic=-1 "
                       "cpuidle.off=1"]
    tmo, pats, feed = 480, [rb"running in system mode",
                            rb"Welcome to .*Ubuntu 26", rb"login:"], None
elif mode == "uboot" and board == "rk3568-lite":
    if not B["rootfs"].is_file():
        die(f"rootfs 缺失: {B['rootfs']}（跑 forge stage）")
    cmd += ["-bios", str(B["uboot"]), "-dtb", str(B["real_dtb"]),
            "-device", f"loader,file={B['image']},addr=0x02000000",
            "-device", f"loader,file={SIM_DTB},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={B['rootfs']},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"booti 0x02000000 - 0x0f000000\n"),
            (25, b"echo UBOOT-ROOTFS-OK\n"), (3, b"poweroff -f\n")]
    tmo, pats = 240, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"UBOOT-ROOTFS-OK"]
elif mode == "fit" and board == "rk3568-lite":
    if not B["fit"].is_file():
        die(f"boot.img 缺失: {B['fit']}（跑 forge pack）")
    cmd += ["-bios", str(B["uboot"]), "-dtb", str(B["real_dtb"]),
            "-device", f"loader,file={B['fit']},addr=0x20000000",
            "-device", f"loader,file={SIM_DTB},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={B['rootfs']},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"bootm 0x20000000 - 0x0f000000\n"),
            (30, b"echo UBOOT-FIT-OK\n"), (3, b"poweroff -f\n")]
    tmo, pats = 300, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)", rb"UBOOT-FIT-OK"]
else:
    die(f"unknown mode/board: {mode} {board}")

if mode != "virt":
    ensure_dtb()
if mode in ("linux", "board", "virt"):
    ensure_initramfs()

soak = int(os.environ.get("SOAK", "0"))
if check and soak and mode in ("linux", "board"):
    # 存活浸泡：去掉自动关机，shell 每 5s 一拍心跳，全到齐后关机——
    # 防「断言过完就挂」（cpuidle 锁死类故障在 30s+ 才发作）
    for i, a in enumerate(cmd):
        if a == "-append":
            cmd[i + 1] = cmd[i + 1].replace("rk.smoke=1", "")
    beats = soak // 5
    feed = [(8, f"echo BEAT-0\n".encode())]
    feed += [(5, f"echo BEAT-{n}\n".encode()) for n in range(1, beats)]
    feed.append((3, b"poweroff -f\n"))
    tmo = soak + 150
    pats = [f"BEAT-{n}".encode() for n in range(beats)]

if not check:
    # 交互直入：去掉自动关机开关，stdio 直连串口
    for i, a in enumerate(cmd):
        if a == "-append":
            cmd[i + 1] = cmd[i + 1].replace("rk.smoke=1", "").replace("  ", " ")
            break
    bootargs = (f"setenv bootargs 'console={B['console']} root=/dev/vda rw "
                "rootwait init=/bin/sh panic=-1'")
    hints = {
        "uboot": (f"裸 Image@0x02000000 + {SIM_DTB.name}@0x0f000000 + 真根(/dev/vda)",
                  f"{bootargs}\n  booti 0x02000000 - 0x0f000000"),
        "fit": (f"FIT boot.img@0x20000000 + {SIM_DTB.name}@0x0f000000 + 真根(/dev/vda)",
                f"{bootargs}\n  bootm 0x20000000 - 0x0f000000"),
        "linux": ("initramfs，/init 自动落 shell", ""),
        "rootfs": ("真根(/dev/vda) + init=/bin/sh，/init 后即 shell", ""),
    }
    if mode in hints:
        preload, bootcmd = hints[mode]
        lines = f"[boot-smoke] {board} {mode} 预载: {preload}"
        if bootcmd:
            lines += f"\n[boot-smoke] 建议:\n  {bootcmd}"
        print(lines, file=sys.stderr)
    sys.exit(subprocess.run(cmd).returncode)

log_path = Path(os.environ.get("LOG") or Path(tempfile.gettempdir())
                / f"rk-m0-{board}-{mode}-boot.log")
with open(log_path, "wb") as log:
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log,
                            stderr=subprocess.STDOUT)
    if feed:
        def writer():
            for delay, data in feed:
                time.sleep(delay)
                try:
                    proc.stdin.write(data)
                    proc.stdin.flush()
                except OSError:
                    return
        threading.Thread(target=writer, daemon=True).start()
    try:
        proc.wait(timeout=tmo)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

data = log_path.read_bytes()
fails = [p for p in pats if not re.search(p, data)]
for p in pats:
    tag = "FAIL" if p in fails else "PASS"
    print(f"{tag}: {p.decode('latin1')}")
if fails:
    print(f"== FAIL，日志尾 20 行（{log_path}）：")
    for line in data.decode("latin1", errors="replace").splitlines()[-20:]:
        print(line)
sys.exit(1 if fails else 0)
