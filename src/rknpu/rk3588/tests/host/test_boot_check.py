"""Exercise the real boot-check script with fixture sysfs and command outputs."""
from pathlib import Path
import os
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import BOARD
SOURCE = BOARD / 'verify_boot_cleanup.sh'


def main():
    text = SOURCE.read_text()
    drivers = dict(line.split() for line in text.split("<<'DEVICES'\n", 1)[1].split('\nDEVICES', 1)[0].splitlines())
    assert drivers['fdab0000.rknpu'] == 'RKNPU'
    assert len(drivers) == 23
    with tempfile.TemporaryDirectory(prefix='media-boot-check-') as td:
        base = Path(td)
        (base / 'bin').mkdir()
        (base / 'devices').mkdir()
        for name, driver in drivers.items():
            p = base / 'devices' / name
            p.mkdir()
            (p / 'driver').symlink_to(base / 'drivers' / driver)
        power = base / 'devices/fd8d8000.power-management:power-controller'
        power.mkdir()
        (power / 'state_synced').write_text('1\n')
        (base / 'iomem').write_text('fdab0000-fdab3fff : fdab0000.rknpu\n')
        for name, body in {
            'uname': 'echo ' + text.split('expected_kernel=', 1)[1].splitlines()[0] + '\n',
            'dmesg': 'cat "$FIXTURE_BASE/dmesg"\n',
        }.items():
            p = base / 'bin' / name
            p.write_text('#!/bin/sh\n' + body)
            p.chmod(0o755)
        (base / 'dmesg').write_text('fixture boot\n')
        (base / 'verify_legacy_sync.sh').write_text('echo fixture NPU PASS\nexit 0\n')
        script = text.replace('cd /opt/rknn-verify', 'cd "' + str(base) + '"')
        script = script.replace('/sys/bus/platform/devices/', str(base / 'devices') + '/')
        script = script.replace('/proc/iomem', str(base / 'iomem'))
        (base / 'boot.sh').write_text(script)
        def run():
            return subprocess.run(['sh', str(base / 'boot.sh')], capture_output=True, text=True,
                                  env=dict(os.environ, FIXTURE_BASE=str(base), PATH=str(base / 'bin') + ':' + os.environ['PATH']), timeout=10)
        p = run()
        assert p.returncode == 0, p.stdout + p.stderr
        npu = base / 'devices/fdab0000.rknpu/driver'
        npu.unlink()
        npu.symlink_to(base / 'drivers/rknpu')
        p = run()
        assert p.returncode == 1 and 'expected driver RKNPU' in p.stdout, p.stdout
        npu.unlink()
        npu.symlink_to(base / 'drivers/RKNPU')
        secondary = base / 'devices/fdb70f00.iommu/driver'
        secondary.unlink()
        p = run()
        assert p.returncode == 1 and 'expected driver rk_iommu' in p.stdout, p.stdout
        secondary.symlink_to(base / 'drivers/rk_iommu')
        (base / 'dmesg').write_text('rockchip-pm-domain: sync_state() pending due to fdb70000.rga\n')
        assert run().returncode == 1
    print('PASS boot checker: exact RKNPU binding, all 23 bindings, missing IOMMU and PM pending still fail')


def test_boot_check():
    main()


if __name__ == '__main__':
    main()
