#!/usr/bin/env python3
"""rk3568-lite 一键拉起。纯 Python，Windows 原生可跑。

用法: boot-smoke.py [模式] [--check]      默认 = uboot 交互直入
模式: uboot   U-Boot shell（bootloader 体验；--check = booti 接力内核三断言）
      linux   initramfs Linux shell（--check = M0 三断言）
      rootfs  virtio 真根文件系统直启
      board   真板 DTS 直启
      virt    Day-0 参考启动（QEMU 自带 virt 机器）

--check 走冒烟断言（CI 形态，喂命令+超时+正则）；不带则 stdio 直连串口交互，
退出按 Ctrl-A x。SMP=1 可降单核调试；LOG= 指定 --check 日志路径。
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
IMAGE = ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/Image"
INITRD = SIM / "initramfs-rk3568.cpio.gz"
ROOTFS = ROOT / "out/rk3568-atk/rootfs.ext4"
FIT = ROOT / "out/rk3568-atk/boot.img"
REAL_DTB = ROOT / "third_party/src/rk3568-atk/linux/arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dtb"
UBOOT = ROOT / "third_party/src/rk3568-atk/uboot/u-boot.bin"

argv = sys.argv[1:]
check = "--check" in argv
mode = next((a for a in argv if not a.startswith("--")), "uboot")


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
    """dtb 缺失或比 dts 旧时自动重编（需 dtc + 内核 include 树）"""
    src, dst = SIM / "rk3568-lite.dts", SIM / "rk3568-lite.dtb"
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    inc = ROOT / "third_party/src/rk3568-atk/linux/include"
    if not shutil.which("dtc") or not (inc / "dt-bindings").is_dir():
        die(f"{dst.name} 需要从 {src.name} 重编：请安装 dtc 并确保内核树存在")
    with open(dst, "wb") as f:
        pre = subprocess.Popen(
            ["cpp", "-nostdinc", "-I", str(inc), "-undef",
             "-x", "assembler-with-cpp", str(src)], stdout=subprocess.PIPE)
        post = subprocess.Popen(
            ["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", "-", "-"],
            stdin=pre.stdout, stdout=f)
        pre.stdout.close()
        post.communicate()
        if pre.wait() or post.returncode:
            die("dtb 重编失败")
    print("[boot-smoke] rk3568-lite.dtb 已从 dts 重新生成")


def ensure_initramfs():
    """initramfs 缺失或比 rootfs 旧时自动重打"""
    initrd = SIM / "initramfs-rk3568.cpio.gz"
    busybox = ROOT / "out/rk3568-atk/rootfs/bin/busybox"
    if initrd.exists() and busybox.is_file() \
            and initrd.stat().st_mtime >= busybox.stat().st_mtime:
        return
    subprocess.run([sys.executable, str(SIM / "build-initramfs.py")], check=True)

if not IMAGE.is_file():
    die(f"内核 Image 缺失: {IMAGE}（跑 forge build）")

cmd = [find_qemu(), "-M", "rk3568-lite", "-smp", os.environ.get("SMP", "4"),
       "-m", "1G", "-nographic", "-no-reboot"]
sim_dtb = ["-dtb", str(SIM / "rk3568-lite.dtb")]
smoke_pats = [rb"Linux version 7\.1\.", rb"Run /init as init process",
              rb"RK3568-M0-SHELL-OK"]

if mode == "virt":
    cmd[cmd.index("-M") + 1] = "virt"
    cmd += ["-cpu", "cortex-a55", "-kernel", str(IMAGE), "-initrd", str(INITRD),
            "-append", "console=ttyAMA0 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "linux":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD), *sim_dtb,
            "-append", "console=ttyS2 rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 120, smoke_pats, None
elif mode == "board":
    cmd += ["-kernel", str(IMAGE), "-initrd", str(INITRD),
            "-dtb", str(REAL_DTB),
            "-append", "console=ttyS2 earlycon rdinit=/init rk.smoke=1 panic=-1"]
    tmo, pats, feed = 420, smoke_pats, None
elif mode == "rootfs":
    if not ROOTFS.is_file():
        die(f"rootfs 缺失: {ROOTFS}（跑 forge stage）")
    cmd += ["-kernel", str(IMAGE),
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd", *sim_dtb,
            "-append", "console=ttyS2 root=/dev/vda rw init=/bin/sh "
                       "rk.smoke=1 panic=-1"]
    feed = [(8, b"echo RK3568-ROOTFS-SHELL-OK\n"), (2, b"poweroff -f\n")]
    tmo, pats = 240, [rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"RK3568-ROOTFS-SHELL-OK"]
elif mode == "uboot":
    if not ROOTFS.is_file():
        die(f"rootfs 缺失: {ROOTFS}（跑 forge stage）")
    # U-Boot 吃真板 DTB（看不见 virtio），只负责 booti；内核吃七节点 sim DTB
    # （含 virtio 节点）接过接力棒后挂整块 rootfs.ext4 真根
    cmd += ["-bios", str(UBOOT), "-dtb", str(REAL_DTB),
            "-device", f"loader,file={IMAGE},addr=0x02000000",
            "-device", f"loader,file={SIM / 'rk3568-lite.dtb'},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"booti 0x02000000 - 0x0f000000\n"),
            (25, b"echo RK3568-UBOOT-ROOTFS-OK\n"),
            (3, b"poweroff -f\n")]
    tmo, pats = 240, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"RK3568-UBOOT-ROOTFS-OK"]
elif mode == "fit":
    if not ROOTFS.is_file():
        die(f"rootfs 缺失: {ROOTFS}（跑 forge stage）")
    if not FIT.is_file():
        die(f"boot.img 缺失: {FIT}（跑 forge pack）")
    # 真板同款：forge 的 FIT boot.img + bootm。第三参用外部 sim DTB 覆盖 FIT
    # 内置真板 DTB——sim 里根盘是 virtio 替身（真板 DTB 无此节点，rootwait
    # 会永远等不到 /dev/vda）
    cmd += ["-bios", str(UBOOT), "-dtb", str(REAL_DTB),
            "-device", f"loader,file={FIT},addr=0x20000000",
            "-device", f"loader,file={SIM / 'rk3568-lite.dtb'},addr=0x0f000000",
            "-drive", f"if=none,id=hd,file={ROOTFS},format=raw",
            "-device", "virtio-blk-device,drive=hd"]
    feed = [(0.2, b"\n"),
            (5, b"setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                 b"init=/bin/sh panic=-1'\n"),
            (1, b"bootm 0x20000000 - 0x0f000000\n"),
            (30, b"echo RK3568-UBOOT-FIT-OK\n"),
            (3, b"poweroff -f\n")]
    tmo, pats = 300, [rb"U-Boot 2026", rb"Hit any key to stop autoboot",
                      rb"VFS: Mounted root \(ext4 filesystem\)",
                      rb"RK3568-UBOOT-FIT-OK"]
else:
    die(f"unknown mode: {mode}")

if mode in ("linux", "rootfs", "uboot", "fit"):
    ensure_dtb()
if mode in ("linux", "board", "virt"):
    ensure_initramfs()

if not check:
    # 交互直入：去掉自动关机开关，stdio 直连串口
    for i, a in enumerate(cmd):
        if a == "-append":
            cmd[i + 1] = cmd[i + 1].replace("rk.smoke=1", "").replace("  ", " ")
            break
    bootargs = ("setenv bootargs 'console=ttyS2 root=/dev/vda rw rootwait "
                "init=/bin/sh panic=-1'")
    hints = {
        "uboot": ("裸 Image@0x02000000 + sim-dtb@0x0f000000 + 真根(/dev/vda)",
                  f"{bootargs}\n  booti 0x02000000 - 0x0f000000"),
        "fit": ("FIT boot.img@0x20000000 + sim-dtb@0x0f000000 + 真根(/dev/vda)",
                f"{bootargs}\n  bootm 0x20000000 - 0x0f000000"),
    }
    if mode in hints:
        preload, bootcmd = hints[mode]
        print(f"[boot-smoke] 预载: {preload}\n[boot-smoke] 建议:\n  {bootcmd}",
              file=sys.stderr)
    sys.exit(subprocess.run(cmd).returncode)

log_path = Path(os.environ.get("LOG") or Path(tempfile.gettempdir())
                / f"rk3568-m0-{mode}-boot.log")
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
