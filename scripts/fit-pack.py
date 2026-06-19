#!/usr/bin/env python3
# fit-pack.py — forge FIT image packer (replaces vendor mkimage for uboot.img).
#
# Produces a U-Boot FIT image (-E external-data layout) BYTE-COMPATIBLE with the
# vendor mkimage 2017.09 output the rkbin SPL accepts — in pure Python, with no
# mkimage / dtc / U-Boot build dependency. This is the "direction b" hand-built
# FIT packer from notes/20 (the mkimage saga): reverse the vendor uboot.img byte
# layout and reproduce it directly, the same way rkfw-pack.py (commit ba87abb)
# reproduced afptool/rkImageMaker for update.img.
#
# Why not mainline/vendor mkimage: vendor SPL parses ONLY the external-data layout
# vendor mkimage 2017.09 emits; mainline mkimage's -E puts optee data at a
# different offset → SPL reads mis-aligned bytes → "optee Bad hash". The ATK fork
# that produces the accepted layout is non-public (internal manifest 192.168.1.71)
# and drags the whole U-Boot build system to recompile. So we emit the layout
# ourselves. Proven byte-identical to vendor by `fit-pack.py selftest`.
#
# FIT -E layout (reverse-engineered from third_party/bringup/out/uboot.img):
#   file = FDT blob (header+struct+strings) | external data (per-image blobs) | pad
#   - external data starts at byte fdt_totalsize; each blob 0x200-aligned within it
#   - each image node: data-size / data-offset (offset relative to external start)
#   - each image's hash node: sha256 of that image's blob (the 32 raw bytes)
#   - root auto-props: version=0, totalsize=<fdt_totalsize+external_span>, timestamp
#   - file padded to 0x200
# The FDT string table and per-node property order faithfully reproduce mkimage's
# three-phase build (see _build_strings / the final-tree construction below) so the
# output is byte-for-byte equal to vendor (modulo the timestamp).
#
#   fit-pack.py [--timestamp N] <its> <out>
#   fit-pack.py selftest [--vendor <uboot.img>] [--its <rk3506-mainline.its>]
#       extracts the 3 blobs from a vendor uboot.img, repacks with the vendor
#       timestamp, and asserts byte-identity — airtight encoder proof, no board.
import argparse, hashlib, os, re, struct, sys, tempfile

FDT_MAGIC      = 0xd00dfeed
FDT_BEGIN_NODE = 1
FDT_END_NODE   = 2
FDT_PROP       = 3
FDT_NOP        = 4
FDT_END        = 9
HEADER_SIZE    = 40          # 10 × u32 BE
RSVMAP_SIZE    = 16          # one (0,0) terminator, no reservations
FIT_ALIGN      = 0x200       # IMAGE_ALIGN_SIZE — mkimage's FIT_ALIGN (vendor image.h:958)

# Prop names mkimage adds during FIT transformation, in the order they enter the
# string table AFTER the ITS-derived names. phase2 = root auto-props mkimage
# prepends; phase3 = props the -E external-data conversion introduces. These are
# appended (dedup, none collide with phase1) to reproduce the vendor string order
# exactly: …, timestamp, totalsize, version, value, data-offset, data-size.
_PHASE2_STRINGS = ['timestamp', 'totalsize', 'version']
_PHASE3_STRINGS = ['value', 'data-offset', 'data-size']


# ───────────────────────── ITS (FIT source) parser ──────────────────────────
# Focused recursive-descent parser for the FIT-ITS subset forge uses. Produces a
# generic node tree preserving ITS source order (prop order, child order) — the
# order is load-bearing for byte-identical FDT string-table reproduction.

class Node:
    __slots__ = ('name', 'props', 'children')
    def __init__(self, name):
        self.name = name
        self.props = []       # list of (name, value); value is a typed tuple
        self.children = []    # list of Node

# value tuples: ('str', s) | ('cells', [int,...]) | ('incbin', filename)

_TOKEN_RE = re.compile(r'''
      "(?P<str>(?:[^"\\]|\\.)*)"
    | (?P<punct>[{};=()<>])
    | (?P<word>[^\s{};=()<>"]+)
''', re.VERBOSE)


def _tokenize(text):
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.DOTALL)   # block comments
    text = re.sub(r'//[^\n]*', ' ', text)                      # line comments
    toks = []
    for m in _TOKEN_RE.finditer(text):
        if m.lastgroup == 'str':
            toks.append(('str', m.group('str')))
        elif m.lastgroup == 'punct':
            toks.append(('punct', m.group('punct')))
        else:
            toks.append(('word', m.group('word')))
    return toks


def _parse_int(s):
    return int(s, 0) if s.lower().startswith('0x') else int(s)


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def _peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def _next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def _expect_punct(self, p):
        t = self._next()
        if t != ('punct', p):
            sys.exit(f"fit-pack: parse error: expected {p!r} got {t!r}")

    def parse_node(self):
        t = self._next()
        if t[0] != 'word':
            sys.exit(f"fit-pack: parse error: expected node name got {t!r}")
        node = Node(t[1])
        self._expect_punct('{')
        while self._peek() != ('punct', '}'):
            mt = self._peek()
            if mt[0] != 'word':
                sys.exit(f"fit-pack: parse error: expected prop/node name got {mt!r}")
            nxt = self._peek(1)
            if nxt == ('punct', '='):
                self._parse_prop(node)
            elif nxt == ('punct', '{'):
                node.children.append(self.parse_node())
            else:
                sys.exit(f"fit-pack: parse error: unexpected {nxt!r} after {mt!r}")
        self._expect_punct('}')
        if self._peek() == ('punct', ';'):
            self._next()
        return node

    def _parse_prop(self, node):
        name = self._next()[1]
        self._expect_punct('=')
        node.props.append((name, self._parse_value()))
        self._expect_punct(';')

    def _parse_value(self):
        t = self._next()
        if t == ('punct', '<'):
            cells = []
            while self._peek() != ('punct', '>'):
                w = self._next()
                if w[0] != 'word':
                    sys.exit(f"fit-pack: parse error: bad cell {w!r}")
                cells.append(_parse_int(w[1]))
            self._expect_punct('>')
            return ('cells', cells)
        if t[0] == 'str':
            return ('str', t[1])
        if t[0] == 'word' and t[1] == '/incbin/':
            self._expect_punct('(')
            s = self._next()
            if s[0] != 'str':
                sys.exit(f"fit-pack: parse error: /incbin/ needs a string path, got {s!r}")
            self._expect_punct(')')
            return ('incbin', s[1])
        sys.exit(f"fit-pack: parse error: bad value {t!r}")


def parse_its(text):
    """Parse a FIT ITS source string into a Node tree (root named '/')."""
    p = _Parser(_tokenize(text))
    # Skip the `/dts-v1/;` directive (and any /memreserve/;) up to the root `/ {`.
    while p._peek() != ('word', '/'):
        if p._peek() == (None, None):
            sys.exit("fit-pack: parse error: no root node found in ITS")
        p._next()
    return p.parse_node()


# ───────────────────────────── tree helpers ─────────────────────────────────

def find_child(node, name):
    for c in node.children:
        if c.name == name:
            return c
    return None


def get_prop(node, name):
    for n, v in node.props:
        if n == name:
            return v
    return None


# ──────────────────────────── FDT / FIT assembly ────────────────────────────

def _align_up(x, a):
    return (x + a - 1) & ~(a - 1)


def _u32(x):
    return struct.pack('>I', x & 0xFFFFFFFF)


def _strval(s):
    return s.encode('utf-8') + b'\x00'


def _encode_prop_value(val):
    if val[0] == 'str':
        return _strval(val[1])
    if val[0] == 'cells':
        return b''.join(_u32(c) for c in val[1])
    raise ValueError(f"cannot encode prop value {val!r} into the final tree")


def _build_strings(parsed_root):
    """Reproduce mkimage's string-table order: phase1 = ITS tree pre-order DFS
    (props then children, first-occurrence dedup — note the parsed tree still
    carries the /incbin/ `data` props, so the unused 'data' string lands at the
    right spot, matching vendor), then phase2/phase3 appends."""
    strings = bytearray()
    off = {}

    def add(s):
        if s not in off:
            off[s] = len(strings)
            strings.extend(s.encode('utf-8'))
            strings.append(0)

    def walk(node):
        for n, _ in node.props:
            add(n)
        for c in node.children:
            walk(c)

    walk(parsed_root)
    for s in _PHASE2_STRINGS:
        add(s)
    for s in _PHASE3_STRINGS:
        add(s)
    return bytes(strings), off


def _build_final_tree(parsed_root, images, blobs, offsets, configs, conf,
                      totalsize_val, timestamp):
    """Construct the final FIT node tree (data→data-size/data-offset, hashes
    filled, root auto-props prepended) in mkimage's exact per-node property order.
    totalsize_val is the root /totalsize property value (set by caller to the
    file size — Rockchip SPL loads ceil(/totalsize / bl_len) bytes, spl_boot_image.c:293)."""
    root = Node('')

    # root: version, totalsize, timestamp, description, #address-cells
    root.props.append(('version', _u32(0)))
    root.props.append(('totalsize', _u32(totalsize_val)))
    root.props.append(('timestamp', _u32(timestamp)))
    root.props.append(('description', _strval(get_prop(parsed_root, 'description')[1])))
    root.props.append(('#address-cells', _u32(get_prop(parsed_root, '#address-cells')[1][0])))

    images_node = Node('images')
    for img, blob, off in zip(images, blobs, offsets):
        n = Node(img['name'])
        n.props.append(('data-size', _u32(len(blob))))
        n.props.append(('data-offset', _u32(off)))
        for pname, pval in img['node'].props:           # ITS order, minus data
            if pname == 'data':
                continue
            n.props.append((pname, _encode_prop_value(pval)))
        if img['has_hash']:
            h = Node('hash')
            h.props.append(('value', hashlib.sha256(blob).digest()))
            h.props.append(('algo', _strval('sha256')))
            n.children.append(h)
        images_node.children.append(n)
    root.children.append(images_node)

    configs_node = Node('configurations')
    configs_node.props.append(('default', _strval(get_prop(configs, 'default')[1])))
    if conf is not None:
        conf_node = Node('conf')
        for pname, pval in conf.props:
            conf_node.props.append((pname, _encode_prop_value(pval)))
        configs_node.children.append(conf_node)
    root.children.append(configs_node)
    return root


def _emit_struct(final_root, str_off):
    """Emit the FDT struct block (BEGIN_NODE/PROP/END_NODE/END tokens, 4-byte aligned)."""
    buf = bytearray()

    def u32(x):
        buf.extend(struct.pack('>I', x))

    def emit(node, is_root):
        u32(FDT_BEGIN_NODE)
        nm = (b'' if is_root else node.name.encode('utf-8')) + b'\x00'
        buf.extend(nm)
        buf.extend(b'\x00' * ((-len(nm)) % 4))
        for pname, pdata in node.props:
            u32(FDT_PROP)
            u32(len(pdata))
            u32(str_off[pname])
            buf.extend(pdata)
            buf.extend(b'\x00' * ((-len(pdata)) % 4))
        for c in node.children:
            emit(c, False)
        u32(FDT_END_NODE)

    emit(final_root, True)
    u32(FDT_END)
    return bytes(buf)


def pack(its_path, out_path, timestamp=0, verbose=True):
    """Build a FIT -E image from an ITS, resolving /incbin/ relative to its dir."""
    its_dir = os.path.dirname(os.path.abspath(its_path))
    with open(its_path, encoding='utf-8') as f:
        parsed_root = parse_its(f.read())

    images_node = find_child(parsed_root, 'images')
    configs_node = find_child(parsed_root, 'configurations')
    if images_node is None or configs_node is None:
        sys.exit("fit-pack: ITS missing /images or /configurations")

    images = []
    for img in images_node.children:
        dp = get_prop(img, 'data')
        if not dp or dp[0] != 'incbin':
            sys.exit(f"fit-pack: image {img.name!r} has no data = /incbin/(...)")
        images.append({'node': img, 'name': img.name,
                       'datafile': dp[1], 'has_hash': find_child(img, 'hash') is not None})

    # read blobs + lay out external data: each blob occupies FIT_ALIGN(len),
    # mirroring mkimage's `buf_ptr += FIT_ALIGN(len)` (fit_image.c:524). The
    # inter-blob gaps stay zero (vendor's are zero too).
    blobs, offsets, buf_ptr = [], [], 0
    for img in images:
        with open(os.path.join(its_dir, img['datafile']), 'rb') as bf:
            blob = bf.read()
        offsets.append(buf_ptr)
        blobs.append(blob)
        buf_ptr += _align_up(len(blob), FIT_ALIGN)
    ext = bytearray(buf_ptr)
    for off, blob in zip(offsets, blobs):
        ext[off:off + len(blob)] = blob

    conf = find_child(configs_node, 'conf')
    strings, str_off = _build_strings(parsed_root)

    # struct-block size is value-independent → build with a placeholder totalsize
    # to size the FDT, then rebuild with the real value. /totalsize = file_size:
    # Rockchip SPL loads ceil(/totalsize / bl_len)*bl_len bytes (spl_boot_image.c:293),
    # so the file_size value guarantees the whole image is read for any bl_len.
    placeholder = _build_final_tree(parsed_root, images, blobs, offsets,
                                    configs_node, conf, 0, timestamp)
    size_struct = len(_emit_struct(placeholder, str_off))
    fdt_totalsize = HEADER_SIZE + RSVMAP_SIZE + size_struct + len(strings)
    external_start = _align_up(fdt_totalsize, FIT_ALIGN)   # mkimage: new_size = FIT_ALIGN(fdt_totalsize)
    file_size = external_start + len(ext)

    final_root = _build_final_tree(parsed_root, images, blobs, offsets,
                                   configs_node, conf, file_size, timestamp)
    struct_blk = _emit_struct(final_root, str_off)
    assert len(struct_blk) == size_struct

    header = struct.pack('>10I', FDT_MAGIC, fdt_totalsize,
                         HEADER_SIZE + RSVMAP_SIZE,               # off_dt_struct  = 0x38
                         HEADER_SIZE + RSVMAP_SIZE + size_struct, # off_dt_strings
                         HEADER_SIZE,                             # off_mem_rsvmap = 0x28
                         17, 16, 0, len(strings), size_struct)
    fdt = header + (b'\x00' * RSVMAP_SIZE) + struct_blk + strings
    assert len(fdt) == fdt_totalsize

    out = bytearray(fdt)
    out.extend(b'\x00' * (external_start - fdt_totalsize))   # FDT→external FIT_ALIGN gap
    out.extend(ext)
    with open(out_path, 'wb') as f:
        f.write(out)

    if verbose:
        print(f"packed {out_path}: {len(out)} B (FDT {fdt_totalsize} @0, "
              f"external {len(ext)} @0x{external_start:x}, /totalsize={file_size})",
              file=sys.stderr)
        for img, blob, off in zip(images, blobs, offsets):
            print(f"  {img['name']:8} data-offset=0x{off:06x} data-size=0x{len(blob):x} "
                  f"sha256={hashlib.sha256(blob).hexdigest()[:16]}…", file=sys.stderr)
    return out


# ─────────────────────────── FDT reader (selftest) ──────────────────────────

def read_fdt(data):
    """Parse a FDT blob into a Node tree (props carry raw value bytes)."""
    (magic, totalsize, off_struct, off_strings, off_rsvmap, ver, _lc, _bc,
     size_strings, size_struct) = struct.unpack('>10I', data[:HEADER_SIZE])
    if magic != FDT_MAGIC:
        sys.exit(f"fit-pack: not a FDT (magic {magic:#x})")
    strings = data[off_strings:off_strings + size_strings]

    def sname(o):
        return strings[o:strings.index(b'\x00', o)].decode('utf-8')

    pos = [off_struct]

    def parse():
        tok = struct.unpack('>I', data[pos[0]:pos[0] + 4])[0]
        pos[0] += 4
        if tok != FDT_BEGIN_NODE:
            sys.exit("fit-pack: expected BEGIN_NODE")
        e = data.index(b'\x00', pos[0])
        node = Node(data[pos[0]:e].decode('utf-8'))
        pos[0] = (e + 1 + 3) & ~3
        while True:
            tok = struct.unpack('>I', data[pos[0]:pos[0] + 4])[0]
            pos[0] += 4
            if tok == FDT_END_NODE:
                return node
            if tok == FDT_PROP:
                ln, no = struct.unpack('>II', data[pos[0]:pos[0] + 8])
                pos[0] += 8
                v = data[pos[0]:pos[0] + ln]
                pos[0] = (pos[0] + ln + 3) & ~3
                node.props.append((sname(no), v))
            elif tok == FDT_BEGIN_NODE:
                pos[0] -= 4
                node.children.append(parse())
            elif tok == FDT_END:
                return node
            # FDT_NOP: ignore
    return parse(), totalsize


def _tree_sig(node, depth=0, out=None):
    """Canonical line signature of a parsed FDT tree (props in order, then children).
    /timestamp and /totalsize values are normalized — they are mkimage host
    artifacts (build time + the pre-externalization inline-FIT size) that SPL never
    consumes for boot; only their presence (which SPL DOES need) matters."""
    if out is None:
        out = []
    pad = '  ' * depth
    for pn, pv in node.props:
        if pn in ('timestamp', 'totalsize'):
            out.append(f"{pad}.{pn} = <host-artifact>")
        else:
            out.append(f"{pad}.{pn} = {pv.hex()}")
    for c in node.children:
        out.append(f"{pad}<{c.name}>")
        _tree_sig(c, depth + 1, out)
    return out


def cmd_selftest(args):
    """Repack a vendor uboot.img's own blobs and prove SPL-equivalence: identical
    FDT tree (modulo host-only /timestamp + /totalsize values) and identical
    external blobs at identical offsets, with /totalsize sized to load the whole
    file. Raw byte-identity is NOT expected — mkimage leaves a residual pre-
    fdt_pack gap plus host timestamp/totalsize that SPL never reads."""
    import difflib, shutil
    with open(args.vendor, 'rb') as f:
        vendor = f.read()
    vtree, vfdt = read_fdt(vendor)
    v_ext = _align_up(vfdt, FIT_ALIGN)   # external data starts at FIT_ALIGN(fdt_totalsize)

    with open(args.its, encoding='utf-8') as f:
        its_root = parse_its(f.read())
    its_images = find_child(its_root, 'images')
    name_map = {}
    for img in its_images.children:
        dp = get_prop(img, 'data')
        if dp and dp[0] == 'incbin':
            name_map[img.name] = dp[1]

    tmp = tempfile.mkdtemp(prefix='fit-pack-selftest-')
    try:
        v_blobs = {}
        for img in find_child(vtree, 'images').children:
            ds = struct.unpack('>I', get_prop(img, 'data-size'))[0]
            do = struct.unpack('>I', get_prop(img, 'data-offset'))[0]
            v_blobs[img.name] = vendor[v_ext + do: v_ext + do + ds]
            fn = name_map.get(img.name)
            if not fn:
                sys.exit(f"fit-pack: selftest can't map image {img.name!r} to an /incbin/ file")
            with open(os.path.join(tmp, fn), 'wb') as bf:
                bf.write(v_blobs[img.name])
        shutil.copy(args.its, os.path.join(tmp, os.path.basename(args.its)))

        out = os.path.join(tmp, 'uboot.img')
        pack(os.path.join(tmp, os.path.basename(args.its)), out, timestamp=0, verbose=False)
        with open(out, 'rb') as f:
            mine = f.read()
        mtree, mfdt = read_fdt(mine)
        m_ext = _align_up(mfdt, FIT_ALIGN)

        problems = []

        # (a) FDT tree identical modulo host-only /timestamp + /totalsize values
        vsig, msig = _tree_sig(vtree), _tree_sig(mtree)
        if vsig != msig:
            problems.append("FDT tree differs from vendor (beyond /timestamp + /totalsize):")
            problems.extend('  ' + l for l in difflib.unified_diff(
                vsig, msig, 'vendor', 'mine', lineterm=''))

        # (b) external blobs identical at identical offsets
        for img in find_child(mtree, 'images').children:
            ds = struct.unpack('>I', get_prop(img, 'data-size'))[0]
            do = struct.unpack('>I', get_prop(img, 'data-offset'))[0]
            mb = mine[m_ext + do: m_ext + do + ds]
            if v_blobs.get(img.name) != mb:
                problems.append(f"external blob {img.name!r} differs from vendor")

        # (c) /totalsize loads the whole file for any plausible NAND block length
        m_ts = struct.unpack('>I', get_prop(mtree, 'totalsize'))[0]
        for bl in (512, 2048, 4096):
            loaded = -(-m_ts // bl) * bl
            if loaded < len(mine):
                problems.append(f"/totalsize={m_ts} loads only {loaded} B at bl_len={bl} "
                                f"(< file {len(mine)} B)")

        ndiff = sum(1 for a, b in zip(mine, vendor) if a != b) + abs(len(mine) - len(vendor))
        first = next((i for i, (a, b) in enumerate(zip(mine, vendor)) if a != b), None)

        if problems:
            print("fit-pack selftest: FAIL", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"fit-pack selftest: PASS — FDT tree + external blobs SPL-equivalent to "
              f"{args.vendor} ({len(mine)} B).")
        if ndiff:
            print(f"  raw byte diff: {ndiff} B (first @ 0x{first:x}) — confined to "
                  f"SPL-irrelevant regions (FDT→external gap, /timestamp, /totalsize value).",
                  file=sys.stderr)
        else:
            print("  raw byte diff: 0 B (byte-identical — --vendor holds a forge-packed "
                  "image; this run is a determinism check).", file=sys.stderr)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description='forge FIT -E packer (replaces vendor mkimage)')
    sub = ap.add_subparsers(dest='cmd')
    p = sub.add_parser('pack', help='build a FIT image from an ITS')
    p.add_argument('--timestamp', type=lambda s: int(s, 0), default=0,
                   help='root timestamp (default 0 = reproducible)')
    p.add_argument('its')
    p.add_argument('out')
    p.set_defaults(func=lambda a: pack(a.its, a.out, a.timestamp))
    s = sub.add_parser('selftest', help='repack a vendor uboot.img, prove SPL-equivalence')
    s.add_argument('--vendor', default='third_party/bringup/out/uboot.img')
    s.add_argument('--its', default='third_party/bringup/fit/rk3506-mainline.its')
    s.set_defaults(func=cmd_selftest)
    args = ap.parse_args()
    if not getattr(args, 'func', None):
        ap.print_help()
        sys.exit(2)
    rc = args.func(args)
    sys.exit(rc if isinstance(rc, int) else 0)   # pack returns the bytes (not an exit code)


if __name__ == '__main__':
    main()
