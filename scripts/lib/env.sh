# scripts/lib/env.sh — load config/forge.env + the active board's config/boards/<board>.env,
# and export resolved ABSOLUTE paths + all board constants. Source this from build/pack
# scripts instead of re-deriving _PROJECT_ROOT and hardcoded paths. Idempotent.
#
# Board selection: FORGE_BOARD env var or `forge.sh --board=<id>` (forge.sh pre-scans
# --board and exports FORGE_BOARD before sourcing this). Default: aes.
#
# After sourcing, the script-facing vars are exported:
#   PROJECT_ROOT  BRINGUP  OUT_DIR  LINUX_DIR  UBOOT_DIR  BUILDROOT  BOARD_CFG  ASSETS
#   KERNEL_ARTIFACT_DIR  FORGE_RKBIN_DIR  FORGE_BOARD
#   + all board fields: BOARD SOC ARCH ABI CPU KERNEL_BASE DT_NAME KERN_IMG STORAGE
#     UBOOT_DEFCONFIG(_SD) LOADER_INI NAND_* RKBIN_* TOOLCHAIN_*
# ${BASH_SOURCE[0]:-$0}: bash sets BASH_SOURCE; under zsh (which lacks it when
# sourced) fall back to $0 (matches scripts/env-setup.sh — keeps sourceable from zsh).
_env_sh_dir=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
export PROJECT_ROOT=$(cd "${_env_sh_dir}/../.." && pwd)
export _PROJECT_ROOT="$PROJECT_ROOT"   # back-compat alias (existing scripts use _PROJECT_ROOT)

# 1) project-level paths + default board
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/config/forge.env"

# 2) active board config (board-specific constants). FORGE_BOARD from env or forge.sh
#    --board pre-scan; default aes for backward compatibility.
export FORGE_BOARD="${FORGE_BOARD:-aes}"
_board_env="${PROJECT_ROOT}/config/boards/${FORGE_BOARD}.env"
if [ ! -r "$_board_env" ]; then
  echo "env.sh: board config not found: $_board_env (FORGE_BOARD=${FORGE_BOARD})" >&2
  echo "  available boards: $(ls "${PROJECT_ROOT}/config/boards/"*.env 2>/dev/null | sed 's#.*/##;s/\.env$//' | tr '\n' ' ')" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$_board_env"

# 3) resolve project-relative paths → absolute exports (the names scripts already use)
export BRINGUP="${PROJECT_ROOT}/${BRINGUP_DIR}"
export OUT_DIR="${PROJECT_ROOT}/${BRINGUP_DIR}/out"              # board-scoped out/ (was relative → absolute)
export LINUX_DIR="${PROJECT_ROOT}/${LINUX_TREE}"
# kernel artifacts (zImage/Image + dtb) source for pack-fit.sh. Defaults to LINUX_DIR
# (buildroot profile builds the kernel there); the openwrt profile overrides this
# to OpenWrt's build dir (OpenWrt builds the kernel — see build-openwrt.sh).
export KERNEL_ARTIFACT_DIR="${KERNEL_ARTIFACT_DIR:-$LINUX_DIR}"
export UBOOT_DIR="${PROJECT_ROOT}/${UBOOT_TREE}"
export OPENWRT_DIR="${PROJECT_ROOT}/${OPENWRT_TREE}"
export BUILDROOT="${PROJECT_ROOT}/${BUILDROOT_DIR}"
export BOARD_CFG="${PROJECT_ROOT}/${BOARD_CFG_DIR}"
export ASSETS="${PROJECT_ROOT}/${ASSETS_DIR}"
export FORGE_RKBIN_DIR="${FORGE_RKBIN_DIR:-${PROJECT_ROOT}/${FORGE_RKBIN_DIR_DEFAULT}}"

# 4) board field pass-through (identity + kernel + u-boot + storage + rkbin + toolchain)
export BOARD SOC ARCH ABI CPU KERNEL_BASE DT_NAME KERN_IMG KERNEL_BASE_DEFCONFIG KERNEL_FRAGMENTS STORAGE
export UBOOT_DEFCONFIG UBOOT_DEFCONFIG_SD BUILDROOT_DEFCONFIG LOADER_INI LOADER_TRUST_INI WIFI_DRIVER
export PARAMETER_NAND PARAMETER_SD PARAMETER_EMMC PKGFILE_NAND PKGFILE_RESCUE PKGFILE_SD PKGFILE_EMMC
export NAND_MIN_IO NAND_PEB NAND_LEB NAND_MAX_LEB
export RKBIN_BLOB_SUBDIR RKBIN_DDR_PAT RKBIN_USBPLUG_PAT RKBIN_SPL_PAT RKBIN_TEE_PAT RKBIN_TEE_EXCLUDE RKBIN_BL31_PAT
export TOOLCHAIN_PREFIX TOOLCHAIN_BIN_DIR TOOLCHAIN_SYSROOT
unset _env_sh_dir _board_env
