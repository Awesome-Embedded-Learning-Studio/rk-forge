#!/usr/bin/env python3
"""span 块拓扑分析（note 114：staging 内容 2D 块置换取证）。

对 STGDUMPSPAN.<n>：在图像域做 2D 块匹配（块 B×B px），输出每块的
最佳 (dx,dy) 位移表——块粒度/置换模式一眼定谳（页置换 vs 大块搬运
vs 原位）。"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from verify_screen import load_png  # noqa: E402

REF = ("out/rk3588-topeet/ubuntu-rootfs.work/usr/share/backgrounds/"
       "warty-final-ubuntu.png")
W, H, STRIDE = 3840, 2160, 15360


def px_at(d, x, y):
    o = y * STRIDE + x * 4
    return d[o], d[o + 1], d[o + 2]


def block_match(d, refpx, bx, by, B, R):
    """(bx,by) 起 B×B 块 vs 参照同位置 ±R 搜索，返回 (mad,dx,dy)。"""
    best = (1e9, 0, 0)
    for dy in range(-R, R + 1, 8):
        ry = by + dy
        if ry < 0 or ry + B > H:
            continue
        for dx in range(-R, R + 1, 8):
            rx = bx + dx
            if rx < 0 or rx + B > W:
                continue
            td = tn = 0
            for yy in range(0, B, 16):
                for xx in range(0, B, 16):
                    s = px_at(d, bx + xx, by + yy)
                    i = ((ry + yy) * W + rx + xx) * 3
                    td += abs(s[0] - refpx[i]) + abs(s[1] - refpx[i + 1]) \
                        + abs(s[2] - refpx[i + 2])
                    tn += 3
            m = td / tn
            if m < best[0]:
                best = (m, dx, dy)
    return best


def main():
    path = sys.argv[1]
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    R = int(sys.argv[3]) if len(sys.argv) > 3 else 512
    d = open(path, "rb").read()
    _, _, refpx = load_png(REF)
    print(f"{path}: 块 {B}px, 搜索 ±{R}")
    for by in range(0, H - B, B * 2):
        row = []
        for bx in range(0, W - B, B):
            m, dx, dy = block_match(d, refpx, bx, by, B, R)
            mark = "." if (m < 3 and dx == 0 and dy == 0) else \
                   ("#" if m < 5 else "?")
            row.append(f"{mark}({dx:+4d},{dy:+3d},{m:4.1f})")
        print(f"  y={by:4d}: " + " ".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
