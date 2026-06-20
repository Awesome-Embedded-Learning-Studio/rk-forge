# scripts/lib/env.sh — load config/forge.env and export resolved ABSOLUTE paths.
# Source this from build/pack scripts instead of re-deriving _PROJECT_ROOT and
# hardcoded paths. Idempotent (safe to source multiple times).
#
# After sourcing, the script-facing vars are exported:
#   PROJECT_ROOT  BRINGUP  OUT_DIR  LINUX_DIR  UBOOT_DIR  BUILDROOT  BOARD_CFG
#   ASSETS  FORGE_RKBIN_DIR(default)  BOARD  SOC  KERNEL_BASE  NAND_*
# CLI flags (--out / --tree / --linux / --rkbin) parsed AFTER sourcing override
# these defaults.
# ${BASH_SOURCE[0]:-$0}: bash sets BASH_SOURCE; under zsh (which lacks it when
# sourced) fall back to $0. Matches scripts/env-setup.sh's idiom — keeps this
# sourceable from zsh without PROJECT_ROOT mis-resolving (was: bare
# ${BASH_SOURCE[0]} → empty under zsh → PROJECT_ROOT=/home → forge died).
_env_sh_dir=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
export PROJECT_ROOT=$(cd "${_env_sh_dir}/../.." && pwd)
export _PROJECT_ROOT="$PROJECT_ROOT"   # back-compat alias (existing scripts use _PROJECT_ROOT)

# load the single source of truth (project-relative defaults)
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/config/forge.env"

# resolve to absolute exports (the names scripts already use)
export BRINGUP="${PROJECT_ROOT}/${BRINGUP_DIR}"
export OUT_DIR="${PROJECT_ROOT}/${OUT_DIR}"                 # was relative → absolute
export LINUX_DIR="${PROJECT_ROOT}/${LINUX_TREE}"
export UBOOT_DIR="${PROJECT_ROOT}/${UBOOT_TREE}"
export BUILDROOT="${PROJECT_ROOT}/${BUILDROOT_DIR}"
export BOARD_CFG="${PROJECT_ROOT}/${BOARD_CFG_DIR}"
export ASSETS="${PROJECT_ROOT}/${ASSETS_DIR}"
export FORGE_RKBIN_DIR="${FORGE_RKBIN_DIR:-${PROJECT_ROOT}/${FORGE_RKBIN_DIR_DEFAULT}}"
# board + NAND geometry pass-through
export BOARD SOC KERNEL_BASE
export NAND_MIN_IO NAND_PEB NAND_LEB NAND_MAX_LEB
unset _env_sh_dir
