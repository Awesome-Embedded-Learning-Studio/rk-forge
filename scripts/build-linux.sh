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

  # WiFi module (CONFIG_<WIFI_DRIVER>=m). In-tree module.ko target (NOT make M= —
  # M= hits a modfinal rule error on these in-tree modules). Board-gated via
  # WIFI_DRIVER (config/boards/<board>.env): aes=rtl8733bu (USB), rk3568-atk=
  # rtl8852bs (SDIO, armbian fork). Module name = WIFI_DRIVER sans the "rtl"
  # prefix (rtl8733bu→8733bu, rtl8852bs→8852bs). The module.ko modpost needs
  # Module.symvers; make zImage only yields vmlinux.symvers (the driver references
  # only vmlinux symbols — CFG80211/MAC80211 are =y built-in), so seed it. Only
  # build when missing; incremental runs skip.
  if [[ -n "${WIFI_DRIVER:-}" ]]; then
    WIFI_MOD="${WIFI_DRIVER#rtl}"                                  # 8733bu / 8852bs
    WIFI_KO="drivers/net/wireless/realtek/${WIFI_DRIVER}/${WIFI_MOD}.ko"
    if [[ ! -f "$WIFI_KO" ]]; then
      [[ -f Module.symvers ]] || cp vmlinux.symvers Module.symvers
      log_info "building ${WIFI_MOD}.ko (in-tree module.ko target; missing — full-rebuild case)"
      forge_progress_run kernel make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" "$WIFI_KO"
      log_ok "${WIFI_MOD}.ko → ${WIFI_KO}"
    else
      log_info "${WIFI_MOD}.ko present (skip module build)"
    fi
  else
    log_info "no WIFI_DRIVER for this board (config/boards/\${FORGE_BOARD}.env) — skip WiFi module build"
  fi
fi
