#!/usr/bin/env python3
"""文件推 guest（send3 落库版）：240 字符分块 base64 + md5 校验。
依赖 sim/serx.py 同款串口会话。
用法： CMD_TIMEOUT=90 python3 sim/sendfile.py <本地> <远端>"""
import base64
import hashlib
import os
import re
import socket
import sys
import time

LOCAL, REMOTE = sys.argv[1], sys.argv[2]
PORT = int(os.environ.get("SERPORT", "4446"))
CTMO = float(os.environ.get("CMD_TIMEOUT", "20"))

data = open(LOCAL, "rb").read()
md5 = hashlib.md5(data).hexdigest()[:8]
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


def run(c, tmo=CTMO):
    global buf
    sk.sendall(b"export PS1='@@ '\n")
    drain(1.0)
    buf = ""
    sk.sendall(c.encode() + b"\n")
    dl = time.time() + tmo
    while time.time() < dl:
        drain(1.0)
        if re.search(r"@@\s*$", " ".join(tail3())):
            break
    return buf


sk.sendall(b"\x03")
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
    print("登录失败\n" + buf[-400:])
    sys.exit(1)

run(f"rm -f {REMOTE}.b64 {REMOTE}")
b64 = base64.b64encode(data).decode()
CH = 240
for i in range(0, len(b64), CH):
    run(f"printf %s '{b64[i:i + CH]}' >> {REMOTE}.b64", tmo=10)
out = run(f"base64 -d {REMOTE}.b64 > {REMOTE} 2>/dev/null;"
          f" md5sum {REMOTE} | cut -c1-8; wc -c < {REMOTE}")
m = re.search(r"([0-9a-f]{8})\s*\n\s*(\d+)", out)
if m and m.group(1) == md5 and int(m.group(2)) == len(data):
    run(f"rm -f {REMOTE}.b64")
    print(f"remote md5: {m.group(1)} 期望: {md5} len: {len(data)}")
else:
    print(f"校验失败: {m.groups() if m else 'no output'} 期望 {md5}/{len(data)}")
    sys.exit(1)
