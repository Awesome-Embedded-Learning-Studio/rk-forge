#!/usr/bin/env bash
# fetch-rtl8852bs-driver.sh — materialize the RTL8852BS driver drop into the
# rk3568-atk kernel tree from the armbian community fork.
#
# armbian/wifi-rtl8852bs is the community fork of the Realtek vendor driver
# (v1.15.9.2-11, G6 phl framework, CONFIG_SDIO_HCI) — already adapted across
# 6.1 → 6.16 → 6.17 → 6.18 → 7.1 (cfg80211 wdev-ops via RTW_CFG80211_DEV_PARAM_*
# macros, osdep timer/napi/kthread_complete_and_exit fixes, hmac_sha256 rename).
# The fork IS the ready-to-build driver for mainline 7.1; this script only:
#   1. clone <pins/rtl8852bs> @ the pinned ref into the kernel tree, strip .git
#   2. clean any stale build artifacts
#   3. gitignore the drop via the kernel clone's .git/info/exclude (NOT a tracked
#      .gitignore edit) so `git status` stays clean.
#
# Remaining forge-local adaptation (NOT in the fork): arm_rk.mk drops the
# ARCH=arm + vendor arm-eabi-4.6 absolute toolchain path (poison for an aarch64
# in-tree build) and swaps platform_ARM_RK_sdio.o → platform_ops.o stub
# (mainline has no rockchip_wifi_power). That delta is a quilt patch
# (patches/rk3568-atk/linux/00xx-wifi-rtl8852bs-forge-adapt.patch).
#
# Idempotent: a .forge-fetched marker records the cloned commit SHA; re-run
# no-ops unless --force (run --force to refresh after the fork's main advances).
#
# Run BEFORE scripts/apply-series.sh so rtl8852bs/Kconfig exists when the wire
# patch sources it. See document/notes/42.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + LINUX_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

PIN_FILE="${_PROJECT_ROOT}/pins/rtl8852bs"
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --linux) LINUX_DIR="$2"; shift 2;;
    --force) FORCE=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -f "$PIN_FILE" ]] || die "missing pin file: $PIN_FILE"
# pin file format: <git-url> <ref>  (lines starting with '#' are comments)
read -r REPO PIN_REF < <(grep -vE '^[[:space:]]*#' "$PIN_FILE" | grep -vE '^[[:space:]]*$' | head -1)
[[ -n "$REPO" && -n "$PIN_REF" ]] \
  || die "pin file malformed (want '<git-url> <ref>'): $PIN_FILE"
[[ -d "$LINUX_DIR" ]] || die "linux tree not found: $LINUX_DIR (clone it first)"

DROP="${LINUX_DIR}/drivers/net/wireless/realtek/rtl8852bs"
MARKER="$DROP/.forge-fetched"
mkdir -p "$(dirname "$DROP")"

if [[ -f "$MARKER" && "$FORCE" == 0 ]]; then
  log_ok "rtl8852bs/ already fetched @ $(cat "$MARKER") — --force to refresh from $PIN_REF"
  exit 0
fi

# 1. clone the fork @ pin (shallow; the drop is just working source)
log_info "cloning $REPO @ $PIN_REF → $DROP"
rm -rf "$DROP"
git clone -q --branch "$PIN_REF" --depth 1 "$REPO" "$DROP"
SHA=$(git -C "$DROP" rev-parse HEAD)

# Apply the forge-local adaptation (Makefile: RK=y; arm_rk.mk: drop the ARCH=arm
# + vendor arm-eabi-4.6 toolchain poison, swap platform_ARM_RK_sdio.o →
# platform_ops.o stub) BEFORE stripping .git — the drop is gitignored, so this
# can't go through apply-series/git am like a tracked-tree patch. If the fork's
# main advances and the patch no longer applies, refresh it. See notes/42.
ADAPT_PATCH="${_PROJECT_ROOT}/patches/rk3568-atk/linux/0002-wifi-rtl8852bs-forge-adapt.patch"
[[ -f "$ADAPT_PATCH" ]] \
  || die "forge-adapt patch missing: $ADAPT_PATCH"
git -C "$DROP" apply --whitespace=nowarn "$ADAPT_PATCH" \
  || die "forge-adapt patch failed to apply — the fork's main may have advanced; refresh $ADAPT_PATCH"
log_ok "forge-adapt applied (Makefile RK=y + arm_rk.mk aarch64/platform_ops stub)"

rm -rf "$DROP/.git"
echo "$SHA" > "$MARKER"

# 2. clean stale build artifacts (defensive; the fork ships none)
find "$DROP" \( -name '*.o' -o -name '*.o.cmd' -o -name '*.ko' -o -name '*.ko.cmd' \
  -o -name '*.mod' -o -name '*.mod.c' -o -name '*.mod.o' -o -name '.*.cmd' \
  -o -name 'Module.symvers' -o -name 'modules.order' -o -name '.module-common.o' \
  -o -name '.tmp_*' \) -delete 2>/dev/null || true

# 3. ignore the drop WITHOUT editing a tracked .gitignore. --absolute-git-dir
# makes this work in both a plain clone (.git is a dir) and a git worktree.
EXCLUDE="$(git -C "$LINUX_DIR" rev-parse --absolute-git-dir)/info/exclude"
touch "$EXCLUDE"
grep -qxF 'drivers/net/wireless/realtek/rtl8852bs/' "$EXCLUDE" \
  || printf '\n# forge: fetched vendor driver drop (scripts/fetch-rtl8852bs-driver.sh)\ndrivers/net/wireless/realtek/rtl8852bs/\n' >> "$EXCLUDE"

log_ok "RTL8852BS driver materialized @ $SHA (from $REPO $PIN_REF)"
log_info "next: scripts/apply-series.sh --component linux (wire + forge-adapt patches), then build 8852bs.ko"
