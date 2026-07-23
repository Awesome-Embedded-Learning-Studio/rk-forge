#!/usr/bin/env bash
# build-linux.sh — configure + build the mainline Linux kernel + rk3506b-aes.dtb
# for the RK3506B board.
#
# Merges multi_v7_defconfig + board/rk3506-evb/{kernel.config,kernel-trim.config,
# kernel-compress.config}, then builds zImage + the board DT. The trim + XZ fragments
# shrink the kernel so boot.img fits before the factory-bad erase block at
# boot-relative 0x920000 (9.125 MiB). Keep them; do NOT swap in a hand-rolled trim
# that cuts CONFIG_NET — that data-aborts the decompressor (head.S __setup_mmu).
# Cross toolchain from env-setup.sh (Arm GNU gcc 15.2, arm-none-linux-gnueabihf, /opt).
# DT patches must already be applied to the tree — run
# `scripts/apply-series.sh --component linux` once on a clean checkout
# (or pass --apply-patches).
#
# Usage:
#   scripts/build-linux.sh [--apply-patches] [--tree <dir>] [--just-dtb]
#     --apply-patches  run apply-series.sh first (clean-tree setup)
#     --tree <dir>     linux worktree (default: third_party/src/linux)
#     --just-dtb       build only rockchip/rk3506b-aes.dtb (fast DT sanity check)
#
# Seam: bash-first. A future Python CLI may drive this; keep the merge/build
# steps as discrete, re-runnable units.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + LINUX_DIR/BOARD_CFG (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/progress.sh"   # forge_progress_run (live build progress when TTY)

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
# Board's kernel fragments (list from the board env KERNEL_FRAGMENTS; aes carries
# trim+compress for NAND boot-size, other boards may carry just kernel.config).
# Space-separated filenames under ${BOARD_CFG}/, merged in order (later overrides).
_kernel_frag_list="${KERNEL_FRAGMENTS:-kernel.config}"
KERNEL_FRAGMENTS=()
for _f in $_kernel_frag_list; do KERNEL_FRAGMENTS+=("${BOARD_CFG}/${_f}"); done
unset _kernel_frag_list
for _f in "${KERNEL_FRAGMENTS[@]}"; do
  [[ -f "$_f" ]] || die "kernel config fragment not found: $_f (set KERNEL_FRAGMENTS in config/boards/\${FORGE_BOARD}.env)"
done

cd "$LINUX_DIR"

if [[ "$APPLY" == 1 ]]; then
  log_info "applying DT patches (apply-series.sh)…"
  "${_SCRIPT_DIR}/apply-series.sh" --component linux
fi

log_info "merge_config: ${KERNEL_BASE_DEFCONFIG} + ${KERNEL_FRAGMENTS} …"
scripts/kconfig/merge_config.sh -m -O . \
  "${KERNEL_BASE_DEFCONFIG}" "${KERNEL_FRAGMENTS[@]}"

log_info "olddefconfig …"
make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" olddefconfig

if [[ "$JUST_DTB" == 1 ]]; then
  log_info "building ${DT_NAME}.dtb only …"
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" "rockchip/${DT_NAME}.dtb"
  log_ok "dtb → arch/${ARCH}/boot/dts/rockchip/${DT_NAME}.dtb"
else
  log_info "building ${KERN_IMG} + dtbs …"
  forge_progress_run kernel make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)" "${KERN_IMG}" dtbs
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" "rockchip/${DT_NAME}.dtb"
  log_ok "${KERN_IMG} → arch/${ARCH}/boot/${KERN_IMG} ; dtb → arch/${ARCH}/boot/dts/rockchip/${DT_NAME}.dtb"

  # rtl8733bu.ko (CONFIG_RTL8733BU=m, the WiFi module stage-rootfs ships into the
  # rootfs). zImage/dtbs don't build modules. 8733bu is an IN-TREE module (patch
  # 0016), so build it with the in-tree module.ko target (make path/to/8733bu.ko),
  # NOT `make M=` — M= is external-module style and hits a modfinal rule error on
  # this in-tree module. The module.ko modpost needs the top-level Module.symvers:
  # make zImage produces only vmlinux.symvers (vmlinux symbols), NOT Module.symvers
  # (that needs `make modules`, which we avoid — 656 modules). 8733bu references
  # only vmlinux symbols (core + CFG80211=y built-in), so seed Module.symvers from
  # vmlinux.symvers (standard trick for a vmlinux-only tree). Only build when
  # missing; incremental runs skip. ~3 min when it runs.
  # Board-gated: aes = RTL8733BU (WIFI_DRIVER="rtl8733bu"); rk3568-atk has
  # WIFI_DRIVER="" → skip the WiFi module entirely (it has no in-tree rtl8733bu).
  if [[ -n "${WIFI_DRIVER:-}" ]]; then
    if [[ ! -f drivers/net/wireless/realtek/rtl8733bu/8733bu.ko ]]; then
      [[ -f Module.symvers ]] || cp vmlinux.symvers Module.symvers
      log_info "building rtl8733bu.ko (in-tree module.ko target; missing — full-rebuild case)"
      forge_progress_run kernel make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" drivers/net/wireless/realtek/rtl8733bu/8733bu.ko
      log_ok "rtl8733bu.ko → drivers/net/wireless/realtek/rtl8733bu/8733bu.ko"
    else
      log_info "rtl8733bu.ko present (skip module build)"
    fi
  else
    log_info "no WIFI_DRIVER for this board (config/boards/\${FORGE_BOARD}.env) — skip WiFi module build"
  fi
fi
