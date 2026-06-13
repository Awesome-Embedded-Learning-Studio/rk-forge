#!/usr/bin/env bash
# log.sh — shared logging, single source of truth.
# Sourced unconditionally from a known relative path. No per-script fallback
# color blocks (that duplication was imx-forge's smell).
#
# Seam contract (future Python wrapper): data -> stdout, diagnostics -> stderr.
# So never printf progress chatter into a function's data stdout.
[[ -n "${LOG_LIB_LOADED:-}" ]] && return 0   # already sourced; skip redefinition
LOG_LIB_LOADED=1

if [[ -t 1 ]]; then
  C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_GRN=$'\033[32m'; C_BLU=$'\033[34m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_RED=''; C_YEL=''; C_GRN=''; C_BLU=''; C_DIM=''; C_OFF=''
fi

log_info()  { printf '%s\n' "${C_BLU}[INFO]${C_OFF} $*"; }
log_ok()    { printf '%s\n' "${C_GRN}[ OK ]${C_OFF} $*"; }
log_warn()  { printf '%s\n' "${C_YEL}[WARN]${C_OFF} $*" >&2; }
log_error() { printf '%s\n' "${C_RED}[ERR ]${C_OFF} $*" >&2; }
log_debug() { [[ "${DEBUG:-0}" == "1" ]] && printf '%s\n' "${C_DIM}[DBG ]${C_OFF} $*" >&2 || true; }
log_cmd()   { printf '%s\n' "${C_DIM}\$ %s${C_OFF}" "$*" >&2; "$@"; }   # echo-then-run
die()       { log_error "$*"; exit 1; }
