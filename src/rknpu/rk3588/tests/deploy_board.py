"""构建、部署并预检 RK3588 测试资产到指定 rootfs 的 /opt/rknn-verify

用法: python3 src/rknpu/rk3588/tests/deploy_board.py [--rootfs <dir>]
默认 rootfs = out/rk3588-topeet/rootfs(TFTP+NFS 启动回路)。
forge stage-rootfs 会整树重建 rootfs,重建后重跑本脚本即可恢复。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from paths import OWN, MODELS as MODEL_ROOT, ROOTFS, VENDOR as VENDOR_DIR
from build_board import build

MODELS = [MODEL_ROOT / 'mobilenetv2_fp.rknn', MODEL_ROOT / 'mobilenetv2_i8.rknn'] + sorted((MODEL_ROOT / 'zoo').glob('*.rknn'))
VENDOR = VENDOR_DIR / 'librknnrt.so'


def atomic_copy(src, dest, mode):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.rknpu-test-', dir=dest.parent)
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.chmod(tmp, mode)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def check_elf(path: Path, rootfs: Path, want_exec: bool) -> list[str]:
    """静态预检: aarch64 架构 + DT_NEEDED 在 rootfs 内可解析。"""
    problems = []
    out = subprocess.run(["file", str(path)], capture_output=True,
                         text=True).stdout
    if "aarch64" not in out:
        problems.append(f"{path.name}: 非 aarch64 ({out.strip()})")
    if want_exec and "executable" not in out and "shared object" not in out:
        problems.append(f"{path.name}: 非 ELF({out.strip()})")
    dyn = subprocess.run(["readelf", "-d", str(path)], capture_output=True,
                         text=True).stdout
    for line in dyn.splitlines():
        if "NEEDED" not in line:
            continue
        lib = line.split("[")[-1].rstrip("]")
        if lib == "librknnrt.so":   # 由 run.sh 的 LD_LIBRARY_PATH 提供
            continue
        hits = [rootfs / "lib" / lib, rootfs / "usr/lib" / lib]
        if not any(h.exists() for h in hits):
            problems.append(f"{path.name}: rootfs 缺 {lib}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rootfs", default=str(ROOTFS))
    args = ap.parse_args()
    rootfs = Path(args.rootfs)
    if not (rootfs / "bin/busybox").is_file():
        print(f"!! 不是有效 rootfs: {rootfs}")
        return 1

    bundle = build()
    files = [(OWN / 'librknnrt.so', 'own/librknnrt.so', 0o644), (VENDOR, 'vendor/librknnrt.so', 0o644)]
    files += [(p, str(p.relative_to(bundle)), 0o755 if p.stat().st_mode & 0o111 and p.suffix != '.so' else 0o644)
              for p in sorted(bundle.rglob('*')) if p.is_file()]
    missing = [str(p) for p, _, _ in files if not p.is_file()] + [str(p) for p in MODELS if not p.is_file()]
    if missing:
        print('Missing deployment inputs: ' + ', '.join(missing))
        return 1
    dest = rootfs / "opt/rknn-verify"
    dest.mkdir(parents=True, exist_ok=True)
    for sub in ("own", "vendor", "bin", "src", "models"):
        (dest / sub).mkdir(exist_ok=True)

    n = 0
    for src, rel, mode in files:
        if not src.is_file():
            print(f"!! 缺产物: {src}")
            return 1
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(src, out, mode)
        n += 1
    for m in MODELS:
        if not m.is_file():
            print(f"!! 缺模型: {m}")
            return 1
        out = dest / "models" / m.name
        if not out.exists() or out.stat().st_size != m.stat().st_size:
            atomic_copy(m, out, 0o644)
        n += 1

    # 预检全部 ELF 与板端脚本。
    problems = []
    for rel in ("own/librknnrt.so", "vendor/librknnrt.so", "bin/legacy_trace.so",
                "bin/board_harness", "multicore/media_demo"):
        problems += check_elf(dest / rel, rootfs, want_exec=not rel.endswith('.so'))
    scripts = ("run.sh", "verify_legacy_sync.sh", "verify_boot_cleanup.sh", "multicore/run.sh")
    for rel in scripts:
        if subprocess.run(["sh", "-n", str(dest / rel)]).returncode != 0:
            problems.append(rel + ": sh 语法错误")

    print(f"部署 {n} 件 → {dest}")
    if problems:
        print("!! 预检不过:")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("预检全绿: aarch64×5 / 依赖闭包 / 4 份 shell 语法")
    print(f"板上: cd /opt/rknn-verify && ./run.sh            # 全量(9 模型)")
    print(f"      ./run.sh models/mobilenetv2_fp.rknn  # 单模型冒烟")
    return 0


if __name__ == "__main__":
    sys.exit(main())
