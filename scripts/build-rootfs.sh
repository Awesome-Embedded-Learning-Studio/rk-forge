#!/usr/bin/env bash
# build-rootfs.sh — build the buildroot UBIFS rootfs (output/images/rootfs.tar).
#
# Wraps the canonical buildroot build (bringup/buildroot-external/README) with
# the WSL PATH fix (forge_clean_path from lib/host.sh) so it runs unattended.
# forge's board customization is the BR2_EXTERNAL tree at bringup/buildroot-external
# (rk3506_aes_defconfig + overlay + post-build hook). Output → stage-rootfs.sh.
#
# Reproducibility: buildroot is NOT byte-reproducible by default (package file
# timestamps) — unlike U-Boot, where SOURCE_DATE_EPOCH alone suffices. Achieving
# byte-reproducible rootfs.tar needs BR2_REPRODUCIBLE=y in the defconfig + each
# package to support it, then a double-build to verify. That is a deeper, more
# expensive effort than U-Boot's; until then the rootfs.tar is functionally
# reproducible (same inputs → same content) but not byte-identical across builds.
#
# Usage:
#   scripts/build-rootfs.sh [--reconfigure] [--clean]
#     --reconfigure  regen .config from rk3506_aes_defconfig before make
#     --clean        make clean first (full rebuild; slow)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + BUILDROOT + BRINGUP
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/host.sh"    # forge_warn_windows_path / forge_clean_path
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"  # TOOLCHAIN_BIN_DIR / CROSS_COMPILE (toolchain SoT)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/progress.sh"   # forge_progress_run (live build progress when TTY)

RECONFIGURE=0; CLEAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reconfigure) RECONFIGURE=1; shift;;
    --clean) CLEAN=1; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ -d "$BUILDROOT" ]] || die "buildroot tree not found: $BUILDROOT (run scripts/fetch-deps.sh buildroot)"

forge_warn_windows_path
export BR2_EXTERNAL="${BRINGUP}/buildroot-external"
log_info "BR2_EXTERNAL=$BR2_EXTERNAL"

cd "$BUILDROOT"
[[ "$CLEAN" == 1 ]] && { log_info "make clean"; make clean >/dev/null; }
if [[ "$RECONFIGURE" == 1 || ! -f .config ]]; then
  log_info "make ${BUILDROOT_DEFCONFIG} (regen .config from the forge defconfig)"
  make "$BUILDROOT_DEFCONFIG"
fi

# Toolchain path: the defconfig hardcodes /opt/... because buildroot's Kconfig
# state requires a concrete path. Override BR2_TOOLCHAIN_EXTERNAL_PATH at build
# time from the project's single source of truth (config/toolchain.conf ->
# TOOLCHAIN_BIN_DIR), so the toolchain location has ONE owner — the same knob
# U-Boot/kernel builds and the future Python CLI use — instead of re-searching
# PATH. NOTE: this relocates the *path* only; switching to a different gcc
# version still needs the BR2_TOOLCHAIN_EXTERNAL_GCC_*/HEADERS_* symbols updated.
BR2_TC_PATH=$(cd "${TOOLCHAIN_BIN_DIR}/.." && pwd)   # toolchain root (parent of bin/)
[[ -x "${BR2_TC_PATH}/bin/${CROSS_COMPILE}gcc" ]] \
  || die "toolchain root invalid: $BR2_TC_PATH (check config/toolchain.conf)"
log_info "toolchain (from toolchain.conf): $BR2_TC_PATH"

# WSL: buildroot dependencies.mk rejects PATH entries with spaces (/mnt/c/...).
# forge_clean_path strips them; run make under the cleaned PATH.
log_info "make (PATH cleaned of /mnt + whitespace, BR2_TOOLCHAIN_EXTERNAL_PATH from toolchain.conf)"
PATH="$(forge_clean_path)" forge_progress_run buildroot make BR2_TOOLCHAIN_EXTERNAL_PATH="$BR2_TC_PATH"

ROOTFS_TAR="$BUILDROOT/output/images/rootfs.tar"
[[ -f "$ROOTFS_TAR" ]] || die "buildroot produced no rootfs.tar"
log_ok "rootfs.tar → $ROOTFS_TAR ($(stat -c%s "$ROOTFS_TAR") B, sha256=$(sha256sum "$ROOTFS_TAR" | cut -c1-16))"
log_info "next: scripts/forge.sh pack (stage-rootfs picks it up)"
