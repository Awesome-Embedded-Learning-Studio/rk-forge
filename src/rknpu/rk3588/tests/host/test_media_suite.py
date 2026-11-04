from pathlib import Path
import os,subprocess,tempfile,sys,textwrap
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import REPO, ROOT, BOARD, artifact_dir


def main():
    from PIL import Image
    import numpy as np
    repo=REPO;base=artifact_dir('media-suite')
    (base/'multicore/assets').mkdir(parents=True);(base/'bin').mkdir();(base/'devices').mkdir();(base/'video').mkdir()
    roles={'rga':['fdb60000.rga','fdb70000.rga'],'jpeg':['fdba0000.video-codec','fdba4000.video-codec','fdba8000.video-codec','fdbac000.video-codec'],'h264':['fdc38000.video-codec','fdc40000.video-codec']}
    for mode,devices in roles.items():
     for d in devices:
      p=base/'devices'/d;p.mkdir();(p/'driver').symlink_to(base/'drivers/mock')
      for s in ['users','submitted','completed','errors']:(p/f'm2m_core_{s}').write_text('0\n')
    for i,d in enumerate([x[0] for x in roles.values()]):
     p=base/f'video/video{i}';p.mkdir();(p/'device').symlink_to(base/'devices'/d)
    (base/'devices/fd8d8000.power-management:power-controller').mkdir()
    (base/'devices/fd8d8000.power-management:power-controller/state_synced').write_text('1\n')
    (base/'interrupts').write_text(''.join(f'{i}: 0 0 0 0 0 0 0 0 GIC {d}\n' for i,d in enumerate(sum(roles.values(),[]))))
    (base/'multicore/expected-kernel').write_text('fixture-kernel\n')
    (base/'verify_boot_cleanup.sh').write_text('echo fixture boot checks PASS\nexit 0\n')
    (base/'bin/uname').write_text('#!/bin/sh\necho fixture-kernel\n');(base/'bin/uname').chmod(0o755)
    (base/'verify_legacy_sync.sh').write_text('echo fixture NPU PASS\nexit 0\n')
    (base/'bin/dmesg').write_text('#!/bin/sh\necho fixture boot\n');(base/'bin/dmesg').chmod(0o755)
    y=np.fromfunction(lambda row,x:16+(x*3+row*5)%220,(128,128),dtype=int).astype('uint8');
    for i in range(4):
     y=np.fromfunction(lambda row,x:16+(x*3+row*5+i*13)%220,(128,128),dtype=int).astype('uint8')
     Image.fromarray(y).save(base/f'multicore/assets/reference{i}.jpg',quality=90)
    (base/'multicore/media_demo').write_text('''#!__TEST_PYTHON__
    from pathlib import Path
    import json,os,shutil,sys
    base=Path(__file__).resolve().parents[1]
    roles=json.loads(os.environ['ROLE_JSON']);mode=sys.argv[1];frames=int(sys.argv[4]);out=Path(sys.argv[5]);case=os.environ.get('MOCK_CASE','good')
    irq=(base/'interrupts').read_text().splitlines()
    for i,d in enumerate(roles[mode]):
     count=0 if case=='idle' and i==1 else frames
     for stat in ['submitted','completed','errors']:
      p=base/'devices'/d/f'm2m_core_{stat}'
      p.write_text(str(int(p.read_text())+(1 if case=='error' and stat=='errors' else 0 if stat=='errors' else count))+'\\n')
     for j,line in enumerate(irq):
      if line.endswith(d):
       parts=line.split();parts[1]=str(int(parts[1])+count);irq[j]=' '.join(parts)
     print(f'PASS {mode} worker={i} frames={frames} elapsed=0.1')
     if mode=='rga':
      data=bytes(value for y in range(128) for x in range(128) for value in [(x+i*17+frames-1)%256,(y*3+frames-1)%256,(x+y+i)%256,255]);(out/f'rga-worker{i}.rgba').write_bytes(data)
     if mode=='h264':
      data=bytes(16+(x*3+y*5+i*13)%220 for y in range(128) for x in range(128))+bytes([128])*8192;(out/f'h264-worker{i}.nv12').write_bytes(data)
     if mode=='jpeg':shutil.copy(base/f'multicore/assets/reference{i}.jpg',out/f'jpeg-worker{i}.jpg')
    (base/'interrupts').write_text('\\n'.join(irq)+'\\n')
    ''');generated=(base/'multicore/media_demo').read_text().replace('__TEST_PYTHON__',sys.executable)
    head,body=generated.split('\n',1)
    (base/'multicore/media_demo').write_text(head+'\n'+textwrap.dedent(body));(base/'multicore/media_demo').chmod(0o755)
    s=(BOARD/'multicore/run.sh').read_text().replace('BASE=/opt/rknn-verify',f'BASE={base}').replace('/sys/bus/platform/devices/',f'{base}/devices/').replace('/sys/class/video4linux/',f'{base}/video/').replace('/proc/interrupts',str(base/'interrupts')).replace('[ "$waited" -lt 25 ]','[ "$waited" -lt 0 ]')
    (base/'run.sh').write_text(s)
    import json
    logs=[]
    for case,expected in [('good',0),('idle',1),('error',1)]:
     r=subprocess.run(['sh',str(base/'run.sh')],env=dict(os.environ,PATH=str(base/'bin')+':'+os.environ['PATH'],FRAMES='4',MOCK_CASE=case,ROLE_JSON=json.dumps(roles)),capture_output=True,text=True)
     assert r.returncode==expected,(case,r.stdout,r.stderr)
     logs.append(f'{case}: exit {r.returncode}, expected {expected}\n'+r.stdout)
     print(case,'suite exit',r.returncode)
     if case=='good':
      evidence=Path(next(x[len('Evidence: '):] for x in r.stdout.splitlines() if x.startswith('Evidence: ')))
      check=ROOT/'host/verify_media.py'
      p=subprocess.run([sys.executable,str(check),str(evidence),'--frames','4'],capture_output=True,text=True)
      assert p.returncode==0,p.stderr+p.stdout
      Image.fromarray(np.zeros((128,128),dtype='uint8')).save(evidence/'jpeg-worker0.jpg')
      p=subprocess.run([sys.executable,str(check),str(evidence),'--frames','4'],capture_output=True,text=True)
      assert p.returncode==1,p.stderr+p.stdout
      print('JPEG host verifier: valid accepted, black/corrupt content rejected')
    (base/'suite-fixtures.log').write_text('\n'.join(logs))
    print('Evidence:', base)


def test_media_suite():
    import importlib.util
    from unittest import SkipTest
    if not all(importlib.util.find_spec(name) for name in ('numpy', 'PIL')):
        raise SkipTest('media fixtures need numpy and Pillow')
    main()


if __name__ == '__main__':
    main()
