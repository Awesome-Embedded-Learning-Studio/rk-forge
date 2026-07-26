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
#   openwrt → kernel patches are quilt patches-7.1/ (applied by OpenWrt at build
#          time, NOT git-am'd here); a small rk-forge overlay (Device/aes + config)
#          is applied via apply-series.sh --component openwrt
#
# Usage:
#   scripts/fetch-deps.sh [linux|uboot|buildroot|openwrt|all]   (default: all)
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
  [openwrt]="$OPENWRT_DIR"
)

# retry a git clone across transient network failures (huge repos over flaky
# networks: observed the linux-stable full clone die mid-transfer with
# `curl 56 GnuTLS recv error` / `fetch-pack: unexpected disconnect`). Retries
# with linear backoff; returns the clone's exit code on final failure.
git_clone_retry() {  # <clone-args...>
  local tries=3 i=1
  while (( i <= tries )); do
    if git clone "$@" 2>/dev/null; then return 0; fi
    (( i < tries )) && log_warn "git clone failed (attempt $i/$tries); retrying in $(( i * 3 ))s…"
    (( i < tries )) && sleep $(( i * 3 ))
    (( i++ ))
  done
  return 1
}

fetch_one() {  # <name>
  local name="$1" pin_file url ref target
  # Board-specific pin (pins/<board>/<name>) overrides the shared pin (pins/<name>).
  pin_file="${PROJECT_ROOT}/pins/${FORGE_BOARD}/${name}"
  [[ -f "$pin_file" ]] || pin_file="${PROJECT_ROOT}/pins/${name}"
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
  # --branch works for tags/branches → clone shallow (--depth 1): a full clone
  # of linux-stable is multi-GB and routinely dies on flaky networks, and we
  # don't need history (only the pinned ref the patch series applies onto).
  # For a bare SHA (not a named ref) --branch fails → fall back to a full clone
  # + checkout (also retried). Either path: no history is fine — apply-series
  # `git am`s patches onto the resolved HEAD, which is present in a shallow clone.
  if git_clone_retry --depth 1 --branch "$ref" "$url" "$target"; then
    :
  else
    log_info "$name: '$ref' not a named ref (or shallow clone failed) — full clone + checkout (retried)"
    git_clone_retry "$url" "$target" || die "$name: git clone failed after retries ($url)"
    git -C "$target" checkout "$ref" || die "$name: checkout $ref failed (pin wrong?)"
  fi
  log_ok "$name @ $ref → $target"
}

WHAT="${1:-all}"
case "$WHAT" in
  linux|uboot|buildroot|openwrt) fetch_one "$WHAT" ;;
  # `all` covers the buildroot-profile deps (linux+uboot+buildroot). openwrt is
  # NOT in `all` — it's a large optional tree fetched only for the openwrt
  # profile (stage_setup fetches it via `fetch-deps openwrt` when --rootfs=openwrt).
  all) for n in linux uboot buildroot; do fetch_one "$n"; done ;;
  -h|--help) sed -n '2,24p' "$0"; exit 0;;
  *) die "unknown arg: $WHAT (want: linux|uboot|buildroot|openwrt|all)";;
esac
log_info "next: apply-series.sh for linux/uboot (+openwrt if --rootfs=openwrt) + fetch-rtl8733bu-driver.sh"
