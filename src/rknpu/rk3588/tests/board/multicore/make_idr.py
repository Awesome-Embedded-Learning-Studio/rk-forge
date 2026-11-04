"""生成固定 128x128 baseline H.264 IDR/I_PCM,不依赖编码器；附 NV12 真值。"""
from pathlib import Path

class Bits:
    def __init__(self): self.bits = ''
    def u(self, value, count): self.bits += format(value, f'0{count}b')
    def ue(self, value):
        v = format(value + 1, 'b'); self.bits += '0' * (len(v)-1) + v
    def se(self, value): self.ue(2*abs(value)-(value>0))
    def align(self): self.bits += '0' * (-len(self.bits) % 8)
    def raw(self, data):
        assert len(self.bits)%8 == 0
        self.bits += ''.join(format(x, '08b') for x in data)
    def finish(self):
        self.bits += '1'; self.align()
        return bytes(int(self.bits[i:i+8], 2) for i in range(0,len(self.bits),8))

def nal(header, data):
    out = bytearray(b'\0\0\0\1'+bytes([header])); zeros = 0
    for x in data:
        if zeros >= 2 and x <= 3: out.append(3); zeros = 0
        out.append(x); zeros = zeros+1 if x == 0 else 0
    return bytes(out)

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir', required=True, help='directory for generated .h264/.slice/.nv12 fixtures')
    args = ap.parse_args(argv)
    w=h=128
    base=Path(args.output_dir);base.mkdir(parents=True,exist_ok=True)
    for worker in range(2):
        y=bytes(16 + (x*3+row*5+worker*13)%220 for row in range(h) for x in range(w))
        s=Bits();s.u(66,8);s.u(0,8);s.u(30,8);s.ue(0);s.ue(0);s.ue(2);s.ue(1);s.u(0,1);s.ue(w//16-1);s.ue(h//16-1);s.u(1,1);s.u(1,1);s.u(0,1);s.u(0,1)
        p=Bits();p.ue(0);p.ue(0);p.u(0,1);p.u(0,1);p.ue(0);p.ue(0);p.ue(0);p.u(0,1);p.u(0,2);p.se(0);p.se(0);p.se(0);p.u(1,1);p.u(0,1);p.u(0,1)
        f=Bits();f.ue(0);f.ue(2);f.ue(0);f.u(0,4);f.ue(0);f.u(0,1);f.u(0,1);f.se(0);f.ue(1)
        for my in range(h//16):
            for mx in range(w//16):
                f.ue(25);f.align()
                f.raw(bytes(y[(my*16+row)*w+mx*16+x] for row in range(16) for x in range(16)))
                f.raw(bytes([128])*128)
        idr=nal(0x65,f.finish())
        name=f'idr128-worker{worker}'
        (base/(name+'.h264')).write_bytes(nal(0x67,s.finish())+nal(0x68,p.finish())+idr)
        (base/(name+'.slice')).write_bytes(idr)
        (base/(name+'.nv12')).write_bytes(y+bytes([128])*(w*h//2))
        print(name,'IDR slice bytes',len(idr),'NV12 bytes',w*h*3//2)


if __name__ == '__main__':
    main()
