"""replay 对拍器: 两次 qemu+fakekern 装置运行的 GEM dump 逐字节比对

用法:
  python3 replay_diff.py <dirA> <dirB> [--task-only]

dirA/B = fakekern_dump.so 的 RKNN_DUMP_DIR 产出目录(各含 s1_gem*.bin)。
替代引擎的验收门槛 = 全部 GEM 与 vendor blob 的 dump byte-exact。
"""
import argparse
import glob
import os


def load(d):
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "s*_gem*.bin"))):
        name = os.path.basename(p)
        # 保留提交序号。不同提交的同一 GEM 是不同证据，不能相互覆盖。
        with open(p, "rb") as f:
            out[name] = f.read()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirA")
    ap.add_argument("dirB")
    ap.add_argument("--task-only", action="store_true")
    args = ap.parse_args()

    a, b = load(args.dirA), load(args.dirB)
    keys = sorted(set(a) | set(b))
    if args.task_only:
        keys = [k for k in keys if k.split("_", 1)[-1].startswith(("gem3_", "gem2_"))]
    all_ok = bool(keys)
    if not keys:
        print("MISSING: no selected GEM snapshots")
    for k in keys:
        if k not in a or k not in b:
            print(f"MISSING: {k} 不在两个目录都存在 (A={k in a}, B={k in b})")
            all_ok = False
            continue
        if a[k] == b[k]:
            print(f"OK      {k} ({len(a[k])}B) byte-exact")
            continue
        all_ok = False
        n = min(len(a[k]), len(b[k]))
        first = next((i for i in range(n) if a[k][i] != b[k][i]), n)
        diff = sum(1 for i in range(n) if a[k][i] != b[k][i])
        print(f"DIFF    {k}: 首异 @ {first:#x}, {diff}/{n} 字节不同 (len {len(a[k])} vs {len(b[k])})")
        lo = max(0, first - 16)
        print(f"        A: {a[k][lo:first+16].hex(' ')}")
        print(f"        B: {b[k][lo:first+16].hex(' ')}")
    print("RESULT:", "PASS byte-exact" if all_ok else "FAIL")
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
