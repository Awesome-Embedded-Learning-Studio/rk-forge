#!/usr/bin/env bash
# stage.sh — content-hash incremental stage skipping.
# This is rk-forge's answer to RK-SDK build.sh rebuilding everything every time.
# A stage reruns only when its INPUTS (sources + config + patches + DT) change,
# not merely when an output artifact is absent.
#
# Seam: predicate functions return 0 = up-to-date (skip), 1 = rebuild. Caller decides.
[[ -n "${STAGE_LIB_LOADED:-}" ]] && return 0   # already sourced
STAGE_LIB_LOADED=1

# stage_fingerprint <stage-name> <input...>  -> sha1 to stdout
stage_fingerprint() {
  local stage="$1"; shift
  {
    printf 'stage=%s arch=%s cross=%s\n' "$stage" "${ARCH:-?}" "${CROSS_COMPILE:-?}"
    local p
    for p in "$@"; do
      if [[ -d "$p" ]]; then
        # hash the file SET + sizes + mtimes of build-relevant files under the dir
        find "$p" -type f \( -name '*.c' -o -name '*.h' -o -name '*.S' \
          -o -name '*.dts' -o -name '*.dtsi' -o -name '*.config' -o -name 'defconfig' \
          -o -name 'series' -o -name '*.patch' -o -name 'Kconfig*' -o -name 'Makefile*' \) \
          -printf '%P %s %T@\n' 2>/dev/null | sort
      elif [[ -f "$p" ]]; then
        printf '%s %s %s\n' "$p" "$(stat -c%s "$p" 2>/dev/null)" "$(stat -c%Y "$p" 2>/dev/null)"
      fi
    done
  } | sha1sum | awk '{print $1}'
}

# stage_up_to_date <stage> <state-dir> <input...>  -> 0 if current, 1 if stale/missing
stage_up_to_date() {
  local stage="$1" state_dir="$2"; shift 2
  local fp_file="${state_dir}/${stage}.fingerprint" cur
  [[ -f "$fp_file" ]] || return 1
  cur=$(stage_fingerprint "$stage" "$@") || return 1
  [[ "$(cat "$fp_file")" == "$cur" ]]
}

# stage_mark_done <stage> <state-dir> <input...>
stage_mark_done() {
  local stage="$1" state_dir="$2"; shift 2
  mkdir -p "$state_dir"
  stage_fingerprint "$stage" "$@" > "${state_dir}/${stage}.fingerprint"
}
