#!/usr/bin/env python3
"""rk3568-atk sim smoke。用法: smoke.py [模式] [--check]

  uboot（默认） U-Boot shell；--check = booti 接力挂整块真根（四断言）
  fit           bootm 起 forge FIT boot.img（真板同款文件与命令）
  rootfs        virtio-blk 真根直启（无 U-Boot）
  board         真板 DTS（rk3568-atk-evb1-ddr4-v10）直启
  linux / virt  initramfs shell / Day-0 参考启动

--check 走断言（喂命令+超时+正则），不带则 stdio 直连串口交互（Ctrl-A x 退出）。
SOAK=秒数 存活浸泡；SMP=1 降核；QEMU= 覆盖二进制。dtb/initramfs 按新鲜度自动重建。
"""
import os
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM.parents[2] / "sim"))
import engine

ROOT = engine.ROOT
BOARD = "rk3568-lite"
IMAGE = ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/Image"
LINUX_INC = ROOT / "third_party/src/rk3568-atk/linux/include"
INITRD = ROOT / "sim/initramfs-busybox.cpio.gz"
ROOTFS = ROOT / "out/rk3568-atk/rootfs.ext4"
UBOOT = ROOT / "third_party/src/rk3568-atk/uboot/u-boot.bin"
FIT = ROOT / "out/rk3568-atk/boot.img"
REAL_DTB = ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dtb"

argv = sys.argv[1:]
check = "--check" in argv
mode = next((a for a in argv if not a.startswith("--")), "uboot")
soak = int(os.environ.get("SOAK", "0"))

if not IMAGE.is_file():
    sys.exit(f"内核 Image 缺失: {IMAGE}（跑 forge build）")
engine.ensure_dtb(SIM / f"{BOARD}.dts", SIM / f"{BOARD}.dtb", LINUX_INC)

cmd = [engine.find_qemu(), "-M", BOARD,
       "-smp", os.environ.get("SMP", "4"), "-m", "1G",
       "-nographic", "-no-reboot"]
dtb = ["-dtb", str(SIM / f"{BOARD}.dtb")]
smoke_pats = [rb"Linux version 7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]

if mode == "virt":
    cmd[cmd.index("-M") + 1] = "virt"
    cmd += ["-cpu", "cortex-a55", "-kernel", str(IMAGE), "-initrd", str(INITRD),
            "-append", "console=ttyAMA0 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "linux":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD), *dtb,
            "-append", "console=ttyS2 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "board":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD),
            "-dtb", str(REAL_DTB),
            "-append", "console=ttyS2 earlycon rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 420, smoke_pats, None
elif mode == "rootfs":
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd", *dtb,
            "-append", "console=ttyS2 root=/dev/vda rw rootwait "
                       "init=/bin/sh rk.smoke=1 panic=-1"]
    feed = [(8, b"echo ROOTFS-SHELL-OK\n"), (2, b"poweroff -f\n")]
    tmo, pats = 300, [rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"ROOTFS-SHELL-OK"]
elif mode == "uboot":
    cmd += ["-bios", str(UBOOT), "-dtb", str(REAL_DTB),
            "-device", f"loader,file={IMAGE},addr=0x02000000",
            "-device", f"loader,file={SIM / f'{BOARD}.dtb'},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"booti 0x02000000 - 0x0f000000\n"),
            (25, b"echo UBOOT-ROOTFS-OK\n"), (3, b"poweroff -f\n")]
    tmo, pats = 240, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"UBOOT-ROOTFS-OK"]
elif mode == "fit":
    cmd += ["-bios", str(UBOOT), "-dtb", str(REAL_DTB),
            "-device", f"loader,file={FIT},addr=0x20000000",
            "-device", f"loader,file={SIM / f'{BOARD}.dtb'},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"bootm 0x20000000 - 0x0f000000\n"),
            (30, b"echo UBOOT-FIT-OK\n"), (3, b"poweroff -f\n")]
    tmo, pats = 240, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"UBOOT-FIT-OK"]
else:
    sys.exit(f"unknown mode: {mode}")

hints = {
    "uboot": ("裸 Image@0x02000000 + sim-dtb@0x0f000000 + 真根(/dev/vda)",
              "setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait init=/bin/sh panic=-1'\n"
              "booti 0x02000000 - 0x0f000000"),
    "fit": ("FIT boot.img@0x20000000 + sim-dtb@0x0f000000 + 真根(/dev/vda)",
            "setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait init=/bin/sh panic=-1'\n"
            "bootm 0x20000000 - 0x0f000000"),
}
if not check and mode in hints:
    preload, bootcmd = hints[mode]
    print(f"[sim] 预载: {preload}\n[sim] 建议:\n  {bootcmd}\n", file=sys.stderr)

if check and soak and mode in ("linux", "board"):
    feed, pats, tmo = engine.soakify(cmd, soak)
sys.exit(engine.run(mode, BOARD, cmd, pats, feed, tmo, interactive=not check))
