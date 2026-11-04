"""The NPU evidence audit must reject missing, mismatched and nonfinite outputs."""
from pathlib import Path
import struct
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_npu import SIZES, check_model


def main():
    with tempfile.TemporaryDirectory(prefix='rknn-evidence-') as td:
        base = Path(td)
        for impl in ('own', 'vendor'):
            d = base / impl / 'resnet18'
            d.mkdir(parents=True)
            (d / 'out0.bin').write_bytes(struct.pack('<e', 1.0) * 1000)
            (d / 'harness.log').write_text('rknn_init ret=0\nn_input=1 n_output=1\nrknn_run ret=0\n'
                '#### HARNESS: rknn_outputs_get ####\n=> ret=0\n=> out[0] size=2000\n#### HARNESS: done ####\n')
        assert check_model(base, 'resnet18')['pass_']
        own = base / 'own/resnet18/out0.bin'
        original = own.read_bytes()
        own.unlink()
        try:
            check_model(base, 'resnet18')
            raise RuntimeError('missing output accepted')
        except AssertionError:
            pass
        for bad in (b'\0' * 2000, struct.pack('<e', float('nan')) * 1000):
            for impl in ('own', 'vendor'):
                (base / impl / 'resnet18/out0.bin').write_bytes(bad)
            try:
                check_model(base, 'resnet18')
                raise RuntimeError('zero/NaN output accepted')
            except AssertionError:
                pass
        own.write_bytes(original)
        try:
            check_model(base, 'resnet18')
            raise RuntimeError('different output accepted')
        except AssertionError:
            pass
    assert len(SIZES) == 9
    print('PASS NPU evidence: complete/nonzero/finite/byte-identical requirements')
    return 0


def test_npu_evidence():
    main()


if __name__ == '__main__':
    raise SystemExit(main())
