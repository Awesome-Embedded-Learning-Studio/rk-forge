#!/usr/bin/env bash
# toolchain.sh — sources config/toolchain.conf, exports PATH/ARCH/CROSS_COMPILE,
# and verifies the compiler is reachable. Sourced by env-setup.sh and every
# build script. Exits 1 (via die) only when invoked by a build, not when sourced.
[[ -n "${TOOLCHAIN_LIB_LOADED:-}" ]] && return 0   # already sourced
TOOLCHAIN_LIB_LOADED=1

_TC_LIB_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
PROJECT_ROOT=$(cd "${_TC_LIB_DIR}/../.." && pwd)
export PROJECT_ROOT

# toolchain.conf is the project DEFAULT (armhf, for aes). The ACTIVE BOARD's config
# (config/boards/<board>.env, sourced by lib/env.sh BEFORE this) sets TOOLCHAIN_* for
# the board (aarch64 for rk3568-atk). Preserve the board's values across the
# toolchain.conf source so the board wins (env.sh exported them already).
_bt_prefix="${TOOLCHAIN_PREFIX:-}"; _bt_bindir="${TOOLCHAIN_BIN_DIR:-}"
_bt_sysroot="${TOOLCHAIN_SYSROOT:-}"; _bt_arch="${ARCH:-}"
# shellcheck disable=SC1091
source "${PROJECT_ROOT}/config/toolchain.conf"
[[ -n "$_bt_prefix" ]]  && TOOLCHAIN_PREFIX="$_bt_prefix"
[[ -n "$_bt_bindir" ]]  && TOOLCHAIN_BIN_DIR="$_bt_bindir"
[[ -n "$_bt_sysroot" ]] && TOOLCHAIN_SYSROOT="$_bt_sysroot"
[[ -n "$_bt_arch" ]]    && ARCH="$_bt_arch"
unset _bt_prefix _bt_bindir _bt_sysroot _bt_arch

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
