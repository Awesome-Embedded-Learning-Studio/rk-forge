#!/usr/bin/env python3
"""mini readelf：在 stripped so 的 .dynsym/.symtab 里找离目标偏移最近
的符号（guest 内用）。用法：python3 elfnear.py <so文件> <偏移>..."""
import struct
import sys

path = sys.argv[1]
targets = [int(t, 0) for t in sys.argv[2:]]

data = open(path, "rb").read()
assert data[:4] == b"\x7fELF" and data[4] == 2, "not ELF64"
e_shoff, = struct.unpack_from("<Q", data, 0x28)
e_shentsize, e_shnum = struct.unpack_from("<HH", data, 0x3a)

sections = []
for i in range(e_shnum):
    off = e_shoff + i * e_shentsize
    _, sh_type, _, _, sh_offset, sh_size, sh_link, _, _, sh_entsize = \
        struct.unpack_from("<IIQQQQIIQQ", data, off)
    sections.append((sh_type, sh_offset, sh_size, sh_link, sh_entsize))

syms = []
for sh_type, sh_offset, sh_size, sh_link, sh_entsize in sections:
    if sh_type not in (2, 11) or not sh_entsize:  # SYMTAB / DYNSYM
        continue
    # 关联 strtab
    st_off, st_size = sections[sh_link][1], sections[sh_link][2]
    strtab = data[st_off:st_off + st_size]
    for o in range(sh_offset, sh_offset + sh_size, sh_entsize):
        st_name, _info, _other, _shndx, st_value, _sz = struct.unpack_from("<IBBHQQ", data, o)
        if not st_value or not st_name:
            continue
        end = strtab.find(b"\0", st_name)
        name = strtab[st_name:end].decode(errors="replace")
        if name:
            syms.append((st_value, name))

syms.sort()
print(f"{len(syms)} symbols")
for t in targets:
    best = None
    for v, n in syms:
        if v <= t:
            best = (v, n)
        else:
            break
    if best:
        print(f"{t:#x} -> {best[1]} +{t - best[0]:#x} (sym {best[0]:#x})")
    else:
        print(f"{t:#x} -> no sym below")
