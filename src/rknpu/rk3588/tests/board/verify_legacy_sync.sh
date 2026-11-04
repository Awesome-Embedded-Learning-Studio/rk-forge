#!/bin/sh
# 保留原始输出；MobileNet 随机权重会下溢,另用 ResNet18 验证非零写回。
set -u
cd /opt/rknn-verify || exit 1
if [ "${RKNN_TRACE:-0}" = 1 ] && [ ! -r "$PWD/bin/legacy_trace.so" ]; then
    echo "FAIL: missing bin/legacy_trace.so"
    exit 1
fi
mkdir -p results || exit 1
evidence=$(mktemp -d "$PWD/results/legacy-sync-0038.XXXXXX") || exit 1
uname -a > "$evidence/kernel.txt"
cat /proc/interrupts > "$evidence/interrupts.before"
failed=0

run_model()
{
    model="$1"
    minimum="$2"
    name=$(basename "$model" .rknn)
    testdir="$evidence/$name"
    mkdir -p "$testdir" || return 1
    echo "==== TEST $name (nonzero >= $minimum/1000) ===="
    ./run.sh "$model" > "$testdir/run.log" 2>&1
    [ "$?" -eq 0 ] || failed=1
    cat "$testdir/run.log"

    for impl in own vendor; do
        mkdir -p "$testdir/$impl" || return 1
        if [ "${RKNN_TRACE:-0}" = 1 ]; then
            preload="$PWD/bin/legacy_trace.so"
        else
            preload="${LD_PRELOAD:-}"
        fi
        RKNN_TRACE_DIR="$testdir/$impl" LD_PRELOAD="$preload" \
            LD_LIBRARY_PATH="$PWD/$impl" ./bin/board_harness \
            "$model" "$testdir/$impl" > "$testdir/$impl/$name.log" 2>&1
        ret=$?
        echo "$impl harness exit=$ret"
        [ "$ret" -eq 0 ] || failed=1
        output="$testdir/$impl/out0.bin"
        if [ ! -f "$output" ] || [ "$(wc -c < "$output")" -ne 2000 ]; then
            echo "FAIL $impl: expected 2000-byte out0.bin"
            failed=1
            continue
        fi
        # RK3588 小端 binary16: ±0=0/32768,指数全一为 Inf/NaN。
        LC_ALL=C od -An -v -tu2 "$output" | awk -v impl="$impl" -v minimum="$minimum" '
            { for (i = 1; i <= NF; i++) {
                total++
                if ($i != 0 && $i != 32768) nonzero++
                if (int($i / 1024) % 32 == 31) invalid++
            } }
            END {
                printf "%s: nonzero=%d/%d, finite=%s\n", impl, nonzero, total,
                       invalid ? "false" : "true"
                exit !(total == 1000 && nonzero >= minimum && invalid == 0)
            }'
        [ "$?" -eq 0 ] || failed=1
    done
    if cmp -s "$testdir/own/out0.bin" "$testdir/vendor/out0.bin"; then
        echo "byte_exact=true"
    else
        echo "byte_exact=false"
        failed=1
    fi
}

case "${1:-all}" in
    all)
        run_model models/mobilenetv2_fp.rknn 0 || failed=1
        run_model models/resnet18.rknn 901 || failed=1
        ;;
    models/mobilenetv2_fp.rknn|mobilenetv2_fp)
        run_model models/mobilenetv2_fp.rknn 0 || failed=1 ;;
    models/resnet18.rknn|resnet18)
        run_model models/resnet18.rknn 901 || failed=1 ;;
    *) echo "usage: sh verify_legacy_sync.sh [all|mobilenetv2_fp|resnet18]"; exit 2 ;;
esac
cat /proc/interrupts > "$evidence/interrupts.after"
dmesg > "$evidence/dmesg.log" 2>&1
echo "Evidence: $evidence"
cat "$evidence/kernel.txt"
if [ "$failed" -eq 0 ]; then
    echo "PASS: selected model run.sh + fresh finite/nonzero/byte-exact checks"
else
    echo "FAIL: see each model's own/vendor logs and dmesg.log in evidence directory"
fi
exit "$failed"
