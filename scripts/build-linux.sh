#!/usr/bin/env bash
# build-linux.sh — STUB (Week 5-6). Planned flow:
#   source env-setup.sh
#   cd third_party/linux_mainline && ../../scripts/apply-series.sh --component linux_mainline
#   # merge_config.sh boards/rk3506-evb/kernel.config + defconfig (ARCH=arm)
#   # build Image + rk3506-*.dtb; verify: kernel reaches earlycon
# Key insight: RK3506 pinctrl+clk are in mainline (since 6.19), so this is
# "add a board DT on top of merged SoC support", not "migrate from BSP".
# Target kernel: v7.0.x (6.19 is EOL).
set -euo pipefail
echo "build-linux.sh: STUB (planned Week 5-6). See PLAN.md." >&2
exit 1
