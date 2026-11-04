#!/bin/sh
# 逐核心核验: 独立会话、IRQ、提交/完成计数、输出内容,不按 probe 成功判通过。
set -u
BASE=/opt/rknn-verify
cd "$BASE/multicore" || exit 1
mkdir -p "$BASE/results" || exit 1
evidence=$(mktemp -d "$BASE/results/media-multicore.XXXXXX") || exit 1
frames=${FRAMES:-16}
failed=0
uname -a > "$evidence/kernel.txt"
cat "$evidence/kernel.txt"

expected_kernel=$(cat "$BASE/multicore/expected-kernel") || exit 1
if [ "$(uname -r)" != "$expected_kernel" ]; then
    echo "FAIL: load new Image + DTB; expected $expected_kernel"
    echo 1 > "$evidence/device-status"
    echo "Evidence: $evidence"
    exit 1
fi
sh "$BASE/verify_boot_cleanup.sh" > "$evidence/boot-check.log" 2>&1
[ "$?" -eq 0 ] || failed=1
cat "$evidence/boot-check.log"

video_for()
{
    for v in /sys/class/video4linux/video*; do
        [ -e "$v" ] || continue
        parent=$(readlink -f "$v/device")
        case "$parent" in
            */"$1") echo "/dev/${v##*/}"; return 0 ;;
        esac
    done
    return 1
}

snapshot()
{
    output="$1"
    shift
    cat /proc/interrupts > "$output.interrupts"
    : > "$output"
    for device in "$@"; do
        p="/sys/bus/platform/devices/$device"
        if [ ! -L "$p/driver" ]; then
            echo "FAIL: $device unbound"
            return 1
        fi
        users=$(cat "$p/m2m_core_users") || return 1
        submitted=$(cat "$p/m2m_core_submitted") || return 1
        completed=$(cat "$p/m2m_core_completed") || return 1
        errors=$(cat "$p/m2m_core_errors") || return 1
        irqs=$(awk -v device="$device" '
            index($0, device) {
                for (i=2; i<=NF && $i ~ /^[0-9]+$/; i++) total += $i
            }
            END { print total+0 }
        ' "$output.interrupts")
        echo "$device $users $submitted $completed $errors $irqs" >> "$output"
    done
}

run_family()
{
    mode="$1"
    master="$2"
    workers="$3"
    shift 3
    node=$(video_for "$master") || {
        echo "FAIL: no frontend for $master"
        failed=1
        return
    }
    mkdir -p "$evidence/scalar-$mode" || { failed=1; return; }
    echo "==== scalar baseline $mode $node ===="
    if ! snapshot "$evidence/$mode-scalar.before" "$@"; then
        failed=1
        return
    fi
    ./media_demo "$mode" "$node" 1 2 "$evidence/scalar-$mode" \
        > "$evidence/$mode-scalar.log" 2>&1
    ret=$?
    cat "$evidence/$mode-scalar.log"
    if ! snapshot "$evidence/$mode-scalar.after" "$@"; then
        failed=1
        return
    fi
    if [ "$ret" -ne 0 ]; then
        echo "FAIL: $mode scalar baseline; skip its concurrent test"
        failed=1
        return
    fi
    echo "==== $mode $node: workers=$workers frames/worker=$frames ===="
    if ! snapshot "$evidence/$mode.before" "$@"; then
        failed=1
        return
    fi
    ./media_demo "$mode" "$node" "$workers" "$frames" "$evidence" \
        > "$evidence/$mode.log" 2>&1
    ret=$?
    cat "$evidence/$mode.log"
    [ "$ret" -eq 0 ] || failed=1
    if ! snapshot "$evidence/$mode.after" "$@"; then
        failed=1
        return
    fi
    awk -v frames="$frames" -v workers="$workers" '
        NR==FNR { users[$1]=$2; subm[$1]=$3; done[$1]=$4; errors[$1]=$5; irqs[$1]=$6; next }
        {
            n++
            ds=$3-subm[$1]; dc=$4-done[$1]; de=$5-errors[$1]; di=$6-irqs[$1]
            printf "%s submitted=+%d completed=+%d errors=+%d IRQ=+%d users=%d\n", $1, ds, dc, de, di, $2
            if (!($1 in subm) || ds!=frames || dc!=frames || de!=0 || di<=0 || $2!=users[$1]) bad=1
        }
        END { exit (bad || n!=workers) }
    ' "$evidence/$mode.before" "$evidence/$mode.after"
    [ "$?" -eq 0 ] || failed=1
}

run_family rga fdb60000.rga 2 fdb60000.rga fdb70000.rga
run_family jpeg fdba0000.video-codec 4 fdba0000.video-codec fdba4000.video-codec fdba8000.video-codec fdbac000.video-codec
run_family h264 fdc38000.video-codec 2 fdc38000.video-codec fdc40000.video-codec

sh "$BASE/verify_legacy_sync.sh" > "$evidence/npu-regression.log" 2>&1
[ "$?" -eq 0 ] || failed=1
cat "$evidence/npu-regression.log"
dmesg > "$evidence/dmesg.log" 2>&1
if grep -E 'missing multi-core support|rockchip-pm-domain.*sync_state\(\)|rknpu:.*EBUSY|[Ff]rame processing timed out|BUG:|Oops:' "$evidence/dmesg.log"; then
    echo "FAIL: driver/PM/timeout diagnostics remain"
    failed=1
fi
echo "$failed" > "$evidence/device-status"
echo "$frames" > "$evidence/frames"
echo "Evidence: $evidence"
if [ "$failed" -eq 0 ]; then
    echo "DEVICE PASS: all eight media cores completed checked work; NPU regressions passed"
    echo "JPEG pixel validation remains for the host verifier (saved jpeg-worker0..3.jpg)"
else
    echo "FAIL: retain evidence for host analysis"
fi
exit "$failed"
