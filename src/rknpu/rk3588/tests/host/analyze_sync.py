"""主机证据复核。用 toolkit venv 的 Python 执行,不在板上安装依赖。

用法: ~/tools/rknn-toolkit-venv/bin/python analyze_sync_evidence.py <evidence-dir>
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import MODELS

def main():
    import numpy as np
    import onnxruntime as ort
    base = Path(sys.argv[1])
    report = {'evidence': str(base.resolve()), 'fp16_round_to_zero_threshold': 2.0**-25}
    for name, onnx_path in [('mobilenetv2_fp', MODELS / 'mobilenetv2.onnx'),
                            ('resnet18', MODELS / 'zoo/resnet18.onnx')]:
        session = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])
        meta = session.get_inputs()[0]
        reference = session.run(None, {meta.name: np.full(meta.shape, 85.3125, dtype=np.float32)})[0].reshape(-1)
        half = reference.astype(np.float16)
        info = {
            'onnx_sha256': hashlib.sha256(onnx_path.read_bytes()).hexdigest(),
            'input_value': 85.3125,
            'fp32_min': float(reference.min()), 'fp32_max': float(reference.max()),
            'fp32_nonzero': int(np.count_nonzero(reference)),
            'fp16_nonzero': int(np.count_nonzero(half)),
            'fp16_finite': bool(np.all(np.isfinite(half))),
        }
        directory = base / name
        if not directory.is_dir() and name == 'mobilenetv2_fp':
            directory = base  # 早期证据目录还没有按模型分层。
        blobs = []
        for impl in ('own', 'vendor'):
            path = directory / impl / 'out0.bin'
            if not path.is_file(): continue
            data = path.read_bytes()
            values = np.frombuffer(data, dtype='<f2')
            info[impl] = {'bytes': len(data), 'nonzero': int(np.count_nonzero(values)),
                          'finite': bool(np.all(np.isfinite(values)))}
            blobs.append(data)
        if len(blobs) == 2: info['byte_exact'] = blobs[0] == blobs[1]
        internal = directory / 'vendor/submit1-buf4-post.bin'
        if name == 'mobilenetv2_fp' and internal.is_file() and len(blobs) == 2:
            info['vendor_equals_internal_0xa00'] = internal.read_bytes()[0xa00:0xa00+2000] == blobs[1]
            info['buffers'] = []
            for i in range(1, 7):
                files = [directory / impl / f'submit1-buf{i}-{stage}.bin'
                         for impl, stage in [('own', 'pre'), ('own', 'post'), ('vendor', 'pre'), ('vendor', 'post')]]
                a, b, c, d = [p.read_bytes() for p in files]
                info['buffers'].append({'id': i, 'pre_equal': a == c, 'post_equal': b == d,
                                        'changed_bytes': sum(x != y for x, y in zip(a, b))})
        report[name] = info
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
