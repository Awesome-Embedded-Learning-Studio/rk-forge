"""sim 引擎：两板 smoke 共用的拉起/断言/存活浸泡机制。

板卡入口在 boards/<board>/sim/smoke.py（板 implied by 位置），本模块只放
与板无关的机制：QEMU 发现、dtb 新鲜度、交互直入、--check 断言、SOAK 浸泡。
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

ROOT = Path(__file__).resolve().parents[1]


def find_qemu() -> str:
    env = os.environ.get("QEMU")
    if env:
        return env
    local = ROOT / "third_party/qemu/build/qemu-system-aarch64"
    if os.name == "nt":
        local = local.with_suffix(".exe")
    return str(local) if local.exists() else "qemu-system-aarch64"


def ensure_dtb(dts: Path, dtb: Path, linux_include: Path) -> None:
    """dtb 缺失或比 dts 旧时重编（需 dtc + 内核 include 树）"""
    if dtb.exists() and dtb.stat().st_mtime >= dts.stat().st_mtime:
        return
    if not shutil.which("dtc") or not (linux_include / "dt-bindings").is_dir():
        sys.exit(f"{dtb.name} 需要从 {dts.name} 重编：请安装 dtc 并确保内核树存在")
    with open(dtb, "wb") as f:
        pre = subprocess.Popen(
            ["cpp", "-nostdinc", "-I", str(linux_include), "-undef",
             "-x", "assembler-with-cpp", str(dts)], stdout=subprocess.PIPE)
        post = subprocess.Popen(
            ["dtc", "-@", "-I", "dts", "-O", "dtb", "-o", "-", "-"],
            stdin=pre.stdout, stdout=f)
        pre.stdout.close()
        post.communicate()
        if pre.wait() or post.returncode:
            sys.exit("dtb 重编失败")
    print(f"[sim] {dtb.name} 已从 dts 重新生成")


def soakify(cmd: list, seconds: int):
    """存活浸泡：去掉自动关机开关，改为 5s 心跳节拍；返回 (feed, pats, tmo)"""
    for i, a in enumerate(cmd):
        if a == "-append":
            cmd[i + 1] = cmd[i + 1].replace("rk.smoke=1", "")
    beats = seconds // 5
    feed = [(8, b"echo BEAT-0\n")]
    feed += [(5, f"echo BEAT-{n}\n".encode()) for n in range(1, beats)]
    feed.append((3, b"poweroff -f\n"))
    return feed, [f"BEAT-{n}".encode() for n in range(beats)], seconds + 150


def run(mode: str, board: str, cmd: list, pats, feed, tmo: int, interactive: bool):
    """交互直入或 --check 断言；返回进程退出码（断言失败为 1）"""
    if interactive:
        for i, a in enumerate(cmd):
            if a == "-append":
                cmd[i + 1] = cmd[i + 1].replace("rk.smoke=1", "")
                break
        return subprocess.run(cmd).returncode

    log_path = Path(os.environ.get("LOG") or Path(tempfile.gettempdir())
                    / f"sim-{board}-{mode}-boot.log")
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
    return 1 if fails else 0
