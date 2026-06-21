#!/usr/bin/env python3
# rkfw-pack.py — forge RKAF + RKFW update.img packer (replaces vendor afptool/rkImageMaker).
#
# update.img = RKFW[ 0x66 header | MiniLoader(loader) | RKAF archive | 32B ASCII MD5 ]
# RKAF       = 0x8c header | partition table (112B/entry) | partition images (0x800-aligned)
#              | 4B trailing rkcrc32
#
# Format reverse-engineered from vendor afptool/rkImageMaker output and cross-checked
# against community spec github.com/TheGammaSqueeze/rk_image_tool + the open
# reimplementation github.com/suyulin/afptool-rs (which revealed the Rockchip-custom
# rkcrc32 — NOT zlib/IEEE CRC32 — and the PARM wrap = PARM+len+data+rkcrc32(data)).
#
#   pack   <package-file> <image-dir> <loader> <parameter> <out.img>
#   unpack <update.img> <out-dir>
#   info   <update.img>
import argparse, hashlib, os, re, struct, sys

PAGE = 0x800
RKFW_HDR = 0x66
RKAF_HDR = 0x8C
ENTRY_SZ = 112

# Rockchip-custom CRC32 table (MSB-first, poly 0x04c10db7 — NOT IEEE 0x04c11db7).
# Lifted from afptool-rs src/pack.rs; verified to reproduce vendor afptool's trailing
# checksum byte-for-byte (rkcrc32(body)==0xa93e7e20, rkcrc32(parameter.txt)==0xb3aaf39c).
RKCRC32_TABLE = [
    0x00000000,0x04c10db7,0x09821b6e,0x0d4316d9,0x130436dc,0x17c53b6b,0x1a862db2,0x1e472005,
    0x26086db8,0x22c9600f,0x2f8a76d6,0x2b4b7b61,0x350c5b64,0x31cd56d3,0x3c8e400a,0x384f4dbd,
    0x4c10db70,0x48d1d6c7,0x4592c01e,0x4153cda9,0x5f14edac,0x5bd5e01b,0x5696f6c2,0x5257fb75,
    0x6a18b6c8,0x6ed9bb7f,0x639aada6,0x675ba011,0x791c8014,0x7ddd8da3,0x709e9b7a,0x745f96cd,
    0x9821b6e0,0x9ce0bb57,0x91a3ad8e,0x9562a039,0x8b25803c,0x8fe48d8b,0x82a79b52,0x866696e5,
    0xbe29db58,0xbae8d6ef,0xb7abc036,0xb36acd81,0xad2ded84,0xa9ece033,0xa4aff6ea,0xa06efb5d,
    0xd4316d90,0xd0f06027,0xddb376fe,0xd9727b49,0xc7355b4c,0xc3f456fb,0xceb74022,0xca764d95,
    0xf2390028,0xf6f80d9f,0xfbbb1b46,0xff7a16f1,0xe13d36f4,0xe5fc3b43,0xe8bf2d9a,0xec7e202d,
    0x34826077,0x30436dc0,0x3d007b19,0x39c176ae,0x278656ab,0x23475b1c,0x2e044dc5,0x2ac54072,
    0x128a0dcf,0x164b0078,0x1b0816a1,0x1fc91b16,0x018e3b13,0x054f36a4,0x080c207d,0x0ccd2dca,
    0x7892bb07,0x7c53b6b0,0x7110a069,0x75d1adde,0x6b968ddb,0x6f57806c,0x621496b5,0x66d59b02,
    0x5e9ad6bf,0x5a5bdb08,0x5718cdd1,0x53d9c066,0x4d9ee063,0x495fedd4,0x441cfb0d,0x40ddf6ba,
    0xaca3d697,0xa862db20,0xa521cdf9,0xa1e0c04e,0xbfa7e04b,0xbb66edfc,0xb625fb25,0xb2e4f692,
    0x8aabbb2f,0x8e6ab698,0x8329a041,0x87e8adf6,0x99af8df3,0x9d6e8044,0x902d969d,0x94ec9b2a,
    0xe0b30de7,0xe4720050,0xe9311689,0xedf01b3e,0xf3b73b3b,0xf776368c,0xfa352055,0xfef42de2,
    0xc6bb605f,0xc27a6de8,0xcf397b31,0xcbf87686,0xd5bf5683,0xd17e5b34,0xdc3d4ded,0xd8fc405a,
    0x6904c0ee,0x6dc5cd59,0x6086db80,0x6447d637,0x7a00f632,0x7ec1fb85,0x7382ed5c,0x7743e0eb,
    0x4f0cad56,0x4bcda0e1,0x468eb638,0x424fbb8f,0x5c089b8a,0x58c9963d,0x558a80e4,0x514b8d53,
    0x25141b9e,0x21d51629,0x2c9600f0,0x28570d47,0x36102d42,0x32d120f5,0x3f92362c,0x3b533b9b,
    0x031c7626,0x07dd7b91,0x0a9e6d48,0x0e5f60ff,0x101840fa,0x14d94d4d,0x199a5b94,0x1d5b5623,
    0xf125760e,0xf5e47bb9,0xf8a76d60,0xfc6660d7,0xe22140d2,0xe6e04d65,0xeba35bbc,0xef62560b,
    0xd72d1bb6,0xd3ec1601,0xdeaf00d8,0xda6e0d6f,0xc4292d6a,0xc0e820dd,0xcdab3604,0xc96a3bb3,
    0xbd35ad7e,0xb9f4a0c9,0xb4b7b610,0xb076bba7,0xae319ba2,0xaaf09615,0xa7b380cc,0xa3728d7b,
    0x9b3dc0c6,0x9ffccd71,0x92bfdba8,0x967ed61f,0x8839f61a,0x8cf8fbad,0x81bbed74,0x857ae0c3,
    0x5d86a099,0x5947ad2e,0x5404bbf7,0x50c5b640,0x4e829645,0x4a439bf2,0x47008d2b,0x43c1809c,
    0x7b8ecd21,0x7f4fc096,0x720cd64f,0x76cddbf8,0x688afbfd,0x6c4bf64a,0x6108e093,0x65c9ed24,
    0x11967be9,0x1557765e,0x18146087,0x1cd56d30,0x02924d35,0x06534082,0x0b10565b,0x0fd15bec,
    0x379e1651,0x335f1be6,0x3e1c0d3f,0x3add0088,0x249a208d,0x205b2d3a,0x2d183be3,0x29d93654,
    0xc5a71679,0xc1661bce,0xcc250d17,0xc8e400a0,0xd6a320a5,0xd2622d12,0xdf213bcb,0xdbe0367c,
    0xe3af7bc1,0xe76e7676,0xea2d60af,0xeeec6d18,0xf0ab4d1d,0xf46a40aa,0xf9295673,0xfde85bc4,
    0x89b7cd09,0x8d76c0be,0x8035d667,0x84f4dbd0,0x9ab3fbd5,0x9e72f662,0x9331e0bb,0x97f0ed0c,
    0xafbfa0b1,0xab7ead06,0xa63dbbdf,0xa2fcb668,0xbcbb966d,0xb87a9bda,0xb5398d03,0xb1f880b4,
]

def rkcrc32(data: bytes) -> int:
    """Rockchip-custom CRC32 (MSB-first, table lookup, init=0, no final xor)."""
    crc = 0
    for b in data:
        crc = ((crc << 8) ^ RKCRC32_TABLE[((crc >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return crc

def _cstr(b, n):
    return (b[:n]).ljust(n, b'\x00')

def parse_package_file(path):
    out = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            s = line.rstrip('\n')
            if not s.strip() or s.lstrip().startswith('#'):
                continue
            parts = [p for p in s.split('\t') if p.strip()]   # rows use double-tab alignment
            if len(parts) < 2:
                parts = s.split()
            out.append((parts[0].strip(), parts[1].strip()))
    return out

def parse_parameter(path):
    ver, parts = (8, 1, 0), {}
    if not path or not os.path.exists(path):
        return ver, parts
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('FIRMWARE_VER:'):
                nums = re.findall(r'\d+', line.split(':', 1)[1])
                nums = (nums + ['0', '0', '0'])[:3]
                ver = tuple(int(x) for x in nums)
            if 'mtdparts' in line:
                body = line.split('mtdparts', 1)[1].lstrip(': ')
                for tok in body.split(','):
                    m = re.search(r'(-?0x[0-9a-fA-F]+)\s*@\s*0x([0-9a-fA-F]+)\s*\(([^:)]+)', tok)
                    if m:
                        size_s, off_s, name = m.groups()
                        size = 0 if size_s.startswith('-') else int(size_s, 16)
                        parts[name.strip()] = (size, int(off_s, 16))
    return ver, parts

def read_chip_tag(loader_path):
    with open(loader_path, 'rb') as f:
        f.seek(21)
        return f.read(4)

def version_int(ver):
    return (ver[0] << 24) | (ver[1] << 16) | ver[2]

def _load_image(image_dir, rel):
    src = os.path.join(image_dir, rel.replace('Image/', '', 1))
    if not os.path.exists(src):
        src = os.path.join(image_dir, os.path.basename(rel))
    with open(src, 'rb') as f:
        return f.read()

def _wrap_parameter(raw: bytes) -> bytes:
    """afptool PARM wrap: 'PARM' + u32(len) + data + rkcrc32(data)."""
    return b'PARM' + struct.pack('<I', len(raw)) + raw + struct.pack('<I', rkcrc32(raw))

def cmd_pack(args):
    entries = parse_package_file(args.package_file)
    ver, mtdparts = parse_parameter(args.parameter)
    chip = read_chip_tag(args.loader)
    with open(args.loader, 'rb') as f:
        loader = f.read()

    n = len(entries)
    records, images = [], []
    cursor = (RKAF_HDR + n * ENTRY_SZ + PAGE - 1) // PAGE * PAGE
    for name, rel in entries:
        if name == 'package-file':
            with open(args.package_file, 'rb') as f:
                raw = f.read()                     # self-referential: image is the manifest itself
        else:
            raw = _load_image(args.image_dir, rel)
        data = _wrap_parameter(raw) if name == 'parameter' else raw
        size = len(data)
        pos = cursor
        if name in ('package-file', 'bootloader'):
            nand_size, nand_addr = 0, 0xFFFFFFFF
        elif name == 'parameter':
            nand_size, nand_addr = 0x2000, 0x0      # afptool hardcodes parameter's flash meta (not a real flash partition)
        else:
            nand_size, nand_addr = mtdparts.get(name, (0, 0xFFFFFFFF))
            # A real flash partition with nand_addr=0xFFFFFFFF means it wasn't
            # found in the parameter (typo) OR is a "grow" entry whose `-` size
            # the regex can't parse. Either way the RK tool gets no write
            # address → it builds the partition but writes NO image → the board
            # panics ("no filesystem could mount root"). Fail loudly at pack
            # time instead of letting an empty partition ship. (boot-sdl-202606211014)
            if nand_addr == 0xFFFFFFFF:
                sys.stderr.write(
                    f"rkfw-pack: WARNING: partition '{name}' has no fixed flash "
                    f"address (nand_addr=0xFFFFFFFF; not in parameter or is a "
                    f"'grow' entry). The RK tool will likely NOT write its image "
                    f"→ empty partition → board root-mount failure. Give it a "
                    f"fixed 0x<size>@0x<offset> entry in the parameter.\n")
        padded = (size + PAGE - 1) // PAGE
        rec = (_cstr(name.encode(), 32) + _cstr(os.path.basename(rel).encode(), 60)
               + struct.pack('<IIIII', nand_size, pos, nand_addr, padded, size))
        assert len(rec) == ENTRY_SZ, len(rec)
        records.append(rec)
        images.append((pos, data))
        cursor = (pos + size + PAGE - 1) // PAGE * PAGE

    body = bytearray(RKAF_HDR) + b''.join(records)
    for pos, data in images:
        if len(body) < pos:
            body += b'\x00' * (pos - len(body))
        body += data
    body_len = len(body)                    # header + table + images, before the trailing CRC
    hdr = (b'RKAF' + struct.pack('<I', body_len)   # length field = body_len (= span - 4 once CRC is appended)
           + _cstr(b'RK3506', 0x22) + _cstr(b'007', 0x1E) + _cstr(b' RK3506', 0x38)
           + struct.pack('<I', 0) + struct.pack('<I', version_int(ver)) + struct.pack('<I', n))
    assert len(hdr) == RKAF_HDR
    body[:RKAF_HDR] = hdr                   # fill the real header BEFORE computing the trailing CRC
    body += struct.pack('<I', rkcrc32(bytes(body)))   # afptool trailing rkcrc32 over real header+table+images
    rkaf_span = len(body)

    rkwf = b'RKFW'
    rkwf += struct.pack('<H', RKFW_HDR)                        # head_len u16 @0x04
    rkwf += struct.pack('<I', version_int(ver))                # version u32 @0x06
    rkwf += struct.pack('<I', 0x02000000)                      # code u32 @0x0A
    rkwf += b'\x00' * 7                                        # build_time @0x0E (fixed → reproducible)
    rkwf += chip                                               # chip @0x15 (loader[21:25])
    rkwf += struct.pack('<I', RKFW_HDR)                        # loader_off @0x19
    rkwf += struct.pack('<I', len(loader))                     # loader_len @0x1D
    rkwf += struct.pack('<I', RKFW_HDR + len(loader))         # image_off @0x21
    rkwf += struct.pack('<I', rkaf_span)                       # image_len @0x25 (= RKAF span)
    rkwf += b'\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00'  # flags @0x29 (observed)
    rkwf += struct.pack('<I', 0)                               # backup_endpos @0x35
    rkwf += b'\x00' * (RKFW_HDR - len(rkwf))
    assert len(rkwf) == RKFW_HDR

    out = bytearray(rkwf) + loader + body
    out += hashlib.md5(bytes(out)).hexdigest().encode('ascii')
    with open(args.out, 'wb') as f:
        f.write(out)
    print(f"packed {args.out}: {len(out)} B "
          f"(RKFW + loader {len(loader)} B + RKAF {rkaf_span} B + MD5)")
    print(f"  chip {chip!r} → RK{bytes(reversed(chip)).decode('latin1')}, "
          f"{n} parts, version {'.'.join(map(str, ver))}")

def cmd_unpack(args):
    with open(args.update_img, 'rb') as f:
        d = f.read()
    os.makedirs(args.out_dir, exist_ok=True)
    if d[:4] != b'RKFW':
        sys.exit(f"not an RKFW image: magic {d[:4]!r}")
    loader_off = struct.unpack('<I', d[0x19:0x1D])[0]
    loader_len = struct.unpack('<I', d[0x1D:0x21])[0]
    image_off = struct.unpack('<I', d[0x21:0x25])[0]
    with open(os.path.join(args.out_dir, 'boot.bin'), 'wb') as f:
        f.write(d[loader_off:loader_off + loader_len])
    rkaf = d[image_off:]
    if rkaf[:4] != b'RKAF':
        sys.exit(f"RKAF magic mismatch at {image_off:#x}: {rkaf[:4]!r}")
    n = struct.unpack('<I', rkaf[0x88:0x8C])[0]
    for i in range(n):
        e = rkaf[RKAF_HDR + i*ENTRY_SZ: RKAF_HDR + (i+1)*ENTRY_SZ]
        name = e[:32].split(b'\x00')[0].decode('latin1')
        fn = e[32:92].split(b'\x00')[0].decode('latin1')
        pos = struct.unpack('<I', e[96:100])[0]
        size = struct.unpack('<I', e[108:112])[0]
        data = rkaf[pos:pos + size]
        if name == 'parameter' and data[:4] == b'PARM':   # strip PARM wrap
            inner_len = struct.unpack('<I', data[4:8])[0]
            data = data[8:8 + inner_len]
        with open(os.path.join(args.out_dir, fn), 'wb') as f:
            f.write(data)
        print(f"  [{i}] {name:14} {fn:22} pos={pos:#08x} size={size}")

def cmd_info(args):
    with open(args.update_img, 'rb') as f:
        d = f.read()
    print(f"file: {args.update_img} ({len(d)} B)")
    print(f"RKFW magic={d[:4]} head_len=0x{struct.unpack('<H',d[4:6])[0]:x} "
          f"version=0x{struct.unpack('<I',d[6:10])[0]:08x} code=0x{struct.unpack('<I',d[10:14])[0]:08x}")
    print(f"  build_time={d[14:21].hex()} chip={d[21:25]!r} "
          f"(RK{bytes(reversed(d[21:25])).decode('latin1')})")
    print(f"  loader_off=0x{struct.unpack('<I',d[0x19:0x1d])[0]:x} "
          f"loader_len={struct.unpack('<I',d[0x1d:0x21])[0]} "
          f"image_off=0x{struct.unpack('<I',d[0x21:0x25])[0]:x} "
          f"image_len={struct.unpack('<I',d[0x25:0x29])[0]}")
    print(f"  md5 tail={d[-32:].decode('ascii','replace')}  "
          f"computed={hashlib.md5(d[:-32]).hexdigest()}")
    io = struct.unpack('<I', d[0x21:0x25])[0]
    rkaf = d[io:]
    print(f"RKAF @{io:#x} magic={rkaf[:4]} length={struct.unpack('<I',rkaf[4:8])[0]} "
          f"num_parts={struct.unpack('<I',rkaf[0x88:0x8c])[0]} "
          f"trailing_rkcrc={struct.unpack('<I',rkaf[struct.unpack('<I',d[0x25:0x29])[0]-4:struct.unpack('<I',d[0x25:0x29])[0]])[0]:#010x}")
    base = io + RKAF_HDR
    nn = struct.unpack('<I', rkaf[0x88:0x8c])[0]
    for i in range(nn):
        e = d[base + i*ENTRY_SZ: base + (i+1)*ENTRY_SZ]
        name = e[:32].split(b'\x00')[0].decode('latin1')
        fn = e[32:92].split(b'\x00')[0].decode('latin1')
        ns, pos, na, pd, sz = struct.unpack('<IIIII', e[92:112])
        print(f"  [{i}] {name:14} {fn:22} nand_size=0x{ns:x} pos=0x{pos:x} "
              f"nand_addr=0x{na:x} padded=0x{pd:x} size=0x{sz:x}")

def main():
    ap = argparse.ArgumentParser(description='forge RKAF+RKFW update.img packer')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pack'); p.add_argument('package_file'); p.add_argument('image_dir')
    p.add_argument('loader'); p.add_argument('parameter'); p.add_argument('out')
    p.set_defaults(func=cmd_pack)
    u = sub.add_parser('unpack'); u.add_argument('update_img'); u.add_argument('out_dir')
    u.set_defaults(func=cmd_unpack)
    i = sub.add_parser('info'); i.add_argument('update_img')
    i.set_defaults(func=cmd_info)
    args = ap.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
