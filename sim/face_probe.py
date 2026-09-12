#!/usr/bin/env python3
"""脸区悬案离线探针 v2（note 112 §6 刀口，note 114 配套）。

v1 教训：暗壁纸平坦区在 ±14 容差下全互相匹配=无判别力。v2 改用：
  MAD（平均绝对差）为主指标 + 高对比指纹段（眼/鼻行）全文搜索；
  显式对照 +2MB 位移假说（face-xlate 实测该 run 翻译=线性+2MB）。
"""
import sys
import math
from collections import Counter

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from verify_screen import load_png  # noqa: E402

REF = ("out/rk3588-topeet/ubuntu-rootfs.work/usr/share/"
       "backgrounds/warty-final-ubuntu.png")
STRIDE = 3840 * 4
DUMP_BASE = 12 << 20
W = 3840


def ref_rgba_rows(w, h, px, y0, y1):
    """参照行 → RGBA(α=0 通配) 字节，[y0,y1)"""
    rows = {}
    for y in range(y0, y1):
        row = bytearray(w * 4)
        base = y * w * 3
        for x in range(w):
            row[x * 4] = px[base + x * 3]
            row[x * 4 + 1] = px[base + x * 3 + 1]
            row[x * 4 + 2] = px[base + x * 3 + 2]
        rows[y] = bytes(row)
    return rows


def mad_span(dump, off, row, step_px):
    """MAD over RGB triples (skip α)。返回 (mad, n)。"""
    td = tn = 0
    n = len(row) // 4
    for i in range(0, n, step_px):
        o = off + i * 4
        if o + 2 >= len(dump):
            break
        td += abs(dump[o] - row[i * 4]) + abs(dump[o + 1] - row[i * 4 + 1]) \
            + abs(dump[o + 2] - row[i * 4 + 2])
        tn += 3
    return (td / tn if tn else 1e9), tn


def block_compare(dump, rows, tag, shift):
    """按 1MB 块出 MAD：期望字节=dump 覆盖的参照行，位移 shift 试探。"""
    out = []
    for b in range(len(dump) >> 20):
        td = tn = 0
        for y, row in rows.items():
            row_off = y * STRIDE - DUMP_BASE + shift
            lo = max(b << 20, row_off)
            hi = min((b + 1) << 20, row_off + len(row))
            if lo >= hi:
                continue
            skip_px = (lo - row_off) // 4
            m, n = mad_span(dump, lo, row[skip_px * 4:], 8)
            td += m * n
            tn += n
        out.append(td / tn if tn else -1)
    print(f"  {tag}: " + " ".join(f"{x:5.1f}" if x >= 0 else "   --"
                                  for x in out))


def fingerprint(dump, rows, y, x0, npx):
    row = rows[y]
    seg = row[x0 * 4:(x0 + npx) * 4]
    best = []
    for off in range(0, len(dump) - len(seg), 4):
        m, _ = mad_span(dump, off, seg, 3)
        if m < 8:
            best.append((m, off))
    best.sort()
    exp = y * STRIDE + x0 * 4 - DUMP_BASE
    top = "  ".join(f"mad={m:.1f}@+{o:#x}(Δ{o - exp:+#x})" for m, o in best[:4])
    print(f"  y={y} x={x0}+{npx}px 期望原位=+{exp:#x}: {top or '无<8命中'}")


def main():
    dump = open(sys.argv[1] if len(sys.argv) > 1 else "sim/logs/face.bin",
                "rb").read()
    w, h, px = load_png(REF)
    rows = ref_rgba_rows(w, h, px, 780, 1230)
    print(f"dump={len(dump):#x}B  覆盖参照行 {DUMP_BASE // STRIDE}-"
          f"{(DUMP_BASE + len(dump)) // STRIDE}  stride={STRIDE:#x}")
    print("== 逐 1MB MAD（0=精确重合；暗区基底≈壁纸行间方差，参照系见下）")
    # 参照系：参照自身错行对照（y 错 1 行的 MAD 基底）
    base = mad_span(rows[900] + b"\0" * 0, 0, rows[901], 4)[0]
    print(f"  （错 1 行 MAD 基底={base:.1f}）")
    block_compare(dump, rows, "原位    ", 0)
    block_compare(dump, rows, "位移+2MB", 2 << 20)
    print("== 高对比指纹段全文搜索（mad<8 视为命中，Δ=命中-原位）")
    fingerprint(dump, rows, 990, 1500, 900)    # 眼行
    fingerprint(dump, rows, 1090, 1500, 900)   # 鼻行
    fingerprint(dump, rows, 830, 1500, 900)    # 额/耳行
    fingerprint(dump, rows, 990, 300, 600)     # 眼行左远端（背景对照）
    return 0


if __name__ == "__main__":
    sys.exit(main())
