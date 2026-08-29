#!/usr/bin/env python3
"""首帧狩猎器（战役四自动化）：headless 拉起 rk3588-lite Ubuntu 全链，
轮询 fbdump 直到首帧 PNG 落地，记录时间线（开机→login→首帧），收尾杀机。

用法： python3 sim/framehunt.py [超时秒，默认 420]
产物： /tmp/framehunt-serial.log（串口）、/tmp/framehunt-0.png..（截图）、
       /tmp/framehunt-report.txt（时间线）。
环境： SMP=vCPU 数（默认 8）；KEEP=1 时狩猎完不杀 QEMU，串口转 TCP
       （SERIAL_TCP 端口，默认 4446）供 sercmd.py 继续深挖。
单实例纪律：狩猎期间独占 rootfs.ext4，用户 GUI 线勿并行启动。
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))
import engine  # noqa: E402  (find_qemu)

ROOT = engine.ROOT
PORT = 4445
SPORT = int(os.environ.get("SERIAL_TCP", "4446"))
KEEP = os.environ.get("KEEP") == "1"
SERIAL = "/tmp/framehunt-serial.log"
REPORT = "/tmp/framehunt-report.txt"
MARKERS = [
    rb"Running in system mode",      # systemd 起来
    rb"login:",                       # 串口登录提示
    rb"Ubuntu 26",                    # issue 横幅
]

cmd = [
    engine.find_qemu(), "-M", "rk3588-lite",
    "-smp", os.environ.get("SMP", "8"), "-m", "2G",
    "-display", "none", "-no-reboot",
    # 串口走 chardev：TCP（sercmd.py 取证）+ logfile（时间线标记）两用
    "-chardev", f"socket,id=ser0,host=127.0.0.1,port={SPORT},server=on,"
                f"wait=off,logfile={SERIAL}",
    "-serial", "chardev:ser0",
    "-monitor", f"tcp:127.0.0.1:{PORT},server,nowait",
    "-kernel", str(ROOT / "third_party/src/rk3588-topeet/linux/arch/arm64/boot/Image"),
    "-drive", f"if=none,id=hd,file={ROOT / 'out/rk3588-topeet/rootfs.ext4'},format=raw",
    "-device", "virtio-blk-device,drive=hd",
    "-dtb", str(ROOT / "boards/rk3588-topeet/sim/rk3588-topeet-board.dtb"),
    "-append",
    "console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 root=/dev/vda rw rootwait "
    "init=/sbin/init panic=-1 cpuidle.off=1 drm_client_lib.active=none "
    + ("quiet loglevel=2 " if os.environ.get("FAST") == "1" else "")
    + "systemd.mask=serial-getty@ttyFIQ0.service "
    "systemd.mask=wpa_supplicant@wlan0.service "
    "systemd.mask=plymouth-start.service "
    "systemd.mask=plymouth-quit-wait.service",
]

tmo = int(sys.argv[1]) if len(sys.argv) > 1 else 420
lines = []
t0 = time.time()
marks = {}


def note(tag):
    marks[tag] = time.time() - t0
    lines.append(f"[{marks[tag]:7.1f}s] {tag}")


def serial_read():
    try:
        with open(SERIAL, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return b""


def poll_frame(idx):
    """截图一轮；返回 True 表示已就绪"""
    r = subprocess.run(
        [sys.executable, str(SIM / "fbdump.py"), f"/tmp/framehunt-{idx}.png"],
        capture_output=True, text=True, timeout=90,
        env={**os.environ, "MONITOR": str(PORT)})
    return r.stdout.strip(), r.returncode == 0


if os.path.exists(SERIAL):
    os.unlink(SERIAL)
lines.append(f"framehunt: {cmd[0]} -smp {cmd[3]} timeout {tmo}s")
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
lines.append(f"[{0.0:7.1f}s] qemu pid {proc.pid}")

seen = set()
frames = 0
try:
    while time.time() - t0 < tmo:
        time.sleep(5)
        data = serial_read()
        for pat in MARKERS:
            if pat not in seen and data.find(pat) >= 0:
                seen.add(pat)
                note(f"serial: {pat.decode(errors='replace')}")
        if proc.poll() is not None:
            lines.append("qemu 退出（异常）")
            break
        if frames < 3:
            out, ok = poll_frame(frames)
            if ok:
                note(f"frame {frames}: {out}")
                frames += 1
                if frames == 3:
                    break
    if frames == 0:
        lines.append("超时：未捕获首帧")
finally:
    if KEEP:
        lines.append(f"KEEP：QEMU 留守 pid {proc.pid}（串口 tcp:{SPORT} 监视 tcp:{PORT}）")
    else:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

with open(REPORT, "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
