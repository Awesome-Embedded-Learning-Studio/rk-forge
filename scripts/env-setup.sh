#!/usr/bin/env bash
# env-setup.sh — SOURCE this (do not execute) to export the cross toolchain env:
#   source scripts/env-setup.sh
# Seam: only exports; no checks, no output spam. doctor.sh does the checking.
# (Executing it directly won't persist exports — it must be sourced.)
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"

if check_toolchain; then
  log_ok "toolchain ready: ${CROSS_COMPILE}gcc"
else
  log_warn "toolchain ${CROSS_COMPILE}gcc NOT on PATH. Run: ./scripts/doctor.sh"
fi
log_info "ARCH=${ARCH}  CROSS_COMPILE=${CROSS_COMPILE}  PROJECT_ROOT=${PROJECT_ROOT}"
