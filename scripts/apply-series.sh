#!/usr/bin/env bash
# apply-series.sh — apply an ordered quilt-style patch series into a component
# worktree with `git am` (preserves authorship, real commits, bisectable).
#
# Fixes imx-forge's #1 debt: apply_patches.sh applied ONLY the last patch,
# silently SKIPPED on failure, and exited 0 — no series, no ordering, no atomicity,
# and the bug was copy-pasted into FOUR builder scripts.
#
# Usage (run from INSIDE the component worktree):
#   cd third_party/<component> && ../../scripts/apply-series.sh --component <name> [--check]
#
#   --component <linux|uboot>   which patches/<name>/series to apply
#   --check    dry-run: actually applies then reverts — verifies the WHOLE series
#              applies in order, touching nothing. (git apply --check on patch N
#              alone can't see patch N-1's effect, so we do a real apply+revert.)
#   --reverse  pop the series in reverse (W3; not in W1-2)
#
# Seam: exit 0 only on full success; non-zero after atomic rollback.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

COMPONENT=""; CHECK=0; REVERSE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2;;
    --check) CHECK=1; shift;;
    --reverse) REVERSE=1; shift;;
    -h|--help) sed -n '2,26p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ -n "$COMPONENT" ]] || die "missing --component <name>"

SERIES="${_PROJECT_ROOT}/patches/${COMPONENT}/series"
[[ -f "$SERIES" ]] || { log_warn "no series at ${SERIES} (nothing to apply)"; exit 0; }

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || die "not inside a git worktree; run: cd third_party/${COMPONENT}"

PRE_HEAD=$(git rev-parse HEAD)

PATCHES=()
while IFS= read -r line; do
  line="${line%%#*}"; line="${line//[[:space:]]/}"   # strip comments + whitespace
  [[ -z "$line" ]] && continue
  PATCHES+=("${_PROJECT_ROOT}/patches/${COMPONENT}/${line}")
done < "$SERIES"

[[ ${#PATCHES[@]} -gt 0 ]] || { log_warn "series is empty"; exit 0; }
[[ "$REVERSE" == "0" ]] || die "--reverse not implemented in W1-2 (planned W3). git reset --hard ${PRE_HEAD:0:8} manually for now."

rollback() { git reset --hard "$PRE_HEAD" >/dev/null 2>&1 || true; git clean -fdq >/dev/null 2>&1 || true; }

log_info "component=${COMPONENT} patches=${#PATCHES[@]} check=${CHECK} base=${PRE_HEAD:0:8}"

i=0
for p in "${PATCHES[@]}"; do
  i=$((i+1))
  if git am --3way --signoff "$p" >/dev/null 2>&1; then
    log_ok "[$i/${#PATCHES[@]}] $(basename "$p")"
  else
    git am --abort >/dev/null 2>&1 || true
    rollback
    die "[$i/${#PATCHES[@]}] FAILED $(basename "$p") — rolled back to ${PRE_HEAD:0:8}. Edit the patch or reorder patches/${COMPONENT}/series."
  fi
done

if [[ "$CHECK" == "1" ]]; then
  rollback
  log_ok "dry-run OK: all ${#PATCHES[@]} patches apply in order (worktree untouched)"
else
  log_ok "applied ${#PATCHES[@]} patches: ${PRE_HEAD:0:8} -> $(git rev-parse --short HEAD)"
fi
