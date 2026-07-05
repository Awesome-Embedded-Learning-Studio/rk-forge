# lib/progress.sh — pipe a long `make` through scripts/forge/progress.py when
# interactive, so a 72-minute build shows a live progress bar instead of an
# endless scroll of CC/LD lines.
#
# Falls through to plain `make` (no pipe) when ANY of these holds:
#   - stdout isn't a TTY (CI, log redirect, forge stage capture) — plain output
#   - FORGE_PROGRESS=0 is set in the environment                — plain output
#   - progress.py or python3 is missing                         — plain output
#   - the `make -n` pre-scan fails                               — indeterminate bar
#
# Usage (from a build script that has _SCRIPT_DIR set):
#   source "${_SCRIPT_DIR}/lib/progress.sh"
#   forge_progress_run kernel    make ARCH=$ARCH CROSS_COMPILE=$CC -j$(nproc) zImage dtbs
#   forge_progress_run buildroot make BR2_TOOLCHAIN_EXTERNAL_PATH=$TC
#
# Pre-scan: runs `<make-cmd> -n` once first to count the build units (the
# denominator for % + ETA). On a clean build this enumerates every step; on an
# incremental build, only the steps about to run — either way it matches what
# the real build will do. Disable with FORGE_PROGRESS_PRESCAN=0 (then the bar
# runs indeterminate: count + rate + elapsed, no %).
#
# Exit code: returns the make command's exit (PIPESTATUS[0]), so `set -e` /
# `pipefail` in the caller still catch real build failures. The progress.py
# consumer is best-effort and never changes the build's success/failure.

forge_progress_run() {
  local kind="$1"; shift
  local progress_py="${_SCRIPT_DIR}/forge/progress.py"

  # Non-interactive or disabled → plain make, preserve exit.
  if [[ "${FORGE_PROGRESS:-1}" != "1" ]] || [[ ! -t 1 ]] \
     || [[ ! -f "$progress_py" ]] || ! command -v python3 >/dev/null 2>&1; then
    "$@"
    return $?
  fi

  # Pre-scan: dry-run to get the denominator (best-effort; on failure → 0 =
  # indeterminate). `-n` is appended to the make args; make accepts it anywhere.
  local total=0
  if [[ "${FORGE_PROGRESS_PRESCAN:-1}" == "1" ]]; then
    total=$("$@" -n 2>/dev/null | python3 "$progress_py" --count-only "$kind" 2>/dev/null) || total=0
  fi

  # Real build, piped through progress.py. stderr from make is merged into the
  # pipe (progress parses it; kbuild/buildroot emit CC/>>>  on stdout anyway).
  # progress.py renders to stderr, so the bar is visible while stdout stays clean.
  if [[ "$total" -gt 0 ]] 2>/dev/null; then
    "$@" 2>&1 | python3 "$progress_py" "$kind" --total "$total"
  else
    "$@" 2>&1 | python3 "$progress_py" "$kind"
  fi
  return "${PIPESTATUS[0]}"
}
