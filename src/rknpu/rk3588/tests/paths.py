"""Shared paths for RK3588 tests; generated artifacts stay outside the source tree."""
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
BOARD = ROOT / 'board'
FIXTURES = ROOT / 'fixtures'
MODELS = Path(os.environ.get('RKNN_MODEL_DIR', str(REPO / '.claude/rknn'))).resolve()
ENGINE = Path(os.environ.get('RKNN_ENGINE_DIR', str(ROOT.parent))).resolve()
KERNEL = Path(os.environ.get('RKNN_KERNEL_DIR', str(REPO / 'third_party/src/rk3588-topeet/linux'))).resolve()
ROOTFS = Path(os.environ.get('RKNN_TEST_ROOTFS', str(REPO / 'out/rk3588-topeet/rootfs'))).resolve()
VENDOR = Path(os.environ.get('RKNN_VENDOR_DIR', str(REPO / 'reference/rk3588/external/rknpu2/runtime/RK3588/Linux/librknn_api/aarch64'))).resolve()
SDK_INCLUDE = Path(os.environ.get('RKNN_SDK_INCLUDE', str(VENDOR.parent / 'include'))).resolve()
OWN = Path(os.environ.get('RKNN_OWN_LIB_DIR', str(REPO / 'out/rk3588-topeet/rknpu-runtime/aarch64'))).resolve()
ARTIFACTS = Path(os.environ.get('RKNN_TEST_ARTIFACTS', str(REPO / 'out/rk3588-topeet/rknpu-tests'))).resolve()


def artifact_dir(prefix):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix + '.', dir=ARTIFACTS))


def cross_cc():
    explicit = os.environ.get('RKNN_CROSS_CC')
    if explicit:
        found = shutil.which(explicit)
        if not found:
            raise FileNotFoundError('RKNN_CROSS_CC compiler not found: ' + explicit)
        return found
    prefix = os.environ.get('CROSS_COMPILE')
    if prefix:
        found = shutil.which(prefix + 'gcc')
        if not found:
            raise FileNotFoundError('CROSS_COMPILE compiler not found: ' + prefix + 'gcc')
        return found
    found = shutil.which('aarch64-linux-gnu-gcc')
    if found:
        return found
    for path in sorted(Path('/opt').glob('arm-gnu-toolchain-*-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-gcc'), reverse=True):
        if path.is_file():
            return str(path)
    raise FileNotFoundError('AArch64 compiler missing; set RKNN_CROSS_CC or CROSS_COMPILE')
