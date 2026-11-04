"""主机解码 JPEG 并核对所有物理核心计数及 demo 结果。"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('evidence');ap.add_argument('--frames',type=int,default=16)
    a=ap.parse_args(argv);base=Path(a.evidence);report={};ok=(base/"device-status").read_text().strip()=="0"
    assert int((base/"frames").read_text())==a.frames
    reference=np.fromfunction(lambda y,x:16+(x*3+y*5)%220,(128,128),dtype=int).astype(np.float64)
    for worker in range(4):
        path=base/f'jpeg-worker{worker}.jpg'
        with Image.open(path) as image:
            image.load()
            assert image.size==(128,128) and image.format=='JPEG',path
            gray=np.asarray(image.convert('L'),dtype=np.float64)
        expected=np.fromfunction(lambda y,x:16+(x*3+y*5+worker*13)%220,(128,128),dtype=int).astype(np.float64)
        mse=float(np.mean((gray-expected)**2));psnr=10*math.log10(255**2/mse) if mse else 100.0
        report[path.name]={'psnr_db':psnr,'min':float(gray.min()),'max':float(gray.max())}
        ok &= psnr>=28.0
    for mode,workers in [('rga',2),('h264',2)]:
        for worker in range(workers):
            path=base/f'{mode}-worker{worker}.{ "rgba" if mode=="rga" else "nv12" }'
            raw=np.frombuffer(path.read_bytes(),dtype=np.uint8)
            if mode=='rga':
                assert len(raw)%(128*4)==0
                stride=len(raw)//128
                actual=raw.reshape(128,stride)[:,:512].reshape(128,128,4)
                yy,xx=np.indices((128,128));frame=a.frames-1
                expected=np.stack(((xx+worker*17+frame)%256,(yy*3+frame)%256,(xx+yy+worker)%256,np.full((128,128),255)),axis=-1).astype('uint8')
                equal=np.array_equal(actual,expected)
            else:
                assert len(raw)%192==0
                stride=len(raw)//192
                assert stride>=128
                actual=raw.reshape(192,stride)
                expected=np.fromfunction(lambda y,x:16+(x*3+y*5+worker*13)%220,(128,128),dtype=int).astype('uint8')
                equal=np.array_equal(actual[:128,:128],expected) and np.all(actual[128:,:128]==128)
            report[path.name]={'pixel_exact':bool(equal)};ok &= bool(equal)
    for mode,workers in [('rga',2),('jpeg',4),('h264',2)]:
        before={x.split()[0]:[int(v) for v in x.split()[1:]] for x in (base/f'{mode}.before').read_text().splitlines()}
        after={x.split()[0]:[int(v) for v in x.split()[1:]] for x in (base/f'{mode}.after').read_text().splitlines()}
        assert len(after)==workers and before.keys()==after.keys(),mode
        results={}
        for name,values in after.items():
            delta=[x-y for x,y in zip(values,before[name])]
            # users/submitted/completed/errors/IRQ
            passed=delta[0]==0 and delta[1]==a.frames and delta[2]==a.frames and delta[3]==0 and delta[4]>0
            results[name]={'delta':delta,'passed':passed};ok &= passed
        log=(base/f'{mode}.log').read_text()
        for i in range(workers): ok &= f'PASS {mode} worker={i} frames={a.frames} ' in log
        report[mode]=results
    report['pass']=bool(ok)
    (base/'host-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
