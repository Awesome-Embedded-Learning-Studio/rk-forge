#!/usr/bin/env python3
"""串口会话客户端：连 QEMU 串口 TCP（-serial tcp:PORT,server,nowait），等
login 提示、登录 root（空密码）、执行命令、回传输出。自动化取证主力。

用法： python3 sercmd.py [端口] "命令1" "命令2" ...
注意：QEMU 串口 server,nowait 不缓存未连接前的输出——请在 login 提示
出现的时间窗内连接（开机后 ~35s 起 login 常驻，随时可连）。
"""
import os
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4446
CMDS = sys.argv[2:] or ["true"]
# TCG 仿真里 journalctl 全量 grep 可能远超默认，允许 env 放宽
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


def tail(n=300):
    return buf[-n:]


# 1) 敲回车看现场：可能是 login 提示，也可能是上一会话的 shell（@@ 提示符）
sk.sendall(b"\n")
drain(2.0)
state = "shell" if re.search(r"(@@|#)\s*$", tail()) else "login"
if state == "login":
    dl = time.time() + 90
    while time.time() < dl:
        drain(2.0)
        t = tail()
        if state == "login" and re.search(r"login:\s*$", t):
            sk.sendall(b"root\n")
            state = "auth"
            buf = ""
            continue
        if state == "auth" and "Password" in t:
            sk.sendall(b"\n")
            buf = ""
            continue
        if state == "auth" and t.rstrip().endswith("#"):
            state = "shell"
            break

if state != "shell":
    print(f"登录失败（state={state}）\n" + tail(600))
    sys.exit(1)

# 2) 执行命令（PS1 设成可识别的结尾标记）
for c in CMDS:
    buf += f"\n==== CMD: {c}\n"
    sk.sendall(b"export PS1='@@ '\n")
    drain(1.5)
    sk.sendall(c.encode() + b"\n")
    dl = time.time() + CTMO
    while time.time() < dl:
        drain(1.5)
        if re.search(r"@@\s*$", tail()):
            break
sk.close()
print(buf[-14000:])
