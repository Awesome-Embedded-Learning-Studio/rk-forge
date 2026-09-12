#!/usr/bin/env python3
"""稳定性冒烟监视（note 116 收官配套）。

每 2 分钟：monitor 4449 screendump → verify_screen.py 判决 →
串口日志 grep 异常。结果追加 sim/logs/smoke.log，供人工复核。
Ctrl-C 或机器死（端口失活）即止。"""
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ("out/rk3588-topeet/ubuntu-rootfs.work/usr/share/"
       "backgrounds/warty-final-ubuntu.png")


def mc(cmd, wait=8.0):
    sk = socket.create_connection(("127.0.0.1", 4449), timeout=5)
    sk.settimeout(0.4)
    sk.sendall(b"\x03\n")
    time.sleep(0.3)
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
    sk.close()
    return out.decode(errors="replace")


def alive():
    try:
        socket.create_connection(("127.0.0.1", 4449), timeout=3).close()
        return True
    except Exception:
        return False


def main():
    log = open(ROOT / "sim/logs/smoke.log", "a", buffering=1)
    n = 0
    while True:
        n += 1
        ts = time.strftime("%H:%M:%S")
        if not alive():
            log.write(f"{ts} #{n} MONITOR-DEAD 端口 4449 失活\n")
            break
        ppm = ROOT / f"sim/logs/smoke_{n:03d}.ppm"
        mc(f"screendump {ppm}")
        if not ppm.exists():
            log.write(f"{ts} #{n} screendump 失败\n")
            time.sleep(120)
            continue
        r = subprocess.run(
            [sys.executable, str(ROOT / "sim/verify_screen.py"), str(ppm)],
            capture_output=True, text=True, cwd=ROOT)
        verdict = "?"
        for line in r.stdout.splitlines():
            if "verdict" in line:
                verdict = line.split('"')[-2] if '"' in line else line
                break
        # 串口异常扫描（增量：上次读到的位置）
        sl = ROOT / "sim/logs/scmi-serial.log"
        bad = ""
        try:
            data = sl.read_bytes()
            off = getattr(main, "_seroff", 0)
            chunk = data[off:]
            main._seroff = len(data)
            for pat in (b"Unable to handle", b"Internal error",
                        b"panic", b"BUG:"):
                if pat in chunk:
                    bad += pat.decode() + " "
        except Exception:
            pass
        log.write(f"{ts} #{n} {verdict} rc={r.returncode} "
                  f"{'串口异常: ' + bad if bad else '串口净'}\n")
        time.sleep(120)


if __name__ == "__main__":
    main()
