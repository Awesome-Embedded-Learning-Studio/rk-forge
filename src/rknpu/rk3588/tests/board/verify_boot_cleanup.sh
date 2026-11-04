#!/bin/sh
# 检查驱动实际绑定与 PM 同步,不写 state_synced、不修改日志等级。
set -u
cd /opt/rknn-verify || exit 1
mkdir -p results || exit 1
evidence=$(mktemp -d "$PWD/results/boot-cleanup.XXXXXX") || exit 1
failed=0
expected_kernel=7.3.1-00027-g4fad778b0c5a
kernel=$(uname -r)
echo "Kernel: $kernel"
if [ "$kernel" != "$expected_kernel" ]; then
    echo "FAIL: expected $expected_kernel; load the new Image and DTB together"
    failed=1
fi
power=/sys/bus/platform/devices/fd8d8000.power-management:power-controller/state_synced
waited=0
while [ "$(cat "$power" 2>/dev/null)" != 1 ] && [ "$waited" -lt 25 ]; do
    sleep 1
    waited=$((waited + 1))
done
state=$(cat "$power" 2>/dev/null)
echo "PM-domain state_synced=${state:-missing}"
[ "$state" = 1 ] || failed=1

while read -r device expected_driver; do
    [ -n "$device" ] || continue
    link=$(readlink "/sys/bus/platform/devices/$device/driver" 2>/dev/null || true)
    driver=${link##*/}
    echo "$device -> ${driver:-UNBOUND}"
    if [ "$driver" != "$expected_driver" ]; then
        echo "FAIL: $device expected driver $expected_driver"
        failed=1
    fi
done <<'DEVICES'
fdab0000.rknpu RKNPU
fdab9000.iommu rk_iommu
fdb50000.video-codec hantro-vpu
fdb50800.iommu rk_iommu
fdb60000.rga rockchip-rga
fdb60f00.iommu rk_iommu
fdb80000.rga rockchip-rga
fdba0000.video-codec hantro-vpu
fdba0800.iommu rk_iommu
fdc38000.video-codec rkvdec
fdc38700.iommu rk_iommu
fdc70000.video-codec hantro-vpu
fdca0000.iommu vsi_iommu
fdb70000.rga rockchip-rga
fdb70f00.iommu rk_iommu
fdba4000.video-codec hantro-vpu
fdba4800.iommu rk_iommu
fdba8000.video-codec hantro-vpu
fdba8800.iommu rk_iommu
fdbac000.video-codec hantro-vpu
fdbac800.iommu rk_iommu
fdc40000.video-codec rkvdec
fdc40700.iommu rk_iommu
DEVICES

cat /proc/iomem > "$evidence/iomem.log"
if [ -r /sys/kernel/debug/devices_deferred ]; then
    cat /sys/kernel/debug/devices_deferred > "$evidence/devices_deferred.log"
fi
dmesg > "$evidence/dmesg.log" 2>&1
if grep -E 'rknpu:.*EBUSY|can.t request region.*fdab|rockchip-pm-domain.*sync_state\(\)|Timed out\. Forcing sync_state' "$evidence/dmesg.log"; then
    echo "FAIL: resource or supplier synchronization diagnostics remain"
    failed=1
fi
sh ./verify_legacy_sync.sh > "$evidence/inference.log" 2>&1
[ "$?" -eq 0 ] || failed=1
cat "$evidence/inference.log"
echo "Boot evidence: $evidence"
if [ "$failed" -eq 0 ]; then
    echo "PASS: resource/driver/PM synchronization checks and both inference regressions"
else
    echo "FAIL: inspect boot evidence and driver bindings above"
fi
exit "$failed"
