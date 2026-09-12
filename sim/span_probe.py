#!/usr/bin/env python3
"""span dump 行识别器（note 114：mutter 分块上传取证）。

对 STGDUMPSPAN.<n>（spp 起 34MB PA 线性 dump）：抽样若干行，在参照
壁纸全部 2160 行里做恒偏补偿匹配（greeter 暗化≈-8/通道），输出
span 行 → 参照行 的映射——线性段=块携带的图像行窗，断点=块边界/
foreign 区。
用法：python3 sim/span_probe.py sim/logs/span.0 [行号,行号,...]"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from verify_screen import load_png  # noqa: E402

REF = ("out/rk3588-topeet/ubuntu-rootfs.work/usr/share/backgrounds/"
       "warty-final-ubuntu.png")
W, H, STRIDE = 3840, 2160, 15360
SPP_ROW0_OFF = 0        # span dump 行 0 = spp 偏移 0


def best_ref_row(dump, drow, refpx):
    """dump 第 drow 行 vs 参照全行（步 64px 抽样，恒偏补偿 MAD）。"""
    off = drow * STRIDE
    if off + STRIDE > len(dump):
        return None
    best = (1e9, -1, (0, 0, 0))
    for y in range(0, H):
        td = [0, 0, 0]
        n = 0
        for x in range(0, W, 64):
            i = (y * W + x) * 3
            o = off + x * 4
            td[0] += dump[o] - refpx[i]
            td[1] += dump[o + 1] - refpx[i + 1]
            td[2] += dump[o + 2] - refpx[i + 2]
            n += 1
        delta = [t / n for t in td]
        if any(abs(d) > 24 for d in delta):
            continue
        m = 0
        for x in range(0, W, 64):
            i = (y * W + x) * 3
            o = off + x * 4
            m += abs(dump[o] - refpx[i] - delta[0])
            m += abs(dump[o + 1] - refpx[i + 1] - delta[1])
            m += abs(dump[o + 2] - refpx[i + 2] - delta[2])
        m /= n * 3
        if m < best[0]:
            best = (m, y, tuple(round(d, 1) for d in delta))
    return best


def main():
    path = sys.argv[1]
    dump = open(path, "rb").read()
    _, _, refpx = load_png(REF)
    rows = ([int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2
            else list(range(50, 2200, 150)))
    print(f"{path}: {len(dump):#x}B, 行数={len(dump) // STRIDE}")
    prev_map = None
    for r in rows:
        m, y, dl = best_ref_row(dump, r, refpx)
        tag = ""
        if prev_map is not None and y >= 0:
            step = y - prev_map
            tag = f"  行进={step:+d}" + ("  ←断点" if abs(step - (r - prev_r)) > 2
                                        else "")
        print(f"  span 行 {r:4d} → ref 行 {y:4d}  mad={m:5.2f} delta={dl}{tag}")
        if y >= 0:
            prev_map, prev_r = y, r
    return 0


if __name__ == "__main__":
    sys.exit(main())
