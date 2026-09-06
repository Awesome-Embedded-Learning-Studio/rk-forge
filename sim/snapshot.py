#!/usr/bin/env python3
"""桌面态快照：绕过 80 秒 TCG 冷启动地板（战役四提速的真正杠杆）。

背景：framehunt 多轮实测，冷启动到 GNOME 首帧 ~79-92s，瓶颈是 llvmpipe
JIT + shell 冷启的纯模拟 CPU 计算，guest 侧裁剪（动画/服务/journal）与
quiet 内核均无效果。解法改成工作流：把「已到桌面」的整机状态（RAM +
磁盘）存成 QEMU 内部快照，之后每次 restore 直接秒级落桌面。

实现：rootfs.ext4 之上叠 qcow2 overlay（基盘只读、可反复回到同一态），
savevm/loadvm 走 monitor。
  python3 sim/snapshot.py create   # 冷启动到首帧 → savevm desktop → 关机
  python3 sim/snapshot.py restore  # loadvm desktop → 留守运行（串口 4446/监视 4445）
  python3 sim/snapshot.py drop     # 删 overlay（基盘 rootfs.ext4 变了就要重造）
注意：快照绑基盘内容——rootfs.ext4 / 内核 Image 更新后快照即作废，drop 重来。
现状（2026-08-30，战役六后）：vmsd 全量在库（机器级+设备级），restore 9s
出完整桌面。**SMP=1 create → SMP=1 restore 已验证稳定 ≥5min**（屏幕 5min
变黑是 GNOME 空闲息屏——本流程不挂输入设备，属预期）。8 核 restore 仍有
迟发 hardlockup（~1min 后 cpu0 被伙伴看门狗判死，watchdog=0 无效）——vmstate
流本身完好（trace 全段装载成功、机器字段往返正确），嫌疑收敛到多 vCPU 的
跨核/定时器状态恢复，单核即规避。SMP 环境变量同值使用。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))
import engine  # noqa: E402
from fbdump import png_write, qom_get, read_mem  # noqa: E402
import socket  # noqa: E402

ROOT = engine.ROOT
OVERLAY = ROOT / "out/rk3588-topeet/sim-desktop.qcow2"
BASE = ROOT / "out/rk3588-topeet/rootfs.ext4"
PORT, SPORT = 4445, 4446
TAG = "desktop"


def mon_connect():
    sk = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    sk.settimeout(0.4)
    return sk


def mon_cmd(sk, cmd, wait=3.0):
    sk.sendall(cmd.encode() + b"\n")
    out = b""
    dl = time.time() + wait
    while time.time() < dl:
        try:
            d = sk.recv(65536)
            if not d:
                break
            out += d
        except Exception:
            pass
    return out.decode(errors="replace")


def has_frame(sk):
    """扫描输出寄存器已导出 = 桌面已画出。"""
    return bool(qom_get(sk, "vop-fb-phys") or qom_get(sk, "vop-fb-mst"))


def qemu_argv(load=False):
    argv = [
        engine.find_qemu(), "-M", "rk3588-lite",
        "-smp", os.environ.get("SMP", "8"), "-m", "2G",
        "-display", "none", "-no-reboot",
        "-chardev", f"socket,id=ser0,host=127.0.0.1,port={SPORT},server=on,"
                    f"wait=off,logfile=/tmp/snapshot-serial.log",
        "-device", "virtio-serial-device",
        "-device", "virtconsole,chardev=ser0",
        "-serial", "null",
        "-monitor", f"tcp:127.0.0.1:{PORT},server,nowait",
        "-kernel", str(ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/Image"),
        "-drive", f"if=none,id=hd,file={OVERLAY},format=qcow2",
        "-device", "virtio-blk-device,drive=hd",
        # 同 DTB 宪法（note 77）：真板 dtb 直用，virtio 只由 cmdline 枚举
        "-dtb", str(ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/"
                    "dts/rockchip/rk3588-topeet.dtb"),
        "-append",
        "console=hvc0 "
        + " ".join(
            f"virtio_mmio.device=0x200@0x{0xfea00000 + i * 0x200:x}:spi{160 + i}:{i}"
            for i in range(6))
        + " root=/dev/vda rw rootwait init=/sbin/init panic=-1 cpuidle.off=1 "
        "drm_client_lib.active=none quiet loglevel=3 fw_devlink=off "
        # panthor M0 后 renderD128 存在，mutter 的 EGL 会去开它并卡死在
        # 未实现的 CSG ioctl 上（gnome-shell 20s 循环崩，VOP 无帧）。
        # 桌面工作流临时拉黑；M1（ioctl 全通）后撤除。sim-only bootargs
        # 手术，同 smoke.py FAST 档 initcall_blacklist 先例。
        "initcall_blacklist=panthor_init "
        "systemd.mask=serial-getty@ttyFIQ0.service "
        "systemd.mask=wpa_supplicant@wlan0.service "
        "systemd.mask=plymouth-start.service "
        "systemd.mask=plymouth-quit-wait.service",
    ]
    if load:
        argv += ["-loadvm", TAG]
    return argv


def wait_monitor(deadline_s):
    """等 monitor 端口起来并出 prompt。"""
    dl = time.time() + deadline_s
    while time.time() < dl:
        try:
            sk = mon_connect()
            out = mon_cmd(sk, "info status", wait=2.0)
            if "running" in out or "paused" in out:
                return sk
            sk.close()
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit("monitor 迟迟未就绪")


def wait_frame(sk, deadline_s, tag):
    dl = time.time() + deadline_s
    last = 0.0
    while time.time() < dl:
        if has_frame(sk):
            t = time.time()
            print(f"[{tag}] 首帧就绪 +{t - T0:.1f}s")
            return t - T0
        time.sleep(3)
    raise SystemExit("等待首帧超时")


T0 = 0.0


def create():
    global T0
    if OVERLAY.exists():
        raise SystemExit(f"{OVERLAY} 已存在（先 drop；基盘变了也别复用旧快照）")
    subprocess.run([str(ROOT / "third_party/qemu/build/qemu-img"), "create",
                    "-f", "qcow2", "-b", str(BASE), "-F", "raw", str(OVERLAY)],
                   check=True)
    T0 = time.time()
    proc = subprocess.Popen(qemu_argv(load=False),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"冷启动 pid {proc.pid} …")
    sk = wait_monitor(30)
    wait_frame(sk, 300, "create")
    # 多等 10s 让 shell 把首屏画完整（时钟/壁纸都稳定）
    time.sleep(10)
    print("stop + savevm …")
    mon_cmd(sk, "stop", wait=5)
    mon_cmd(sk, f"savevm {TAG}", wait=180)
    mon_cmd(sk, "quit", wait=5)
    proc.wait(timeout=30)
    print(f"快照完成 {TAG}（总耗时 {time.time() - T0:.1f}s）→ {OVERLAY}")


def restore():
    global T0
    if not OVERLAY.exists():
        raise SystemExit("没有 overlay，先 create")
    T0 = time.time()
    proc = subprocess.Popen(qemu_argv(load=True),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"restore pid {proc.pid} …")
    sk = wait_monitor(60)
    t = wait_frame(sk, 120, "restore")
    dt = time.strftime("%H:%M:%S")
    print(f"桌面恢复：冷启动 ~80s → {t:.1f}s；QEMU 留守（串口 tcp:{SPORT}，监视 tcp:{PORT}） pid {proc.pid} @{dt}")


def drop():
    if OVERLAY.exists():
        OVERLAY.unlink()
        print(f"已删 {OVERLAY}")
    else:
        print("本就没有 overlay")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"create": create, "restore": restore, "drop": drop}.get(mode, lambda: print(__doc__))()
