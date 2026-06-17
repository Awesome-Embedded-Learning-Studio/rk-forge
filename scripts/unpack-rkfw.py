#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
# Inspect/extract a Rockchip RKFW update.img without the Windows afptool.
#
# Layout (reverse-engineered from vendor rk3506b_update_ubi_ubifs.img):
#   update.img
#   ├─ RKFW header @0x00 (magic "RKFW", header size 0x66)
#   │    └─ embedded loader components (idbloader/uboot/trust) in the 0x00..N gap
#   └─ RKAF container @ RKAF magic offset (search for "RKAF")
#        ├─ RKAF header: magic "RKAF", model "RK3506"...
#        ├─ partition-entry table (stride 0x70):
#        │     name[0x20] | source_file[0x40] | f0(u32) | size(u32) | f2 | f3
#        │     f0  = byte offset of the partition image, relative to the RKAF magic
#        │     size = image size in bytes
#        └─ payload: partition images laid out sequentially at their f0
#
# parameter.txt (from f0 of the "parameter" entry) holds the *flash* partition
# table (mtdparts, 512B sectors) — that's the on-flash layout, distinct from f0
# which is the in-update.img storage offset.

import struct, sys, os

def find(data, magic, start=0):
    i = data.find(magic, start)
    return i  # -1 if not found

def cstr(b):
    return b.split(b'\x00')[0].decode('latin1', 'replace')

def parse(path, outdir=None, extract=None):
    data = open(path, 'rb').read()
    rkaf = find(data, b'RKAF')
    if rkaf < 0:
        sys.exit("no RKAF magic found — not a Rockchip update.img?")
    print(f"# {path}  ({len(data)} bytes)")
    print(f"# RKAF container @ {rkaf:#x}")
    print(f"# model: {cstr(data[rkaf+8:rkaf+0x28])!r}")
    print()
    print(f"{'name':14}{'source_file':22}{'f0(off)':>12}{'size':>12}   size(MiB)")
    print("-" * 70)

    # first entry: find "package-file" name slot after the header
    first = find(data, b'package-file\x00', rkaf)
    STRIDE = 0x70
    parts = {}
    ent = first
    while True:
        name = cstr(data[ent:ent+0x20])
        if not name:
            break
        file_ = cstr(data[ent+0x20:ent+0x60])
        # entry tail @ +0x60: [f0: image offset | f1: flag(0xffffffff=sentinel) |
        #                       f2: ? | f3: image size]
        f0, f1, f2, size = struct.unpack_from('<IIII', data, ent+0x60)
        parts[name] = (rkaf + f0, size, file_)
        print(f"{name:14}{file_:22}{f0:#12x}{size:#12x}   {size/1048576:8.2f}")
        ent += STRIDE

    # parameter.txt flash layout
    if 'parameter' in parts:
        off, size, _ = parts['parameter']
        txt = data[off:off+size].decode('latin1', 'replace')
        for line in txt.splitlines():
            if 'CMDLINE' in line or 'mtdparts' in line:
                print("\n# flash layout (parameter.txt CMDLINE):")
                print("  " + line.strip())
                break

    if extract:
        names = extract if isinstance(extract, list) else [extract]
        os.makedirs(outdir, exist_ok=True)
        for n in names:
            if n not in parts:
                print(f"!! no partition named {n!r}", file=sys.stderr); continue
            off, size, _ = parts[n]
            out = os.path.join(outdir, n + '.img')
            with open(out, 'wb') as f:
                f.write(data[off:off+size])
            print(f"# extracted {n} -> {out} ({size} bytes)")

if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        sys.exit("usage: unpack-rkfw.py <update.img> [outdir] [-x name[,name...]]")
    img = args[0]
    outdir = '.'
    extract = None
    if len(args) > 1:
        i = 1
        while i < len(args):
            a = args[i]
            if a == '-x':
                extract = args[i+1].split(','); i += 2
            else:
                outdir = a; i += 1
    parse(img, outdir, extract)
