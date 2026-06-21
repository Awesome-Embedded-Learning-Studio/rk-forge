#!/usr/bin/env bash
# fetch-deps.sh — clone the upstream source trees at their pinned refs.
#
# Implements the fetched-clone + tracked-pin model: the src trees (linux/uboot/
# buildroot) are gitignored local clones (NOT submodules — patched trees with a
# submodule drift the superproject gitlink); pins/<name> locks the exact ref for
# reproducibility. This is the rk-native replacement for imx-forge's
# "git submodule update --init" model.
#
# After fetching, the trees still need their deltas applied:
#   linux  → scripts/apply-series.sh --component linux  (patches 0001-0016)
#          + scripts/fetch-rtl8733bu-driver.sh                    (WiFi driver drop)
#   uboot  → scripts/apply-series.sh --component uboot            (3 board patches)
#   buildroot → no patches (BR2_EXTERNAL at bringup/buildroot-external/)
#
# Usage:
#   scripts/fetch-deps.sh [linux|uboot|buildroot|all]   (default: all)
# Idempotent: trees already present are skipped (rm -rf to refetch @ the pin).
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # PROJECT_ROOT + LINUX_DIR/UBOOT_DIR/BUILDROOT
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

# target dir for each source tree
declare -A TARGET=(
  [linux]="$LINUX_DIR"
  [uboot]="$UBOOT_DIR"
  [buildroot]="$BUILDROOT"
)

fetch_one() {  # <name>
  local name="$1" pin_file url ref target
  pin_file="${PROJECT_ROOT}/pins/${name}"
  [[ -f "$pin_file" ]] || { log_warn "$name: no pin file ($pin_file) — skipping"; return 0; }
  # pin file format: <git-url> <ref>  (# = comment)
  read -r url ref < <(grep -vE '^[[:space:]]*#' "$pin_file" | grep -vE '^[[:space:]]*$' | head -1)
  [[ -n "$url" && -n "$ref" ]] || die "$name: pin malformed (want '<url> <ref>'): $pin_file"
  target="${TARGET[$name]}"
  if [[ -d "$target" ]]; then
    log_info "$name: already present ($target) — skipping (rm -rf it to refetch @ $ref)"
    return 0
  fi
  mkdir -p "$(dirname "$target")"
  # --branch works for tags/branches; for a bare SHA (not a named ref) it fails
  # and we fall back to a default-branch clone + checkout.
  if git clone --branch "$ref" "$url" "$target" 2>/dev/null; then
    :
  else
    log_info "$name: '$ref' is not a named ref — full clone + checkout"
    git clone "$url" "$target"
    git -C "$target" checkout "$ref"
  fi
  log_ok "$name @ $ref → $target"
}

WHAT="${1:-all}"
case "$WHAT" in
  linux|uboot|buildroot) fetch_one "$WHAT" ;;
  all) for n in linux uboot buildroot; do fetch_one "$n"; done ;;
  -h|--help) sed -n '2,24p' "$0"; exit 0;;
  *) die "unknown arg: $WHAT (want: linux|uboot|buildroot|all)";;
esac
log_info "next: apply-series.sh for linux/uboot + fetch-rtl8733bu-driver.sh for the WiFi driver"
