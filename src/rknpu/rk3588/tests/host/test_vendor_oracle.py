"""Compare real vendor/own runtimes under QEMU with a simulated device.

Checks full submission sequence and nonzero CPU tensor transformations, not NPU
hardware arithmetic. Generates variants of the existing fake kernel in artifacts;
never patches the vendor library or the original fixture.
"""
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import REPO, ROOT, BOARD, MODELS as RKNN, OWN, ROOTFS, VENDOR, ARTIFACTS, FIXTURES, cross_cc
LIBS = {'own': OWN, 'vendor': VENDOR}
MODELS = ['dualout', 'googlenet', 'mbv3s', 'mobilenetv2_fp', 'mobilenetv2_i8',
          'resnet18', 'resnet18_i8', 'shufflenet', 'squeezenet']
INJECTION = '''int n = 0;
        for (int gi = 0; gi < MAX_GEM; gi++) {
            struct gem *g = &gems[gi];
            if (g->handle != 4 || g->dead) continue;
            dump_one_gem(g, submit_no);
            uint16_t *fixture = malloc(g->size);
            if (!fixture) abort();
            for (uint64_t j = 0; j < g->size / 2; j++) fixture[j] = 0x1000 + j % 0x3000;
            if (pwrite(g->fd, fixture, g->size, 0) != (ssize_t)g->size) abort();
            free(fixture);
        }'''


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix='host-oracle.', dir=ARTIFACTS))
    original = (FIXTURES / 'fakekern_dump.c').read_text()
    marker = 'int n = dump_all(submit_no);'
    assert original.count(marker) == 1
    stubs = {}
    for kind, replacement in [('schedule', 'int n = 0;'), ('cpu', INJECTION),
                              ('assembly', 'int n = submit_no == 1 ? dump_all(submit_no) : 0;')]:
        source, library = evidence / (kind + '.c'), evidence / (kind + '.so')
        source.write_text(original.replace(marker, replacement))
        subprocess.run([cross_cc(), '-shared', '-fPIC', '-O2', str(source), '-o', str(library), '-ldl'], check=True)
        stubs[kind] = library

    def run(item):
        name, impl, mask, kind = item
        dest = evidence / f'{kind}-{name}-{impl}-mask{mask}'
        dest.mkdir()
        model = RKNN / (f'{name}.rknn' if name.startswith('mobilenetv2_') else f'zoo/{name}.rknn')
        p = subprocess.run([
            'qemu-aarch64-static', '-L', str(ROOTFS),
            '-E', 'LD_LIBRARY_PATH=' + str(LIBS[impl]),
            '-E', 'LD_PRELOAD=' + str(stubs[kind]),
            '-E', 'RKNN_DUMP_DIR=' + str(dest),
            str(ARTIFACTS / 'board/bin/board_harness'), str(model), str(dest), str(mask),
        ], capture_output=True, timeout=60)
        (dest / 'harness.log').write_bytes(p.stdout + p.stderr)
        schedule = []
        for line in p.stderr.decode(errors='replace').splitlines():
            if 'SUBMIT#' in line:
                schedule.append(re.sub(r'task_obj_addr=0x[0-9a-f]+', 'task_obj_addr=NORMALIZED', line))
            elif 'subcore_task' in line:
                schedule.append(line)
        return item, (p.returncode, schedule, dest)

    cases = [(n, impl, mask, 'schedule') for n in MODELS
             for impl in LIBS for mask in (0, 1, 2, 3, 4, 7)]
    cases += [(n, impl, 0, 'cpu') for n in ('mbv3s', 'shufflenet', 'dualout') for impl in LIBS]
    cases += [(n, impl, 0, 'assembly') for n in MODELS for impl in LIBS]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(run, cases))
    failures = []
    schedule_pass = 0
    for name in MODELS:
        for mask in (0, 1, 2, 3, 4, 7):
            a, b = [results[name, impl, mask, 'schedule'] for impl in LIBS]
            if a[0] == 0 and a[:2] == b[:2] and a[1]:
                schedule_pass += 1
            else:
                failures.append(f'schedule {name} mask={mask}: see per-implementation harness.log')
    print(f'SUBMISSION ORACLE: {schedule_pass}/54 PASS (9 models x 6 masks)')
    assembly_pass = 0
    for name in MODELS:
        a, b = [results[name, impl, 0, 'assembly'] for impl in LIBS]
        snapshots = [set(p.name for p in r[2].glob('s1_gem*.bin')) for r in (a, b)]
        good = a[0] == 0 and a[:2] == b[:2] and snapshots[0] == snapshots[1]
        good = good and len(snapshots[0]) == (7 if name == 'dualout' else 6)
        for filename in snapshots[0] | snapshots[1]:
            x, y = a[2] / filename, b[2] / filename
            if not (x.is_file() and y.is_file() and x.read_bytes() == y.read_bytes()):
                failures.append(f'assembly mismatch {name}/{filename}')
                good = False
        if good:
            assembly_pass += 1
        else:
            failures.append(f'assembly oracle {name}: inspect first-submit GEM snapshots')
    print(f'ASSEMBLY ORACLE: {assembly_pass}/9 PASS (all first-submit GEMs byte-identical)')
    cpu_pass = 0
    for name, expected_submits in [('mbv3s', 57), ('shufflenet', 17), ('dualout', 2)]:
        a, b = [results[name, impl, 0, 'cpu'] for impl in LIBS]
        good = a[0] == 0 and a[:2] == b[:2]
        snapshots = [set(p.name for p in r[2].glob('s*_gem4_*.bin')) for r in (a, b)]
        good = good and snapshots[0] == snapshots[1] and len(snapshots[0]) == expected_submits
        for filename in snapshots[0] | snapshots[1]:
            x, y = a[2] / filename, b[2] / filename
            if not (x.is_file() and y.is_file() and x.read_bytes() == y.read_bytes()):
                failures.append(f'CPU snapshot mismatch {name}/{filename}')
                good = False
        outputs = [set(p.name for p in r[2].glob('out*.bin')) for r in (a, b)]
        expected_outputs = {'out0.bin', 'out1.bin'} if name == 'dualout' else {'out0.bin'}
        good = good and outputs[0] == outputs[1] == expected_outputs
        for filename in outputs[0] | outputs[1]:
            x, y = a[2] / filename, b[2] / filename
            if not (x.is_file() and y.is_file() and x.stat().st_size and x.read_bytes() == y.read_bytes()):
                failures.append(f'output mismatch {name}/{filename}')
                good = False
        if good:
            cpu_pass += 1
            print(f'CPU ORACLE PASS {name}: {expected_submits} submissions, all activation snapshots + outputs byte-identical')
        else:
            failures.append(f'CPU oracle {name}: inspect logs/snapshots')
    report = {'schedule_pass': schedule_pass, 'schedule_total': 54, 'cpu_pass': cpu_pass,
              'cpu_total': 3, 'assembly_pass': assembly_pass, 'assembly_total': 9,
              'failures': failures, 'hardware_inference': 'NOT_TESTED'}
    (evidence / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Evidence:', evidence)
    for failure in failures:
        print('FAIL:', failure)
    return int(bool(failures))


def test_vendor_oracle():
    import os
    from unittest import SkipTest
    if os.environ.get('RKNN_RUN_VENDOR_ORACLE') != '1':
        raise SkipTest('opt in with RKNN_RUN_VENDOR_ORACLE=1 after build_board.py')
    assert main() == 0


if __name__ == '__main__':
    raise SystemExit(main())
