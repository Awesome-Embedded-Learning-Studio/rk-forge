"""Host fixtures: output isolation and harness failure propagation; no NPU needed."""
import os
from pathlib import Path
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import BOARD as HERE, SDK_INCLUDE
STUB = r'''
#include <stdlib.h>
#include <string.h>
#include "rknn_api.h"
static int fault(const char *s) { const char *f=getenv("HARNESS_FAULT"); return f && !strcmp(f,s); }
int rknn_init(rknn_context *c, void *m, uint32_t s, uint32_t f, rknn_init_extend *e)
{ *c=1; return fault("init") ? -1 : 0; }
int rknn_destroy(rknn_context c) { return fault("destroy") ? -1 : 0; }
int rknn_set_core_mask(rknn_context c, rknn_core_mask m) { return fault("mask") ? -1 : 0; }
int rknn_query(rknn_context c, rknn_query_cmd q, void *p, uint32_t s) {
 if(q==RKNN_QUERY_IN_OUT_NUM) {
  rknn_input_output_num *io=p; io->n_input=fault("multiinput") ? 2 : 1;
  io->n_output=fault("nooutputs") ? 0 : fault("manyoutputs") ? 17 : 2;
  return fault("query") ? -1 : 0;
 }
 rknn_tensor_attr *a=p; a->size=4; a->n_elems=2;
 return fault("attr") ? -1 : 0;
}
int rknn_inputs_set(rknn_context c,uint32_t n,rknn_input in[]) { return fault("inputs") ? -1 : 0; }
int rknn_run(rknn_context c,rknn_run_extend *e) { return fault("run") ? -110 : 0; }
int rknn_outputs_get(rknn_context c,uint32_t n,rknn_output out[],rknn_output_extend *e) {
 static unsigned char b[4]={1,2,3,4};
 if(fault("get")) return -5;
 for(uint32_t i=0;i<n;i++) {
  if(out[i].index != i) return -5;
  out[i].buf=fault("null") ? NULL : b; out[i].size=fault("zero") ? 0 : 4;
 }
 return 0;
}
int rknn_outputs_release(rknn_context c,uint32_t n,rknn_output out[]) { return fault("release") ? -1 : 0; }
'''
MOCK_RUNNER = '''#!/bin/sh
name=$(basename "$1" .rknn)
case "$LD_LIBRARY_PATH" in */own) impl=own;; *) impl=vendor;; esac
case "$name" in
 a-dualfail)
  [ "$impl" = own ] && exit 1
  printf dual > "$2/out0.bin"
  printf tail > "$2/out1.bin" ;;
 b-single) printf same > "$2/out0.bin" ;;
 c-diff) printf '%s' "$impl" > "$2/out0.bin" ;;
 d-empty) : ;;
 e-missing)
  printf same > "$2/out0.bin"
  [ "$impl" = own ] || printf tail > "$2/out1.bin" ;;
esac
exit 0
'''


def main():
    with tempfile.TemporaryDirectory(prefix="rknn-runner-") as td:
        base = Path(td)
        for sub in ("bin", "models", "own", "vendor", "results/own", "results/vendor"):
            (base / sub).mkdir(parents=True, exist_ok=True)
        (base / "bin/board_harness").write_text(MOCK_RUNNER)
        (base / "bin/board_harness").chmod(0o755)
        for name in ("a-dualfail", "b-single", "c-diff", "d-empty", "e-missing"):
            (base / f"models/{name}.rknn").write_bytes(b"x")
        (base / "results/vendor/out1.bin").write_bytes(b"stale")
        env = dict(os.environ, RKNN_VERIFY_BASE=str(base))
        p = subprocess.run(["sh", str(HERE / "run.sh")], env=env, capture_output=True, text=True)
        assert p.returncode == 1, p.stdout
        assert "SUMMARY: 1/5 PASS" in p.stdout, p.stdout
        assert "==== b-single ====\nPASS  (1 outputs byte-identical)" in p.stdout, p.stdout
        evidence = next((base / "results").glob("npu-models.*"))
        assert (evidence / "vendor/a-dualfail/out1.bin").read_bytes() == b"tail"
        assert (evidence / "own/b-single/out0.bin").read_bytes() == b"same"
        assert (base / "results/vendor/out1.bin").read_bytes() == b"stale"
        p = subprocess.run(["sh", str(HERE / "run.sh"), str(base / "models/b-single.rknn")],
                           env=env, capture_output=True, text=True)
        assert p.returncode == 0 and "1/1 PASS" in p.stdout, p.stdout
        assert len(list((base / "results").glob("npu-models.*"))) == 2
        for m in (base / "models").glob("*.rknn"):
            m.unlink()
        p = subprocess.run(["sh", str(HERE / "run.sh")], env=env, capture_output=True, text=True)
        assert p.returncode != 0 and "no models selected" in p.stdout
        print("PASS runner: model/run isolation, stale outputs, diff/missing/empty/API failures, empty selection")

        (base / "stub.c").write_text(STUB)
        harness = base / "native-harness"
        subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                        "-I" + str(SDK_INCLUDE), str(HERE / "board_harness.c"),
                        str(base / "stub.c"), "-o", str(harness)], check=True)
        model = base / "model.rknn"
        model.write_bytes(b"x")
        output = base / "output"
        output.mkdir()
        def run(fault="", dest=output, extra=()):
            return subprocess.run([str(harness), str(model), str(dest), *extra],
                                  env=dict(os.environ, HARNESS_FAULT=fault), capture_output=True)
        assert run().returncode == 0
        assert (output / "out0.bin").read_bytes() == bytes((1, 2, 3, 4))
        assert (output / "out1.bin").read_bytes() == bytes((1, 2, 3, 4))
        for f in ("init", "query", "attr", "inputs", "run", "get", "release", "destroy",
                  "multiinput", "nooutputs", "manyoutputs", "null", "zero"):
            p = run(f)
            assert p.returncode != 0, (f, p.stderr)
        assert run("mask", extra=("1",)).returncode != 0
        assert run(dest=base / "absent").returncode != 0
        (output / "out0.bin").unlink()
        (output / "out0.bin").symlink_to("/dev/full")
        assert run().returncode != 0
        print("PASS harness: two indexed outputs, API errors, invalid output, file open/write failure")

def test_board_runner():
    from unittest import SkipTest
    if not (SDK_INCLUDE / 'rknn_api.h').is_file():
        raise SkipTest('set RKNN_SDK_INCLUDE to the external SDK header directory')
    main()


if __name__ == "__main__":
    main()
