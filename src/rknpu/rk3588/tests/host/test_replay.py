"""Regression: never collapse different submission snapshots or accept empty inputs."""
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    script = Path(__file__).with_name('compare_replay.py')
    with tempfile.TemporaryDirectory(prefix='rknn-replay-') as td:
        a, b = Path(td) / 'a', Path(td) / 'b'
        a.mkdir(); b.mkdir()
        def run(*args):
            return subprocess.run([sys.executable, str(script), str(a), str(b), *args], capture_output=True, text=True)
        assert run().returncode == 1
        name = 'gem3_f0xb_40B_dma0x50300000.bin'
        for d in (a, b):
            (d / ('s1_' + name)).write_bytes(b'matching')
        assert run().returncode == 0
        (a / ('s2_' + name)).write_bytes(b'matching')
        assert run().returncode == 1
        (b / ('s2_' + name)).write_bytes(b'matching')
        (a / ('s1_' + name)).write_bytes(b'different')
        assert run().returncode == run('--task-only').returncode == 1
        (a / ('s1_' + name)).write_bytes(b'matching')
        assert run('--task-only').returncode == 0
    print('PASS replay comparator: empty/missing/earlier-submit mismatch/task-only union')
    return 0


def test_replay():
    main()


if __name__ == '__main__':
    raise SystemExit(main())
