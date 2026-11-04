"""Run RK3588 validation suites locally. No board connection, reboot or flash."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

SUITES = {
    'basic': ['test_board_runner.py', 'test_boot_check.py', 'test_replay.py', 'test_npu_evidence.py', 'test_corepool.py'],
    'media': ['test_media_demo.py', 'test_media_suite.py'],
    'native': [],
    'oracle': ['test_vendor_oracle.py'],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--suite', choices=[*SUITES, 'all'], default='basic')
    ap.add_argument('--sync-evidence', help='old traced MobileNet evidence for the native snapshot test')
    for flag in ('model-dir', 'engine-dir', 'kernel-dir', 'vendor-dir', 'artifact-dir', 'rootfs', 'cross-cc', 'sdk-include', 'own-lib-dir'):
        ap.add_argument('--' + flag)
    a = ap.parse_args()
    mapping = {'model_dir': 'RKNN_MODEL_DIR', 'engine_dir': 'RKNN_ENGINE_DIR', 'kernel_dir': 'RKNN_KERNEL_DIR',
               'vendor_dir': 'RKNN_VENDOR_DIR', 'artifact_dir': 'RKNN_TEST_ARTIFACTS',
               'rootfs': 'RKNN_TEST_ROOTFS', 'cross_cc': 'RKNN_CROSS_CC',
               'sdk_include': 'RKNN_SDK_INCLUDE', 'own_lib_dir': 'RKNN_OWN_LIB_DIR'}
    for attr, env in mapping.items():
        value = getattr(a, attr)
        if value:
            os.environ[env] = str(Path(value).resolve()) if attr != 'cross_cc' else value
    from paths import ROOT, REPO, ENGINE, MODELS, SDK_INCLUDE, artifact_dir
    os.environ['RKNN_MODEL_DIR'] = str(MODELS)
    evidence = artifact_dir('host-run')
    suites = list(SUITES) if a.suite == 'all' else [a.suite]
    results = []

    def run(label, command):
        print('RUN', label, flush=True)
        p = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
        log = p.stdout + p.stderr
        (evidence / (label + '.log')).write_text(log)
        print(log, end='' if log.endswith('\n') else '\n', flush=True)
        results.append({'test': label, 'exit': p.returncode})
        return p.returncode == 0

    for suite in suites:
        if suite == 'native':
            build_dir = evidence / 'native-build'
            configure = ['cmake', '-S', str(ENGINE), '-B', str(build_dir), '-G', 'Ninja',
                         '-DCMAKE_BUILD_TYPE=RelWithDebInfo', '-DRKNN_BUILD_TESTS=ON',
                         '-DRKNN_ENABLE_SANITIZERS=ON', '-DRKNN_SDK_INCLUDE=' + str(SDK_INCLUDE),
                         '-DRKNN_MODEL_DIR=' + str(MODELS), '-DRKNN_TEST_SOURCE_DIR=' + str(ROOT)]
            if a.sync_evidence:
                configure.append('-DRKNN_SYNC_EVIDENCE=' + str(Path(a.sync_evidence).resolve()))
            if run('native-configure', configure) and run('native-build', ['cmake', '--build', str(build_dir), '-j', '4']):
                run('native-ctest', ['ctest', '--test-dir', str(build_dir), '--output-on-failure'])
            if not a.sync_evidence:
                print('SKIP output snapshot: supply --sync-evidence to register the recorded-board-buffer regression', flush=True)
            continue
        if suite == 'oracle':
            if not run('board-build', [sys.executable, str(ROOT / 'build_board.py')]):
                continue
        for name in SUITES[suite]:
            run(name[:-3],
                [sys.executable, str(ROOT / 'host' / name)])
    report = {'pass': bool(results) and all(r['exit'] == 0 for r in results), 'results': results,
              'sync_snapshot_selected': bool(a.sync_evidence), 'hardware_tested': False}
    (evidence / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Evidence:', evidence)
    print('PASS' if report['pass'] else 'FAIL', 'host validation; hardware acceptance is separate')
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
