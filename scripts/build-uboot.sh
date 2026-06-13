#!/usr/bin/env bash
# build-uboot.sh — STUB (Week 3-4). Planned flow:
#   source env-setup.sh
#   cd third_party/uboot && ../../scripts/apply-series.sh --component uboot
#   # pack with rkbin TPL/SPL via binman -> idbloader.img + u-boot.itb
#   # verify: U-Boot banner on UART
# Why stub: U-Boot RK3506 SoC support is ALREADY upstream (Jonas Karlman v2 merged),
# so this mostly needs the board DT/defconfig + rkbin packaging, not a patch carry.
set -euo pipefail
echo "build-uboot.sh: STUB (planned Week 3-4). See PLAN.md and BLOBS.md." >&2
exit 1
