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
  log_info "make rk3506_aes_defconfig (regen .config from the forge defconfig)"
  make rk3506_aes_defconfig
fi

# Detect toolchain root from PATH (avoid hardcoding /opt/... in the defconfig).
# This lets the user change toolchain location without editing config files.
TC_GCC=$(command -v "arm-none-linux-gnueabihf-gcc" 2>/dev/null || true)
if [[ -z "$TC_GCC" ]]; then
  die "arm-none-linux-gnueabihf-gcc not found on PATH. Run: source scripts/env-setup.sh"
fi
BR2_TC_PATH=$(cd "$(dirname "$TC_GCC")/.." && pwd)
log_info "detected toolchain: $BR2_TC_PATH"

# WSL: buildroot dependencies.mk rejects PATH entries with spaces (/mnt/c/...).
# forge_clean_path strips them; run make under the cleaned PATH.
# BR2_TOOLCHAIN_EXTERNAL_PATH overrides the defconfig's hardcoded default.
log_info "make (PATH cleaned of /mnt + whitespace, BR2_TOOLCHAIN_EXTERNAL_PATH from env)"
PATH="$(forge_clean_path)" make BR2_TOOLCHAIN_EXTERNAL_PATH="$BR2_TC_PATH"

ROOTFS_TAR="$BUILDROOT/output/images/rootfs.tar"
[[ -f "$ROOTFS_TAR" ]] || die "buildroot produced no rootfs.tar"
log_ok "rootfs.tar → $ROOTFS_TAR ($(stat -c%s "$ROOTFS_TAR") B, sha256=$(sha256sum "$ROOTFS_TAR" | cut -c1-16))"
log_info "next: scripts/forge.sh pack (stage-rootfs picks it up)"
