#!/usr/bin/env bash
# build-linux.sh — configure + build the mainline Linux kernel + rk3506b-aes.dtb
# for the RK3506B board.
#
# Merges boards/rk3506-evb/kernel.config onto multi_v7_defconfig (ARCH=arm), then
# builds zImage + the board DT. The cross toolchain comes from env-setup.sh
# (vendor gcc 10.3, arm-none-linux-gnueabihf). DT patches must already be applied
# to the tree — run `scripts/apply-series.sh --component linux_mainline` once on a
# clean checkout (or pass --apply-patches).
#
# Usage:
#   scripts/build-linux.sh [--apply-patches] [--tree <dir>] [--just-dtb]
#     --apply-patches  run apply-series.sh first (clean-tree setup)
#     --tree <dir>     linux worktree (default: third_party/explore/linux)
#     --just-dtb       build only rockchip/rk3506b-aes.dtb (fast DT sanity check)
#
# Seam: bash-first. A future Python CLI may drive this; keep the merge/build
# steps as discrete, re-runnable units.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"

LINUX_DIR="${_PROJECT_ROOT}/third_party/explore/linux"
APPLY=0; JUST_DTB=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-patches) APPLY=1; shift;;
    --tree) LINUX_DIR="$2"; shift 2;;
    --just-dtb) JUST_DTB=1; shift;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

check_toolchain || die "toolchain not on PATH. Run: source scripts/env-setup.sh && ./scripts/doctor.sh"
[[ -d "$LINUX_DIR" ]] || die "linux tree not found: $LINUX_DIR"
CFG="${_PROJECT_ROOT}/boards/rk3506-evb/kernel.config"
[[ -f "$CFG" ]] || die "kernel.config not found: $CFG"

cd "$LINUX_DIR"

if [[ "$APPLY" == 1 ]]; then
  log_info "applying DT patches (apply-series.sh)…"
  "${_SCRIPT_DIR}/apply-series.sh" --component linux_mainline
fi

log_info "merge_config: multi_v7_defconfig + kernel.config …"
scripts/kconfig/merge_config.sh -m -O . \
  arch/arm/configs/multi_v7_defconfig "$CFG"

log_info "olddefconfig …"
make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" olddefconfig

if [[ "$JUST_DTB" == 1 ]]; then
  log_info "building rk3506b-aes.dtb only …"
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" rockchip/rk3506b-aes.dtb
  log_ok "dtb → arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
else
  log_info "building zImage + dtbs …"
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)" zImage dtbs
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" rockchip/rk3506b-aes.dtb
  log_ok "zImage → arch/arm/boot/zImage ; dtb → arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
fi
