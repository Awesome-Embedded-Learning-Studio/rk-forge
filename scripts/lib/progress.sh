# lib/progress.sh — pipe a long `make` through buildmeter (third_party/buildmeter,
# the standalone progress-meter package — formerly scripts/forge/progress.py) when
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

# Self-locate so this lib doesn't depend on the caller having set _SCRIPT_DIR
# (matches lib/toolchain.sh's BASH_SOURCE pattern; safe under `set -u`).
_PROGRESS_LIB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
# Points at buildmeter's script-style CLI entry (third_party/buildmeter
# submodule). cli.py self-fixes sys.path so `python3 "$FORGE_PROGRESS_PY"` works
# without PYTHONPATH. Same flag contract as the old progress.py (kind / --total /
# --count-only / --log / --ignore-errors), so callers (build-uboot.sh's custom
# block) need no business-logic change.
FORGE_PROGRESS_PY="${_PROGRESS_LIB_DIR}/../../third_party/buildmeter/src/buildmeter/cli.py"

forge_progress_run() {
  local kind="$1"; shift
  local progress_py="$FORGE_PROGRESS_PY"

  # Non-interactive or disabled → plain make, preserve exit.
  if [[ "${FORGE_PROGRESS:-1}" != "1" ]] || [[ ! -t 1 ]] \
     || [[ ! -f "$progress_py" ]] || ! command -v python3 >/dev/null 2>&1; then
    "$@"
    return $?
  fi

  # stdbuf -oL makes `make` line-buffer its stdout. make block-buffers when
  # stdout is a pipe (which it is here), and would starve the bar until EOF —
  # the bar would only appear at the very end. Fall back to plain if stdbuf
  # isn't available (coreutils; virtually always present on Linux).
  local buf=""
  if command -v stdbuf >/dev/null 2>&1; then buf="stdbuf -oL"; fi

  # Pre-scan: dry-run for the denominator. Emit a status line first so the
  # silent dry-run (can take tens of seconds on a big tree) doesn't look like a hang.
  # `{ make -k -n || true; }` — two dry-run hazards swallowed:
  #  - `-k` (keep-going): the dry-run aborts early on errors that only happen in
  #    -n (e.g. kernel tools/objtool sub-make fails because libsubcmd isn't built
  #    in a dry-run), truncating the CC enumeration → undercount → bar overflows
  #    past 100%. -k makes make enumerate the rest despite the error.
  #  - `|| true`: that same sub-make error makes `make -n` exit non-zero; swallow
  #    it so the caller's `set -o pipefail` doesn't fail the pipe + zero the total.
  local total=0
  if [[ "${FORGE_PROGRESS_PRESCAN:-1}" == "1" ]]; then
    printf '[INFO] counting build units (make -n)…\n' >&2
    # NOTE: buildmeter --count-only stderr is NOT silenced here — on a TTY it
    # renders the pre-scan spinner (`⠙ scanning dry-run (make -n)…`), giving the
    # 15-30s dry-run a heartbeat. It only writes stderr on a TTY, so CI / pipe
    # / non-interactive is unaffected. The make-side 2>/dev/null above still
    # swallows make -n's own noise.
    total=$({ "$@" -k -n 2>/dev/null || true; } \
      | python3 "$progress_py" --count-only "$kind") || total=0
    if [[ "$total" -le 0 ]]; then
      printf '[INFO] pre-scan returned 0 — running indeterminate (no %% bar)\n' >&2
    fi
  fi

  # Tee the full make output to a per-build log under /tmp (preserved for
  # reference / debugging), pipe through progress.py for the live bar.
  local logf="/tmp/forge-${kind}-${BASHPID:-$$}.log"
  printf '[INFO] full build log → %s\n' >&2 "$logf"
  if [[ "$total" -gt 0 ]] 2>/dev/null; then
    $buf "$@" 2>&1 | tee "$logf" | python3 "$progress_py" "$kind" --total "$total" --log "$logf"
  else
    $buf "$@" 2>&1 | tee "$logf" | python3 "$progress_py" "$kind" --log "$logf"
  fi
  return "${PIPESTATUS[0]}"
}
