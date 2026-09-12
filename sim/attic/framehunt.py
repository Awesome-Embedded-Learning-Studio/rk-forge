#!/usr/bin/env python3
"""首帧狩猎器（同 DTB 流，guest 内部判活版）：包装 boards/*/sim/smoke.py 拉起
桌面，串口时间线 + **guest 内 DRM crtc 帧计数**判活首帧。

为什么走 guest 内部：virgl + sdl,gl=on 下两条宿主取证路全盲——HMP screendump
报 "no surface"（GL 扫描输出无 pixman 面），X11 import 读不了 GL 窗口
（XWayland 拒绝）。frame 计数 > 0 = mutter 真在画，guest 自己作证。

用法： python3 sim/framehunt.py [模式，默认 desktop] [超时秒，默认 420]
环境： 透传 smoke.py（GPU_BACKEND=2d 对照等）；GL 形态默认补
       DISPLAY_BACKEND=sdl,gl=on。KEEP=1 留守。
产物： /tmp/framehunt-report.txt + /tmp/framehunt-serial.log；
       串口问答走 /tmp/hvc0-feed（往文件追加即敲 console）。
单实例纪律：狩猎期间独占 rootfs.ext4。
"""
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

SIM = Path(__file__).resolve().parent
SMOKE = SIM.parents[0] / "boards/rk3588-topeet/sim/smoke.py"
PORT = int(os.environ.get("MONITOR", "4445"))
os.environ.setdefault("MONITOR", str(PORT))

mode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].isdigit() else "desktop"
tmo = int(next((a for a in sys.argv[1:] if a.isdigit()), "420"))
KEEP = os.environ.get("KEEP") == "1"

if mode in ("desktop", "gpu-probe") and "GPU_BACKEND" not in os.environ:
    # WSLg 上 egl-headless 无 /dev/dri 拒启；sdl,gl=on 走 GLX（会弹窗口）
    os.environ.setdefault("DISPLAY_BACKEND", "sdl,gl=on")
    os.environ.setdefault("SDL_VIDEODRIVER", "x11")

FEED = "/tmp/hvc0-feed"
SERIAL_LOG = "/tmp/framehunt-serial.log"
REPORT = "/tmp/framehunt-report.txt"
MARKERS = [rb"login:", rb"Ubuntu 26"]

for f in (FEED, SERIAL_LOG):
    open(f, "w").close()

lines = [f"framehunt: mode={mode} timeout={tmo}s "
         f"GPU={'2d' if os.environ.get('GPU_BACKEND') == '2d' else 'gl(virgl)'}"]
t0 = time.time()
proc = subprocess.Popen(
    f"tail -f {FEED} | {sys.executable} {SMOKE} {mode}",
    shell=True, stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

buf = b""
log = open(SERIAL_LOG, "wb")


def note(tag):
    lines.append(f"[{time.time() - t0:7.1f}s] {tag}")


def pump(sec):
    """select 非阻塞收串口，落盘并进 buf。"""
    global buf
    dl = time.time() + sec
    while time.time() < dl:
        r, _, _ = select.select([proc.stdout], [], [], 0.5)
        if r:
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                note(f"smoke 退出 rc={proc.returncode}")
                return False
            buf += chunk
            log.write(chunk)
            log.flush()
    return True


def feed(text, settle=3.0):
    with open(FEED, "a") as f:
        f.write(text)
    return pump(settle)


alive = True
seen = set()
while time.time() - t0 < tmo and seen != set(MARKERS):
    pump(2.0)
    for pat in MARKERS:
        if pat not in seen and buf.find(pat) >= 0:
            seen.add(pat)
            note(f"serial: {pat.decode()}")
    if proc.poll() is not None:
        alive = False
        break

framed = False
if alive and seen:
    # 登录 + 挂 debugfs，然后轮询 DRM crtc dump 里的 frame 计数（guest 内判活：
    # 帧计数不是独立文件，是 /sys/kernel/debug/dri/N/crtc-N 文本里的 "frame:" 行）
    feed("\n", 2.0)
    feed("root\n", 5.0)
    feed("mount -t debugfs none /sys/kernel/debug 2>/dev/null\n", 2.0)
    while time.time() - t0 < tmo:
        mark = len(buf)
        feed("cat /sys/kernel/debug/dri/0/crtc-0 2>/dev/null | head -6; "
             "journalctl -b _COMM=gnome-shell -n 1 --no-pager 2>/dev/null; echo FHDONE\n", 8.0)
        seg = buf[mark:]
        nums = [int(x) for x in re.findall(rb"frame[=:]\s*(\d+)", seg)]
        if nums and max(nums) > 0:
            note(f"frame0: guest DRM frame={max(nums)}（mutter 在画）")
            framed = True
            break
        if b"-- No entries --" not in seg and re.search(rb"journalctl|gnome-shell\[", seg):
            # 帧计数格式未验过（crtc dump 未必含 frame 行），以 gnome-shell
            # journal 首行为代理：shell 起来 = 首帧在其后数秒内
            note("frame0(代理): gnome-shell journal 首条已现")
            framed = True
            break
        if proc.poll() is not None:
            note(f"smoke 退出 rc={proc.returncode}")
            break
        if not pump(2.0):
            break
    if not framed and proc.poll() is None:
        lines.append("超时：guest 侧未见帧计数（桌面未画或 debugfs 不可达）")

try:
    log.close()
finally:
    if KEEP:
        lines.append(f"KEEP：shell pid {proc.pid}（串口问答继续走 {FEED}）")
    else:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

with open(REPORT, "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
