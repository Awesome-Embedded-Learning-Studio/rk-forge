#!/usr/bin/env bash
# toolchain.sh — sources config/toolchain.conf, exports PATH/ARCH/CROSS_COMPILE,
# and verifies the compiler is reachable. Sourced by env-setup.sh and every
# build script. Exits 1 (via die) only when invoked by a build, not when sourced.
[[ -n "${TOOLCHAIN_LIB_LOADED:-}" ]] && return 0   # already sourced
TOOLCHAIN_LIB_LOADED=1

_TC_LIB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
PROJECT_ROOT=$(cd "${_TC_LIB_DIR}/../.." && pwd)
export PROJECT_ROOT

# shellcheck disable=SC1091
source "${PROJECT_ROOT}/config/toolchain.conf"

export ARCH
export CROSS_COMPILE="${TOOLCHAIN_PREFIX}"
[[ -n "${TOOLCHAIN_BIN_DIR}" ]] && export PATH="${TOOLCHAIN_BIN_DIR}:${PATH}"

# Returns 0 if ${CROSS_COMPILE}gcc + readelf resolve on PATH. Prints nothing on
# success (caller logs); designed to be callable as a predicate.
check_toolchain() {
  local cc="${CROSS_COMPILE}gcc"
  command -v "$cc" >/dev/null 2>&1 || return 1
  "$cc" --version >/dev/null 2>&1 || return 1
  command -v "${CROSS_COMPILE}readelf" >/dev/null 2>&1 || return 1
}
