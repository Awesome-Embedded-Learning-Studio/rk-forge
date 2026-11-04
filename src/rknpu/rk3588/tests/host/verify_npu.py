"""Audit nine-model board evidence: complete outputs, successful APIs, finite/nonzero/byte-exact."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

SIZES = {name: [2000] for name in ('googlenet', 'mbv3s', 'mobilenetv2_fp', 'resnet18', 'shufflenet', 'squeezenet')}
SIZES.update(dualout=[15680, 64], mobilenetv2_i8=[1000], resnet18_i8=[1000])


def check_model(base, name):
    sizes = SIZES[name]
    expected = {'out%d.bin' % i for i in range(len(sizes))}
    directories = [base / impl / name for impl in ('own', 'vendor')]
    for directory in directories:
        assert {p.name for p in directory.glob('out*.bin')} == expected, 'missing/extra output: ' + str(directory)
        log = (directory / 'harness.log').read_text()
        assert not re.search(r'ret=-[0-9]+', log), 'API failure: ' + str(directory)
        assert 'rknn_init ret=0' in log and 'rknn_run ret=0' in log and 'HARNESS: done' in log
        assert re.search(r'n_input=1 n_output=%d\b' % len(sizes), log), 'wrong IO count'
        assert re.search(r'HARNESS: rknn_outputs_get.*?=> ret=0\b', log, re.S), 'outputs_get failed/missing'
        entries = [(int(i), int(size)) for i, size in re.findall(r'=> out\[(\d+)\] size=(\d+)', log)]
        assert entries == list(enumerate(sizes)), 'wrong output manifest'
    outputs = []
    for i, size in enumerate(sizes):
        filename = 'out%d.bin' % i
        blobs = [(d / filename).read_bytes() for d in directories]
        assert len(blobs[0]) == len(blobs[1]) == size, 'wrong byte length: ' + filename
        assert blobs[0] == blobs[1], 'output differs: ' + filename
        dtype = '<b' if name.endswith('_i8') else '<e'
        values = [v[0] for v in struct.iter_unpack(dtype, blobs[0])]
        assert all(math.isfinite(v) for v in values), 'NaN/Inf: ' + filename
        nonzero = sum(v != 0 for v in values)
        minimum = 0 if name == 'mobilenetv2_fp' else 901 if name == 'resnet18' else 1
        assert nonzero >= minimum, 'unexpected zero output: ' + filename
        outputs.append(dict(file=filename, bytes=size, elements=len(values), nonzero=nonzero,
                            finite=True, byte_exact=True, sha256=hashlib.sha256(blobs[0]).hexdigest()))
    return dict(pass_=True, outputs=outputs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('evidence', type=Path)
    args = ap.parse_args(argv)
    results = {}
    for name in sorted(SIZES):
        try:
            results[name] = check_model(args.evidence, name)
            print('PASS', name)
        except (OSError, AssertionError, ValueError, struct.error) as error:
            results[name] = dict(pass_=False, error=str(error))
            print('FAIL', name, str(error))
    passed = sum(r['pass_'] for r in results.values())
    report = dict(models=results, models_pass=passed, outputs_expected=10)
    report['pass'] = passed == len(SIZES)
    (args.evidence / 'npu-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('%d/%d PASS' % (passed, len(SIZES)))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
