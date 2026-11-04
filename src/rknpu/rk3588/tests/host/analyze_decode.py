"""Inspect saved decode buffers, including failed scalar runs; never overrides failure."""
import argparse
import json
from collections import Counter
from pathlib import Path


def analyze(path):
    meta = json.loads(path.read_text())
    raw = path.with_suffix('.capture.bin').read_bytes()
    stride, width, height = meta['stride'], meta['width'], meta['height']
    if stride < width or len(raw) < stride * height * 3 // 2:
        return dict(metadata=meta, error='invalid NV12 layout', pixel_exact=False)
    planes = {}
    for plane, rows, offset in [('Y', height, 0), ('UV', height // 2, stride * height)]:
        values = bytearray()
        mismatch = 0
        first = None
        for y in range(rows):
            for x in range(width):
                at = offset + y * stride + x
                actual = raw[at]
                expected = 16 + (x * 3 + y * 5 + meta['worker'] * 13) % 220 if plane == 'Y' else 128
                values.append(actual)
                if actual != expected:
                    mismatch += 1
                    if first is None:
                        first = dict(x=x, y=y, offset=at, actual=actual, expected=expected)
        planes[plane] = dict(mismatches=mismatch, total=len(values), first_mismatch=first,
                             minimum=min(values), maximum=max(values),
                             unchanged_a5=values.count(0xa5), most_common=Counter(values).most_common(8))
    return dict(metadata=meta, planes=planes,
                pixel_exact=all(p['mismatches'] == 0 for p in planes.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('evidence')
    a = ap.parse_args()
    base = Path(a.evidence)
    results = {}
    for path in sorted(base.rglob('h264-worker*-frame*.json')):
        try:
            results[str(path.relative_to(base))] = analyze(path)
        except (OSError, ValueError, KeyError) as error:
            results[str(path.relative_to(base))] = dict(error=str(error), pixel_exact=False)
    (base / 'decode-analysis.json').write_text(json.dumps(results, indent=2) + '\n')
    if not results:
        print('No saved H264 frame evidence; rerun updated multicore demo.')
        return 1
    for name, result in results.items():
        print(name, 'pixel_exact=' + str(result['pixel_exact']))
        for plane, p in result.get('planes', {}).items():
            print(f"  {plane}: mismatch={p['mismatches']}/{p['total']} first={p['first_mismatch']}")
        if 'error' in result:
            print(' ', result['error'])
    return int(any(not r['pixel_exact'] for r in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
