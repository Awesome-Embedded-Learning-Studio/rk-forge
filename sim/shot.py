#!/usr/bin/env python3
"""一键截屏：monitor 4449 screendump → 转 PNG 拷 Windows 桌面。

用法：python3 sim/shot.py [文件名(不带扩展)]
默认名 rk_screen。机器判活失败时提示先启动。"""
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESKTOP = Path("/mnt/c/Users/CharlieChen/Desktop")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "rk_screen"
    try:
        sk = socket.create_connection(("127.0.0.1", 4449), timeout=5)
    except Exception:
        print("机器未启动（4449 无监听）。启动命令：")
        print("  cd ~/rk-forge && FSQUAD_REPAINT=1 GPUDBG=1 FSQUAD=1 "
              "FSQUAD_REALIMG=1 FSQUAD_BGFULLRES=1 GDM=1 "
              "setsid nohup python3 sim/resboot.py 7200 "
              "> sim/logs/resboot.out 2>&1 &")
        return 1
    sk.settimeout(0.4)
    sk.sendall(b"\x03\n")
    time.sleep(0.3)
    sk.sendall(f"screendump sim/logs/{name}.ppm\n".encode())
    dl = time.time() + 8
    while time.time() < dl:
        try:
            if not sk.recv(65536):
                break
        except Exception:
            pass
    sk.close()
    ppm = ROOT / f"sim/logs/{name}.ppm"
    if not ppm.exists():
        print("screendump 失败")
        return 1
    png = DESKTOP / f"{name}.png"
    subprocess.run(["convert", str(ppm), str(png)], check=True)
    print(f"已放桌面: {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
