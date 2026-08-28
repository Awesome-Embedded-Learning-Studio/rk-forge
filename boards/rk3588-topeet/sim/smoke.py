#!/usr/bin/env python3
"""rk3588-topeet sim smoke。用法: smoke.py [模式] [--check]

  ubuntu（默认） Ubuntu 26.04 完整开机到串口 login（systemd，TCG 约 4-5 分钟）
  rootfs        真板 DTS + Ubuntu 合体（init=/bin/sh 快速路径）
  board         真板 DTS 直启（8 核异构）
  linux         initramfs shell
  uboot / fit   待 SCMI 仿真课题（rk3588 U-Boot 依赖 BL31 固件服务）

--check 走断言，不带则 stdio 直连串口交互（Ctrl-A x 退出）。
SOAK=秒数 存活浸泡；SMP= 降核；QEMU= 覆盖二进制。dtb/initramfs 按新鲜度自动重建。
"""
import os
import sys
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM.parents[2] / "sim"))
import engine

ROOT = engine.ROOT
BOARD = "rk3588-lite"
IMAGE = ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/Image"
LINUX_INC = ROOT / "third_party/src/rk3588-topeet/linux/include"
INITRD = ROOT / "sim/initramfs-busybox.cpio.gz"
ROOTFS = ROOT / "out/rk3588-topeet/rootfs.ext4"
REAL_DTB = ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/dts/rockchip/rk3588-topeet.dtb"

argv = sys.argv[1:]
check = "--check" in argv
mode = next((a for a in argv if not a.startswith("--")), "ubuntu")
soak = int(os.environ.get("SOAK", "0"))

if not IMAGE.is_file():
    sys.exit(f"内核 Image 缺失: {IMAGE}（跑 forge build）")
engine.ensure_dtb(SIM / f"{BOARD}.dts", SIM / f"{BOARD}.dtb", LINUX_INC)

cmd = [engine.find_qemu(), "-M", BOARD,
       "-smp", os.environ.get("SMP", "8"), "-m", "2G",
       "-nographic", "-no-reboot"]
smoke_pats = [rb"Linux version 7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]
def real_args(extra: str) -> list:
    """真板 DTS 公共参数：FIQ 调试器被 modify_dtb 挪走、uart2 还给 8250；
    显式 earlycon 不依赖 chosen；cpuidle.off=1 规避 TCG 异构 lockup（笔记 68）"""
    return ["-dtb", str(REAL_DTB),
            "-append", f"console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 {extra} "
                       "panic=-1 cpuidle.off=1 "
                       # sim 无 FIQ 调试器/无 WiFi：屏蔽对应 getty/wpa 省两轮 90s 等待
                       "systemd.mask=serial-getty@ttyFIQ0.service "
                       "systemd.mask=wpa_supplicant@wlan0.service"]

if mode == "linux":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD),
            "-dtb", str(SIM / f"{BOARD}.dtb"),
            "-append", "console=ttyS2 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "board":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD),
            *real_args("rdinit=/init rk.smoke=1")]
    tmo, pats, feed = 420, smoke_pats, None
elif mode == "rootfs":
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd",
            *real_args("root=/dev/vda rw rootwait init=/bin/sh")]
    feed = [(25, b"echo ROOTFS-SHELL-OK\n"), (3, b"poweroff -f\n")]
    tmo, pats = 600, [rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"ROOTFS-SHELL-OK"]
elif mode == "ubuntu":
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd",
            *real_args("root=/dev/vda rw rootwait init=/sbin/init")]
    tmo, pats, feed = 480, [rb"running in system mode",
                            rb"Welcome to .*Ubuntu 26", rb"login:"], None
else:
    sys.exit(f"unknown mode: {mode}（uboot/fit 待 SCMI 课题，见 document/notes/68）")

if check and soak and mode in ("linux", "board"):
    feed, pats, tmo = engine.soakify(cmd, soak)
sys.exit(engine.run(mode, BOARD, cmd, pats, feed, tmo, interactive=not check))
