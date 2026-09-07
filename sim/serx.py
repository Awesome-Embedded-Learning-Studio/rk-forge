#!/usr/bin/env python3
"""串口会话韧性客户端（sercmd2 落库版）：rk-forge/rk-forge 登录、
$/#/@@ 多提示符判定、login 提示检测、命令超时可调。
用法： CMD_TIMEOUT=60 python3 sim/serx.py [端口] "命令" ..."""
import os
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4446
CMDS = sys.argv[2:] or ["true"]
CTMO = float(os.environ.get("CMD_TIMEOUT", "20"))

sk = socket.create_connection(("127.0.0.1", PORT), timeout=5)
sk.settimeout(0.3)
buf = ""


def drain(sec):
    global buf
    dl = time.time() + sec
    while time.time() < dl:
        try:
            d = sk.recv(65536)
            if not d:
                break
            buf += d.decode(errors="replace")
        except Exception:
            pass


def tail3():
    return [l for l in buf.strip().splitlines()[-3:]]


sk.sendall(b"\x03")        # 预踢残留会话
drain(1.0)
sk.sendall(b"\n")
drain(2.0)
state = "shell" if re.search(r"(@@|#|\$)\s*$", " ".join(tail3())) else "login"
if state == "login":
    dl = time.time() + 120
    while time.time() < dl:
        drain(2.0)
        joined = " ".join(tail3())
        if state == "login" and re.search(r"login:\s*$", joined):
            sk.sendall(b"rk-forge\n")
            state = "auth"
            buf = ""
            continue
        if state == "auth" and re.search(r"[Pp]assword", joined):
            sk.sendall(b"rk-forge\n")
            buf = ""
            continue
        if state == "auth" and re.search(r"[$#]\s*$", joined):
            state = "shell"
            break

if state != "shell":
    print(f"登录失败（state={state}）\n" + buf[-600:])
    sys.exit(1)

for c in CMDS:
    buf += f"\n==== CMD: {c}\n"
    sk.sendall(b"export PS1='@@ '\n")
    drain(1.5)
    sk.sendall(c.encode() + b"\n")
    dl = time.time() + CTMO
    while time.time() < dl:
        drain(1.5)
        if re.search(r"@@\s*$", " ".join(tail3())):
            break
sk.close()
print(buf[-14000:])
