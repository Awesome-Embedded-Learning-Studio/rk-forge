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
# 真板 DTB + sim 手术（vin-supply 摘除，dtc 保证结构）——raw 真板 dtb 的
# PMIC 链会 defer 死 panel，rockchip-drm 永不 bind（/dev/dri 缺失的根因）
REAL_DTB = SIM / "rk3588-topeet-board.dtb"

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
if os.environ.get("GUI"):
    # GUI=1：-nographic 换 -display gtk（WSLg 直接弹 Windows 窗口），串口走 stdio
    gui = [x for x in ("-nographic",) if False]
    cmd = [c for c in cmd if c != "-nographic"] + ["-display", "gtk", "-serial", "mon:stdio"]
if os.environ.get("MONITOR"):
    # MONITOR=4444 时开 QEMU monitor（fbdump.py 截图用），另终端跑 fbdump
    cmd += ["-monitor", f"tcp:127.0.0.1:{os.environ['MONITOR']},server,nowait"]
smoke_pats = [rb"Linux version 7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]
def real_args(extra: str) -> list:
    """真板 DTS 公共参数：FIQ 调试器被 modify_dtb 挪走、uart2 还给 8250；
    显式 earlycon 不依赖 chosen；cpuidle.off=1 规避 TCG 异构 lockup（笔记 68）"""
    return ["-dtb", str(REAL_DTB),
            "-append", f"console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 {extra} "
                       "panic=-1 cpuidle.off=1 "
                       # fbdev client 的首次 modeset 会死锁（runtime PM ×
                       # flip_done，笔记 73）——绕过后 KMS 用户态路径完整，
                       # gdm/weston/modetest 均可用；fbcon 挂账战役四
                       "drm_client_lib.active=none "
                       # sim 无 FIQ 调试器/无 WiFi：屏蔽对应 getty/wpa 省两轮 90s 等待；
                       # plymouth 的 splash 也是一串 modeset 触发源，一并屏蔽
                       "systemd.mask=serial-getty@ttyFIQ0.service "
                       "systemd.mask=wpa_supplicant@wlan0.service "
                       "systemd.mask=plymouth-start.service "
                       "systemd.mask=plymouth-quit-wait.service"]

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
