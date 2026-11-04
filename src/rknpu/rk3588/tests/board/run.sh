#!/bin/sh
# 每次运行、每个模型、每个实现独立目录，保留完整输出以便复核。
# 用法: run.sh [model.rknn]
set -u
BASE=${RKNN_VERIFY_BASE:-/opt/rknn-verify}
mkdir -p "$BASE/results" || exit 1
OUT=$(mktemp -d "$BASE/results/npu-models.XXXXXX") || exit 1
uname -a > "$OUT/kernel.txt"
cat /proc/interrupts > "$OUT/interrupts.before" 2>&1
echo "NPU model comparison (multimedia tests: $BASE/multicore/run.sh)"
echo "Evidence: $OUT"

fail=0
total=0

run_one()
{
    m="$1"
    name=$(basename "$m" .rknn)
    total=$((total + 1))
    echo "==== $name ===="
    own="$OUT/own/$name"
    vendor="$OUT/vendor/$name"
    mkdir -p "$own" "$vendor" || { fail=$((fail + 1)); return; }
    LD_LIBRARY_PATH="$BASE/own" "$BASE/bin/board_harness" "$m" "$own" \
        > "$own/harness.log" 2>&1
    ro=$?
    LD_LIBRARY_PATH="$BASE/vendor" "$BASE/bin/board_harness" "$m" "$vendor" \
        > "$vendor/harness.log" 2>&1
    rv=$?
    if [ "$ro" -ne 0 ] || [ "$rv" -ne 0 ]; then
        echo "RUN  FAIL  own=$ro vendor=$rv (logs: $own/harness.log, $vendor/harness.log)"
        fail=$((fail + 1))
        return
    fi
    bad=0
    count=0
    for o in "$own"/out*.bin; do
        [ -f "$o" ] || continue
        count=$((count + 1))
        on=$(basename "$o")
        if [ ! -s "$o" ] || ! cmp -s "$o" "$vendor/$on"; then
            echo "DIFF FAIL  $on"
            bad=1
        fi
    done
    for o in "$vendor"/out*.bin; do
        [ -f "$o" ] || continue
        on=$(basename "$o")
        [ -f "$own/$on" ] || { echo "MISS FAIL  own/$on"; bad=1; }
    done
    if [ "$count" -eq 0 ]; then
        echo "MISS FAIL  no own outputs"
        bad=1
    fi
    if [ "$bad" -eq 0 ]; then
        echo "PASS  ($count outputs byte-identical)"
    else
        echo "OUTPUT DIFF — evidence: $own + $vendor"
        fail=$((fail + 1))
    fi
}

if [ -n "${1:-}" ]; then
    run_one "$1"
else
    for m in "$BASE"/models/*.rknn; do
        [ -f "$m" ] || continue
        run_one "$m"
    done
fi

echo
cat /proc/interrupts > "$OUT/interrupts.after" 2>&1
dmesg > "$OUT/dmesg.log" 2>&1
echo "==== SUMMARY: $((total - fail))/$total PASS ===="
if [ "$total" -eq 0 ]; then
    echo "FAIL: no models selected"
    exit 1
fi
[ "$fail" -eq 0 ]
