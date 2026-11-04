"""Host execution of the actual demo against a mock V4L2 device, plus failure evidence."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import tempfile


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import BOARD, FIXTURES, ROOT, artifact_dir, cross_cc
MULTICORE = BOARD / "multicore"


def main():
    import numpy as np
    from PIL import Image
    base = artifact_dir('media-demo')
    (base / 'assets').mkdir()
    spec = importlib.util.spec_from_file_location('analyze_decode', ROOT / 'host/analyze_decode.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    demo, mock = base / 'media_demo', base / 'mock_v4l2.so'
    subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', str(MULTICORE / 'media_demo.c'), '-o', str(demo)], check=True)
    subprocess.run([cross_cc(), '-O2', '-Wall', '-Wextra', '-Werror', str(MULTICORE / 'media_demo.c'), '-o', str(base / 'media_demo.aarch64')], check=True)
    # Suppression applies only to the glibc poll wrapper in this host test double.
    subprocess.run(['gcc', '-O2', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                    '-Wno-maybe-uninitialized', str(FIXTURES / 'mock_v4l2.c'), '-o', str(mock), '-ldl'], check=True)
    for i in range(4):
        y = np.fromfunction(lambda row, x: 16 + (x*3 + row*5 + i*13) % 220, (128, 128), dtype=int).astype('uint8')
        Image.fromarray(y).save(base / f'assets/mock-worker{i}.jpg', quality=90)
    subprocess.run([sys.executable, str(MULTICORE / 'make_idr.py'), '--output-dir', str(base / 'assets')], check=True)
    results = []
    for mode, workers in [('rga', 2), ('jpeg', 4), ('h264', 2)]:
        for bad in ('valid', 'corrupt', 'hardware_error') if mode == 'h264' else ('valid', 'corrupt'):
            dest = base / f'{mode}-{bad}'
            dest.mkdir()
            env = dict(os.environ, LD_PRELOAD=str(mock), TEST_MODE=mode)
            if bad == 'corrupt':
                env['TEST_CORRUPT'] = '1'
            if bad == 'hardware_error':
                env['TEST_HW_ERROR'] = '1'
            p = subprocess.run([str(demo), mode, '/dev/null', str(workers), '4', str(dest)],
                               cwd=base, env=env, capture_output=True, text=True, timeout=20)
            (dest / 'demo.log').write_text(p.stdout + p.stderr)
            assert (p.returncode == 0) == (bad == 'valid'), (mode, bad, p.stdout, p.stderr)
            if mode == 'h264':
                metadata = sorted(dest.glob('h264-worker*-frame0.json'))
                assert len(metadata) == workers, (mode, bad, metadata)
                for path in metadata:
                    data = analyzer.analyze(path)
                    assert data['pixel_exact'] == (bad != 'corrupt'), data
                    if bad == 'hardware_error':
                        assert data['metadata']['capture_flags'] & 0x40
                    if bad == 'corrupt':
                        assert data['planes']['Y']['mismatches'] == 1
                        assert 'actual=' in p.stderr and 'expected=' in p.stderr
            results.append(dict(mode=mode, case=bad, exit=p.returncode))
            print('PASS', mode, bad, 'exit', p.returncode)
    # Reproduce the old JPEG ordering with the same mock: OUTPUT allocated before
    # CAPTURE S_FMT must fail with EBUSY, matching hantro_set_fmt_cap().
    current = (MULTICORE / 'media_demo.c').read_text()
    jpeg_marker = 'format_queue(fd,&dst,V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,dstfmt,W*H*4);\n        format_queue(fd,&src,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,srcfmt,0);'
    assert current.count(jpeg_marker) == 1
    old_jpeg = current.replace(jpeg_marker,
        'format_queue(fd,&src,V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE,srcfmt,0);\n'
        '        allocate_queue(fd,&src);\n'
        '        format_queue(fd,&dst,V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE,dstfmt,W*H*4);')
    sps_marker = 'if(dec)h264_controls(fd,-1);'
    assert current.count(sps_marker) == 1
    old_h264 = current.replace(sps_marker, '/* regression: omit initial SPS */')
    for mode, bad_source, error in [('jpeg', old_jpeg, 'Device or resource busy'),
                                    ('h264', old_h264, 'decoded pixels')]:
        source, binary = base / ('old-' + mode + '.c'), base / ('old-' + mode)
        source.write_text(bad_source)
        subprocess.run(['gcc', '-O2', str(source), '-o', str(binary)], check=True)
        dest = base / ('old-' + mode + '-results')
        dest.mkdir()
        p = subprocess.run([str(binary), mode, '/dev/null', '1', '2', str(dest)], cwd=base,
                           env=dict(os.environ, LD_PRELOAD=str(mock), TEST_MODE=mode), capture_output=True, text=True, timeout=20)
        assert p.returncode != 0 and error in p.stderr, p.stderr
        (dest / 'demo.log').write_text(p.stdout + p.stderr)
        print('PASS regression guard:', mode, error)
    (base / 'verification.json').write_text(json.dumps(results, indent=2) + '\n')
    print('Evidence:', base)
    return 0


def test_media_demo():
    import importlib.util
    from unittest import SkipTest
    if not all(importlib.util.find_spec(name) for name in ('numpy', 'PIL')):
        raise SkipTest('media fixtures need numpy and Pillow')
    try:
        cross_cc()
    except FileNotFoundError as error:
        raise SkipTest(str(error))
    main()


if __name__ == '__main__':
    raise SystemExit(main())
