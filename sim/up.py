#!/usr/bin/env python3
"""研究机启动器：一条命令冷启 rk3588-lite（标准已验证形态）。

用法：
  python3 sim/up.py              # 后台无窗（默认 2h）
  python3 sim/up.py --window     # SDL 弹窗（WSLg 桌面 1024×600）
  python3 sim/up.py 3600         # 自定时限（秒）
替代 setsid+nohup 的 shell 形态：无 nohup 噪音、日志干净、
启动后自检端口并给出观察命令。"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def port_live(p):
    try:
        socket.create_connection(("127.0.0.1", p), timeout=1).close()
        return True
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    window = "--window" in args
    nums = [a for a in args if a.isdigit()]
    dur = nums[0] if nums else "7200"

    if port_live(4446) or port_live(4449):
        print("端口 4446/4449 已被占用——旧机器还活着。")
        print("  停旧机: pgrep -f qemu-system-aarch64 | xargs -r kill")
        return 1

    env = dict(os.environ,
               FSQUAD_REPAINT="1", GPUDBG="1", FSQUAD="1",
               FSQUAD_REALIMG="1", FSQUAD_BGFULLRES="1", GDM="1",
               SCMIDBG="1")
    if window:
        env["DISPLAYMODE"] = "sdl"

    out = open(ROOT / "sim/logs/resboot.out", "w")
    subprocess.Popen(
        [sys.executable, str(ROOT / "sim/resboot.py"), dur],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
        stdout=out, stderr=subprocess.STDOUT,
        start_new_session=True)
    out.close()

    for _ in range(100):
        if port_live(4446):
            break
        time.sleep(0.2)
    if not port_live(4446):
        print("启动后 20s 未见 4446 监听——查 sim/logs/resboot.out")
        return 1

    # note 79 日用形态：virtio 键鼠在场时关 gt911 宿主鼠标桥
    # （两路 grab 抢窗口拖动）。HMP 运行时关，机器默认 on。
    try:
        sk = socket.create_connection(("127.0.0.1", 4449), timeout=5)
        sk.settimeout(0.4)
        sk.sendall(b"\x03\ngt911_mouse off\n")
        time.sleep(0.5)
        sk.close()
    except Exception:
        pass

    print(f"机器已启动（{'SDL 弹窗' if window else '后台无窗'}，"
          f"限时 {dur}s；键鼠=SDL 窗口→virtio，gt911 桥已让位）")
    print("  ~5min 后 GDM 出壁纸（TCG 软件仿真，慢是常态）。")
    print("  截屏: python3 sim/shot.py   判活: ss -tln | grep 4446")
    print("── 串口启动日志（Ctrl-C 只停看日志，机器照跑）──")
    ser = ROOT / "sim/logs/scmi-serial.log"
    ser.write_text("")          # 清旧轮日志，跟的是本次启动
    pos = 0
    try:
        while True:
            data = ser.read_bytes()
            if len(data) > pos:
                sys.stdout.write(data[pos:].decode(errors="replace"))
                sys.stdout.flush()
                pos = len(data)
            # 测活走 monitor 口（4446 串口 chardev 单连接，反复连
            # 会自扰）；monitor 断连即机器真死
            if not port_live(4449):
                print("\n[机器已退出]")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[停止跟随日志；机器继续运行]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
