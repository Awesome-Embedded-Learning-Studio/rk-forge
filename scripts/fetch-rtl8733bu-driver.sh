#!/usr/bin/env bash
# fetch-rtl8733bu-driver.sh — materialize the RTL8733BU driver drop into the
# kernel tree from the forge-maintained fork.
#
# The driver (no mainline equivalent) lives in the forge fork at
# Awesome-Embedded-Learning-Studio/rtl8733bu-linux-driver (branch linux-7.1-port,
# GPL-2.0-only): Realtek → wirenboard v5.15.12-264_for6.18 → the 7.1 port (static
# Kbuild + USB&&CFG80211 Kconfig + cfg80211 wdev-ops wrappers). The fork IS the
# ready-to-build driver — the port is baked into it, so this script only:
#   1. clone <pins/rtl8733bu> @ the pinned ref into the kernel tree, strip .git
#   2. clean any stale build artifacts
#   3. gitignore the drop via the kernel clone's .git/info/exclude (NOT a tracked
#      .gitignore edit) so `git status` stays clean — the 2-line realtek
#      registration is a separate quilt patch (patches/linux_mainline/0016), the
#      only tracked delta.
#
# Idempotent: a .forge-fetched marker records the cloned commit SHA; re-run no-ops
# unless --force (run --force to refresh after the fork's linux-7.1-port advances).
#
# Run BEFORE scripts/apply-series.sh so rtl8733bu/Kconfig exists when patch 0016
# sources it. See document/notes/29 + document/pitfalls/07.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + LINUX_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

PIN_FILE="${_PROJECT_ROOT}/pins/rtl8733bu"
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --linux) LINUX_DIR="$2"; shift 2;;
    --force) FORCE=1; shift;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -f "$PIN_FILE" ]] || die "missing pin file: $PIN_FILE"
# pin file format: <git-url> <ref>  (lines starting with '#' are comments)
read -r REPO PIN_REF < <(grep -vE '^[[:space:]]*#' "$PIN_FILE" | grep -vE '^[[:space:]]*$' | head -1)
[[ -n "$REPO" && -n "$PIN_REF" ]] \
  || die "pin file malformed (want '<git-url> <ref>'): $PIN_FILE"
[[ -d "$LINUX_DIR" ]] || die "linux tree not found: $LINUX_DIR (clone it first)"

DROP="${LINUX_DIR}/drivers/net/wireless/realtek/rtl8733bu"
MARKER="$DROP/.forge-fetched"
mkdir -p "$(dirname "$DROP")"

if [[ -f "$MARKER" && "$FORCE" == 0 ]]; then
  log_ok "rtl8733bu/ already fetched @ $(cat "$MARKER") — --force to refresh from $PIN_REF"
  exit 0
fi

# 1. clone the fork @ pin (shallow; the drop is just working source)
log_info "cloning $REPO @ $PIN_REF → $DROP"
rm -rf "$DROP"
git clone -q --branch "$PIN_REF" --depth 1 "$REPO" "$DROP"
SHA=$(git -C "$DROP" rev-parse HEAD)
rm -rf "$DROP/.git"
echo "$SHA" > "$MARKER"

# 2. clean stale build artifacts (the fork ships none; defensive)
find "$DROP" \( -name '*.o' -o -name '*.o.cmd' -o -name '*.ko' -o -name '*.ko.cmd' \
  -o -name '*.mod' -o -name '*.mod.c' -o -name '*.mod.o' -o -name '.*.cmd' \
  -o -name 'Module.symvers' -o -name 'modules.order' -o -name '.module-common.o' \
  -o -name '.tmp_*' \) -delete 2>/dev/null || true

# 3. ignore the drop WITHOUT editing a tracked .gitignore. --absolute-git-dir
# makes this work in both a plain clone (.git is a dir) and a git worktree.
EXCLUDE="$(git -C "$LINUX_DIR" rev-parse --absolute-git-dir)/info/exclude"
touch "$EXCLUDE"
grep -qxF 'drivers/net/wireless/realtek/rtl8733bu/' "$EXCLUDE" \
  || printf '\n# forge: fetched vendor driver drop (scripts/fetch-rtl8733bu-driver.sh)\ndrivers/net/wireless/realtek/rtl8733bu/\n' >> "$EXCLUDE"

log_ok "RTL8733BU driver materialized @ $SHA (from $REPO $PIN_REF)"
log_info "next: scripts/apply-series.sh --component linux_mainline (patch 0016 wires it), then build + make modules"
