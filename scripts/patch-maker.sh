#!/usr/bin/env bash
# patch-maker.sh — generate per-commit numbered patches from a component's branch
# divergence and APPEND them to its series file.
#
# Fixes imx-forge's patch_maker.sh, which squashed N commits into ONE date-stamped
# blob via `git format-patch --stdout` (destroying order, breaking bisect, and —
# combined with the "apply only newest by filename" bug — silently dropping work).
#
# Usage (inside the component worktree):
#   cd third_party/<component> && ../../scripts/patch-maker.sh --component <name> --since <base-ref>
#     --since <base-ref>  upstream ref you diverged from (e.g. v7.0.12, or the gitlink commit)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

COMPONENT=""; SINCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2;;
    --since) SINCE="$2"; shift 2;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ -n "$COMPONENT" ]] || die "missing --component <name>"
[[ -n "$SINCE" ]] || die "missing --since <base-ref> (e.g. v7.0.12)"

OUT="${_PROJECT_ROOT}/patches/${COMPONENT}"
SERIES="${OUT}/series"
mkdir -p "$OUT"; touch "$SERIES"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git worktree"

mapfile -t FILES < <(git format-patch --signoff --output-directory "$OUT" "${SINCE}..HEAD" 2>/dev/null || true)
[[ ${#FILES[@]} -gt 0 ]] || { log_warn "no commits in ${SINCE}..HEAD"; exit 0; }

added=0
for f in "${FILES[@]}"; do
  b=$(basename "$f")
  if grep -qxF "$b" "$SERIES" 2>/dev/null; then continue; fi
  printf '%s\n' "$b" >> "$SERIES"
  added=$((added+1))
  log_debug "  + $b"
done
log_ok "wrote ${#FILES[@]} patches into patches/${COMPONENT}/ (${added} new series entries)"
