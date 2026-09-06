#!/usr/bin/env python3
"""rk3588-topeet sim smoke。用法: smoke.py [模式] [--check]

  ubuntu（默认） Ubuntu 26.04 完整开机到串口 login（板级显示路径）
  desktop       同一 DTB + virtio-gpu-gl 桌面加速路径
  gpu-probe     同一 DTB 下从 guest 内部验证 virtio-gpu/DRM 枚举
  rootfs        真板 DTS + Ubuntu 合体（init=/bin/sh 快速路径）
  board         真板 DTS 直启（8 核异构）
  linux         initramfs shell
  uboot / fit   待 SCMI 仿真课题（rk3588 U-Boot 依赖 BL31 固件服务）

--check 走断言，不带则 stdio 直连 virtio-console（Ctrl-A x 退出）。
SOAK=秒数存活浸泡；SMP=降核；QEMU=覆盖二进制；GPU_BACKEND=2d 可诊断
无 virgl 的 QEMU。dtb/initramfs 按新鲜度自动重建。
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
# 真机与仿真共用同一个、未经 QEMU 修改的 DTB。仿真专用的 block/console/GPU
# transport 通过 virtio_mmio.device= 内核参数枚举，不写进设备树。
REAL_DTB = (ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/dts/"
            "rockchip/rk3588-topeet.dtb")

VIRTIO_MMIO = " ".join(
    f"virtio_mmio.device=0x200@0x{0xfea00000 + i * 0x200:x}:spi{160 + i}:{i}"
    for i in range(6)
)

argv = sys.argv[1:]
check = "--check" in argv
mode = next((a for a in argv if not a.startswith("--")), "ubuntu")
soak = int(os.environ.get("SOAK", "0"))

if not IMAGE.is_file():
    sys.exit(f"内核 Image 缺失: {IMAGE}（跑 forge build）")
engine.ensure_dtb(SIM / f"{BOARD}.dts", SIM / f"{BOARD}.dtb", LINUX_INC)

cmd = [engine.find_qemu(), "-M", BOARD,
       "-smp", os.environ.get("SMP", "8"), "-m", "2G",
       "-display", "none", "-no-reboot",
       "-chardev", "stdio,id=hvc0,mux=on,signal=off",
       # The real DTB's UART boot console stays intact but is kept off stdio;
       # hvc0 is the sole visible console, avoiding doubled/interleaved logs.
       "-serial", ("chardev:hvc0" if mode == "linux" else "null"),
       "-mon", "chardev=hvc0,mode=readline",
       "-device", "virtio-serial-device",
       "-device", "virtconsole,chardev=hvc0"]
if os.environ.get("GUI"):
    # GUI=1：virtio-console 继续走 stdio，显示走 GTK。
    display = cmd.index("none")
    cmd[display] = "gtk"
if os.environ.get("MONITOR"):
    # MONITOR=4444 时开 QEMU monitor（fbdump.py 截图用），另终端跑 fbdump
    cmd += ["-monitor", f"tcp:127.0.0.1:{os.environ['MONITOR']},server,nowait"]
if mode in ("desktop", "gpu-probe"):
    if os.environ.get("GPU_BACKEND") == "vop":
        gpu = None                     # 真面板形态：rockchipdrm 是唯一 DRM 卡
    else:
        gpu = ("virtio-gpu-device" if os.environ.get("GPU_BACKEND") == "2d"
               else "virtio-gpu-gl-device")
    # id 给 HMP screendump 点名用（多控制台时裸 screendump 抓到的是默认台）。
    # VIRTIO_INPUT=0 撤掉 virtio 键鼠——M2 终审用：窗口鼠标只剩 gt911 真路径
    if gpu:
        cmd += ["-device", f"{gpu},id=gpu0"]
    if os.environ.get("VIRTIO_INPUT", "1") == "1":
        cmd += ["-device", "virtio-tablet-device", "-device", "virtio-keyboard-device"]
    if gpu == "virtio-gpu-gl-device":
        # virgl 要带 GL 的显示后端：GUI=1 → gtk,gl=on；headless → egl-headless。
        # WSLg 上 gtk 的 EGL 路不通（无 /dev/dri → 窗口建废，连接器报
        # disconnected），DISPLAY_BACKEND=sdl,gl=on 走 GLX 是正解
        cmd[cmd.index("-display") + 1] = (os.environ.get("DISPLAY_BACKEND")
                                          or ("gtk,gl=on" if os.environ.get("GUI")
                                              else "egl-headless"))
        # virgl 给第二个显示设备建 GL 上下文会撞上游断言（qemu GitLab#1727）
        # ——VOP 控制台关掉走单显示形态（fb 寄存器仍导出，fbdump 不受影响）
        cmd[cmd.index("-M") + 1] += ",vop-console=off"
smoke_pats = [rb"Linux (?:version |\(none\) )7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]
def real_args(extra: str) -> list:
    """真板 DTB 公共参数；hvc0 和其他 virtio transport 只由 cmdline 枚举。"""
    # FAST=1 提速档（sim bootargs=宪法许可层）：quiet 砍内核期串口 MMIO 退出；
    # fw_devlink=off 放行未建模设备的供应者等待（defer 风暴）
    # initcall_blacklist：rk806 供电链活了以后 DSI 面板会 probe 出第二张 DRM 卡，
    # virtio-gpu 桌面形态下 mutter 对双屏不知所措——掐掉 rockchipdrm。
    # GPU_BACKEND=vop（真面板桌面）则必须让它活
    blacklist = ("" if os.environ.get("GPU_BACKEND") == "vop"
                 else " initcall_blacklist=rockchip_drm_init")
    fast = ("quiet loglevel=3 fw_devlink=off" + blacklist
            if os.environ.get("FAST") == "1" else "")
    return ["-dtb", str(REAL_DTB),
            "-append", f"console=hvc0 {VIRTIO_MMIO} {extra} "
                       f"panic=-1 cpuidle.off=1 {fast}"
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
    feed = [(25, b"echo ROOTFS-SHELL-OK\n"), (3, b"\x01x")]
    tmo, pats = 600, [rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"ROOTFS-SHELL-OK"]
elif mode == "gpu-probe":
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd",
            *real_args("root=/dev/vda rw rootwait init=/bin/sh")]
    # 不依赖桌面登录凭据：直接在 guest 的 sysfs/devtmpfs 中确认 GPU。
    probe = (b"mount -t proc proc /proc 2>/dev/null; "
             b"mount -t sysfs sysfs /sys 2>/dev/null; "
             b"mount -t devtmpfs devtmpfs /dev 2>/dev/null; "
             b"test -e /sys/class/drm/card0 && test -e /dev/dri/card0 && "
             b"echo VIRTIO-GPU-GUEST-OK || echo VIRTIO-GPU-GUEST-FAIL\n")
    feed = [(25, probe), (3, b"\x01x")]
    tmo, pats = 300, [rb"virtio-mmio: Registering device",
                      rb"VIRTIO-GPU-GUEST-OK"]
elif mode in ("ubuntu", "desktop"):
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd",
            *real_args("root=/dev/vda rw rootwait init=/sbin/init")]
    tmo, pats, feed = 480, [rb"running in system mode",
                            rb"Welcome to .*Ubuntu 26", rb"login:"], None
    if mode == "desktop":
        pats.insert(0, rb"Initialized virtio_gpu")
else:
    sys.exit(f"unknown mode: {mode}（uboot/fit 待 SCMI 课题，见 document/notes/68）")

if check and soak and mode in ("linux", "board"):
    feed, pats, tmo = engine.soakify(cmd, soak)
elif check and feed is None:
    # engine 收齐日志后仍需 QEMU 退出；mux 的 Ctrl-A x 是无破坏的 test teardown。
    feed = [(60 if mode in ("ubuntu", "desktop") else 35, b"\x01x")]
sys.exit(engine.run(mode, BOARD, cmd, pats, feed, tmo, interactive=not check))
