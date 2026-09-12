#!/usr/bin/env python3
"""M2n 屏幕内容校验（note 113）：用确定性数值判决取代 MCP 读图。

MCP 读图两次把差值 94 的图描述成"完美浣熊"（note 112 §6）——自由
心证不可作证据。本工具把校验拆成三种可复现的数值判定：

  1. 全屏对照（默认）  screen.ppm vs 参照图（PNG/PPM）
     - 参照盒式降采样到屏尺寸，鲁棒估全局色偏（greeter 调光）
     - 64x36 块差网格 + 结构/背景分域统计（结构域=参照边缘密度）
     - 结构块位移场（限界搜索最优匹配偏移）→ 移位/错乱定量
     - 判定线：背景域 p90<=BG_TH 且 结构域 p50<=ST_TH → PASS
     - 产出 diff 热图 PPM（人眼复核用，不作判据）
  2. 1:1 条带对照 --strips   用户令"先 1:1 对比"：整行 3840px 无缩放
     - 每行：原位差 + 限界位移搜索后的最优差 → 对齐保持/破坏逐行定谳
  3. 原始页分类 --classify  staging 脸区悬案武器：dump 出的二进制
     - 每 4KB 页：熵/零占比/ASCII 占比/指针特征（同低字节变高字节
       的 32 位词游程）→ image/pagetable/text/zero/mixed 分类直方图

纯标准库；判定只看数字，MCP/人眼仅复核热图。
"""

import argparse
import json
import math
import os
import struct
import sys
import zlib

BG_TH = 20      # 背景块差阈值（p90 用）
ST_TH = 40      # 结构块差阈值（p50 用）
BLK = 16        # 块尺寸（位移场与块网格一致）


# ---- 图像 IO ---------------------------------------------------------------

def load_ppm(path):
    d = open(path, "rb").read()
    if not d.startswith(b"P6"):
        raise ValueError(f"{path}: 只支持 P6 二进制 PPM")
    parts = d.split(b"\n", 3)
    w, h = map(int, parts[1].split())
    px = parts[3]
    if len(px) < w * h * 3:
        raise ValueError(f"{path}: 数据不足 {len(px)} < {w*h*3}")
    return w, h, px


def load_png(path):
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: 非 PNG")
    pos, idat = 8, b""
    w = h = ct = None
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        if typ == b"IHDR":
            w, h, _, ct = struct.unpack(">IIBB", d[pos + 8:pos + 18])[:4]
        elif typ == b"IDAT":
            idat += d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    ch = {0: 1, 2: 3, 4: 2, 6: 4}.get(ct)
    if ch != 3:
        raise ValueError(f"{path}: 只支持 8bit RGB(colortype 2)，"
                         f"当前 colortype={ct}")
    raw = zlib.decompress(idat)
    stride = w * 3
    out = bytearray(w * h * 3)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(3, stride):
                line[i] = (line[i] + line[i - 3]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - 3] if i >= 3 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bytes(out)


def load_image(path):
    if path.lower().endswith(".ppm"):
        return load_ppm(path)
    return load_png(path)


def save_ppm(path, w, h, px):
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(px)


# ---- 基础量 -----------------------------------------------------------------

def box_resize(px, w, h, w2, h2, step=3):
    """盒式平均降采样（step 为盒内抽样步长，控成本）。"""
    out = bytearray(w2 * h2 * 3)
    for ey in range(h2):
        y0, y1 = ey * h // h2, max(ey * h // h2 + 1, (ey + 1) * h // h2)
        for ex in range(w2):
            x0, x1 = ex * w // w2, max(ex * w // w2 + 1, (ex + 1) * w // w2)
            rr = gg = bb = nn = 0
            for yy in range(y0, y1, step):
                base = yy * w
                for xx in range(x0, x1, step):
                    i = (base + xx) * 3
                    rr += px[i]
                    gg += px[i + 1]
                    bb += px[i + 2]
                    nn += 1
            j = (ey * w2 + ex) * 3
            out[j] = rr // nn
            out[j + 1] = gg // nn
            out[j + 2] = bb // nn
    return bytes(out)


def pchannel0(v):
    """中位数（robust 中心估计）。"""
    s = sorted(v)
    return s[len(s) // 2] if s else 0


def diff_rgb(a, b, i):
    return abs(a[i] - b[i]) + abs(a[i + 1] - b[i + 1]) + abs(a[i + 2] - b[i + 2])
    s = sorted(v)
    return s[len(s) // 2]


def median3(ds):
    return [pchannel0(d) for d in ds]


def edge_density(px, w, h, x0, y0, x1, y1, step=2):
    """区域内平均梯度幅（结构度量，判定结构/背景块用）。"""
    tot = n = 0
    for y in range(max(1, y0), min(h - 1, y1), step):
        base = y * w
        for x in range(max(1, x0), min(w - 1, x1), step):
            i = (base + x) * 3
            gx = abs(px[i + 3] - px[i - 3])
            gy = abs(px[i + 3 * w] - px[i - 3 * w])
            tot += gx + gy
            n += 1
    return tot / max(n, 1)


# ---- 模式 1：全屏对照 --------------------------------------------------------

def verify_full(screen_path, ref_path, out_dir, blk=BLK):
    sw, sh, spx = load_image(screen_path)
    rw, rh, rpx = load_image(ref_path)
    exp = box_resize(rpx, rw, rh, sw, sh) if (rw, rh) != (sw, sh) else rpx

    ds = [[], [], []]
    for y in range(0, sh, 17):
        for x in range(0, sw, 23):
            i = (y * sw + x) * 3
            for k in range(3):
                ds[k].append(spx[i + k] - exp[i + k])
    off = median3(ds)

    def odiff(i):
        return (abs(spx[i] - off[0] - exp[i])
                + abs(spx[i + 1] - off[1] - exp[i + 1])
                + abs(spx[i + 2] - off[2] - exp[i + 2]))

    # 参照边缘密度定结构块
    tx, ty = sw // blk, sh // blk
    bg_diffs, st_diffs = [], []
    block_bad = []
    for by in range(ty):
        for bx in range(tx):
            x0, y0 = bx * blk, by * blk
            dens = edge_density(exp, sw, sh, x0, y0, x0 + blk, y0 + blk)
            tot = n = 0
            for y in range(y0, min(y0 + blk, sh), 2):
                base = y * sw
                for x in range(x0, min(x0 + blk, sw), 2):
                    tot += odiff((base + x) * 3)
                    n += 1
            m = tot / max(n, 1)
            (st_diffs if dens > 6 else bg_diffs).append(m)
            block_bad.append((m, bx, by, dens))

    bg_p90 = quant(bg_diffs, 0.9)
    st_p50 = quant(st_diffs, 0.5)
    st_p90 = quant(st_diffs, 0.9)
    verdict = "PASS" if (bg_p90 <= BG_TH and st_p50 <= ST_TH) else "FAIL"

    # 结构块位移场（限界搜索）
    shifts = []
    worst = sorted(block_bad, reverse=True)[:400]
    for m, bx, by, dens in worst:
        if dens <= 6 or m < ST_TH:
            continue
        x0, y0 = bx * blk, by * blk
        best = (1 << 30, 0, 0)
        for dy in range(-32, 33, 8):
            for dx in range(-32, 33, 8):
                tot = n = 0
                for y in range(max(0, y0 + dy), min(sh - 1, y0 + dy + blk), 4):
                    base = y * sw
                    for x in range(max(0, x0 + dx), min(sw - 1, x0 + dx + blk), 4):
                        i = (base + x) * 3
                        j = ((y0 + (y - y0 - dy)) * sw
                             + x0 + (x - x0 - dx)) * 3
                        if 0 <= j < len(exp) - 2:
                            tot += abs(spx[i] - off[0] - exp[j]) \
                                + abs(spx[i + 1] - off[1] - exp[j + 1]) \
                                + abs(spx[i + 2] - off[2] - exp[j + 2])
                            n += 1
                if n and tot / n < best[0]:
                    best = (tot / n, dx, dy)
        shifts.append((best[1], best[2], best[0]))

    # 热图
    heat = bytearray(sw * sh * 3)
    for y in range(sh):
        for x in range(sw):
            i = (y * sw + x) * 3
            d = min(odiff(i), 255)
            heat[i] = d
            heat[i + 1] = 255 - d
            heat[i + 2] = 128
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        save_ppm(os.path.join(out_dir, "diff-heat.ppm"), sw, sh, bytes(heat))

    from collections import Counter
    hist = Counter((dx, dy) for dx, dy, _ in shifts if dx or dy)
    res = {
        "screen": os.path.basename(screen_path),
        "ref": os.path.basename(ref_path),
        "offset_rgb": off,
        "bg_blocks": len(bg_diffs), "bg_p90": round(bg_p90, 1),
        "st_blocks": len(st_diffs), "st_p50": round(st_p50, 1),
        "st_p90": round(st_p90, 1),
        "shift_mode": hist.most_common(3),
        "verdict": verdict,
        "thresholds": {"bg_p90<=": BG_TH, "st_p50<=": ST_TH},
    }
    return res


def quant(v, q):
    s = sorted(v)
    return s[min(len(s) - 1, int(len(s) * q + 0.5))] if s else 0


# ---- 模式 2：1:1 条带对照 -----------------------------------------------------

def verify_strips(strips_path, ref_path, rows):
    rw, rh, rpx = load_image(ref_path)
    w, h, px = load_ppm(strips_path)      # h == len(rows)
    out = []
    for r, y in enumerate(rows):
        srow = px[r * w * 3:(r + 1) * w * 3]
        if y >= rh:
            out.append({"row": y, "error": "参照行越界"})
            continue
        rrow = rpx[y * rw * 3:(y + 1) * rw * 3]
        # 原位差（步长 4px 控成本）
        tot = n = 0
        for x in range(0, min(w, rw) - 3, 4):
            i = x * 3
            tot += abs(srow[i] - rrow[i]) + abs(srow[i + 1] - rrow[i + 1]) \
                + abs(srow[i + 2] - rrow[i + 2])
            n += 1
        in_place = tot / max(n, 1)
        # 限界位移搜索（±96px, 步 8；只搜 x，行内 1:1）
        best = (in_place, 0)
        for dx in range(-96, 97, 8):
            if dx == 0:
                continue
            tot = n = 0
            for x in range(max(0, -dx), min(w, rw - dx) - 3, 4):
                i, j = x * 3, (x + dx) * 3
                tot += abs(srow[i] - rrow[j]) + abs(srow[i + 1] - rrow[j + 1]) \
                    + abs(srow[i + 2] - rrow[j + 2])
                n += 1
            if n and tot / n < best[0]:
                best = (tot / n, dx)
        out.append({"row": y, "in_place": round(in_place, 1),
                    "best_dx": best[1], "best": round(best[0], 1),
                    "aligned": best[1] == 0})
    return out


# ---- 模式 3：原始页分类 -------------------------------------------------------

def classify_pages(path, page=4096):
    d = open(path, "rb").read()
    res = {"pages": [], "summary": {}}
    from collections import Counter
    kinds = Counter()
    for off in range(0, len(d), page):
        chunk = d[off:off + page]
        if not chunk:
            break
        # 熵（字节直方图）
        freq = [0] * 256
        for b in chunk:
            freq[b] += 1
        ent = -sum((c / len(chunk)) * math.log2(c / len(chunk))
                   for c in freq if c)
        zero = freq[0] / len(chunk)
        ascii_r = sum(freq[32:127]) / len(chunk)
        # 指针特征：32 位词低 2 位=11（LPAE 表项 valid）比例
        words = struct.unpack(f"<{len(chunk) // 4}I",
                              chunk[:len(chunk) // 4 * 4])
        ptr_like = sum(1 for w in words if w & 3 == 3) / max(len(words), 1)
        # 真文本特征：空格占比 + 换行/Tab（紫色图像字节恰落 ASCII
        # 可打印区会被裸 ascii_r 误判——需要排版字符作证）
        texty = (ascii_r > 0.8 and freq[0x20] > 0.08
                 and (freq[0x0a] > 0 or freq[0x09] > 0))
        if zero > 0.95:
            k = "zero"
        elif ent < 1.5 and zero > 0.5:
            k = "sparse"
        elif ptr_like > 0.3:
            k = "pagetable"
        elif texty:
            k = "text"
        elif ent > 6.0:
            k = "image"
        else:
            k = "mixed"
        kinds[k] += 1
        res["pages"].append({"off": off, "ent": round(ent, 2),
                             "zero": round(zero, 3),
                             "ascii": round(ascii_r, 3),
                             "ptr": round(ptr_like, 3), "kind": k})
    res["summary"] = dict(kinds)
    res["summary"]["total"] = sum(kinds.values())
    return res


# ---- CLI ---------------------------------------------------------------------

# note 114 定谳：greeter 实际显示 warty-final（非 cnusr25——两壁纸同
# 为暗紫底色系，历史误判源头）。写死为默认判据。
DEFAULT_REF = ("out/rk3588-topeet/ubuntu-rootfs.work/usr/share/"
               "backgrounds/warty-final-ubuntu.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("screen", help="屏幕 PPM（screendump）")
    ap.add_argument("--ref", default=DEFAULT_REF,
                    help="参照图 PNG/PPM（默认=warty-final，note 114 定谳）")
    ap.add_argument("--out-dir", help="热图输出目录")
    ap.add_argument("--strips", action="store_true",
                    help="1:1 条带模式（screen=条带 PPM，配 --strip-rows）")
    ap.add_argument("--strip-rows", default="100,500,990,1500,2000",
                    help="条带对应的源行号（逗号分隔）")
    ap.add_argument("--classify", action="store_true",
                    help="原始页分类模式（screen=二进制 dump）")
    args = ap.parse_args()

    if args.classify:
        r = classify_pages(args.screen)
        print(json.dumps(r["summary"], ensure_ascii=False))
        for p in r["pages"][:64]:
            print(f"  +{p['off']:#07x} ent={p['ent']:5.2f} z={p['zero']:.2f} "
                  f"a={p['ascii']:.2f} ptr={p['ptr']:.2f} {p['kind']}")
        return 0

    if not args.ref:
        ap.error("全屏/条带对照都需要 --ref")
    if args.strips:
        rows = [int(x) for x in args.strip_rows.split(",")]
        r = verify_strips(args.screen, args.ref, rows)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        aligned = sum(1 for x in r if x.get("aligned"))
        print(f"对齐行 {aligned}/{len(r)}")
        return 0

    r = verify_full(args.screen, args.ref, args.out_dir)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
