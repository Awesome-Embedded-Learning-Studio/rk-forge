"""Build board verification assets into out/; does not contact or reboot the board."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from paths import ARTIFACTS, BOARD, OWN, ROOT, SDK_INCLUDE, VENDOR, cross_cc


def build(destination=None):
    dest = Path(destination) if destination else ARTIFACTS / 'board'
    for sub in ('bin', 'src', 'multicore'):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    runtime = VENDOR if (VENDOR / 'librknnrt.so').is_file() else OWN
    header = SDK_INCLUDE / 'rknn_api.h'
    if not header.is_file() or not (runtime / 'librknnrt.so').is_file():
        raise FileNotFoundError('Need external rknn_api.h and a runtime; set RKNN_SDK_INCLUDE / RKNN_VENDOR_DIR / RKNN_OWN_LIB_DIR')
    cc = cross_cc()
    flags = [cc, '-O2', '-Wall', '-Wextra', '-Werror']
    subprocess.run([*flags, '-I' + str(SDK_INCLUDE), str(BOARD / 'board_harness.c'),
                    '-L' + str(runtime), '-lrknnrt', '-o', str(dest / 'bin/board_harness')], check=True)
    subprocess.run([*flags, '-shared', '-fPIC', str(BOARD / 'legacy_trace.c'),
                    '-o', str(dest / 'bin/legacy_trace.so'), '-ldl', '-pthread'], check=True)
    subprocess.run([*flags, str(BOARD / 'multicore/media_demo.c'),
                    '-o', str(dest / 'multicore/media_demo')], check=True)
    sources = [(BOARD / name, name) for name in ('run.sh', 'verify_legacy_sync.sh', 'verify_boot_cleanup.sh')]
    sources += [(BOARD / name, 'src/' + name) for name in ('board_harness.c', 'legacy_trace.c')]
    sources += [(BOARD / 'multicore' / name, 'multicore/' + name)
                for name in ('run.sh', 'media_demo.c', 'expected-kernel', 'make_idr.py')]
    sources += [(ROOT / 'host/verify_media.py', 'multicore/verify_outputs.py'),
                (ROOT / 'host/analyze_decode.py', 'multicore/analyze_decode.py')]
    for src, rel in sources:
        target = dest / rel
        shutil.copy2(src, target)
        target.chmod(0o755 if rel.endswith('.sh') else 0o644)
    subprocess.run([sys.executable, str(BOARD / 'multicore/make_idr.py'),
                    '--output-dir', str(dest / 'multicore/assets')], check=True)
    hashes = {str(p.relative_to(dest)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(dest.rglob('*')) if p.is_file() and p.name != 'build-manifest.json'}
    (dest / 'build-manifest.json').write_text(json.dumps({'compiler': cc, 'sha256': hashes}, indent=2) + '\n')
    print('Board bundle:', dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output-dir')
    args = ap.parse_args()
    build(args.output_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
