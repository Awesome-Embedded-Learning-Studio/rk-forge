#!/usr/bin/env bash
# doctor.sh — standalone environment checker.
# NO interactive /dev/tty apt-install (that was imx-forge env-init.sh's trap — it
# made the script un-Python-wrap-able). Here we just PRINT the remediation command
# to stdout and exit 0 (ok) / 1 (missing something).
# Seam: clean exit codes; diagnostics to stderr; the apt line to stdout.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"

MISSING=()
check_cmd() { command -v "$1" >/dev/null 2>&1; }

printf '== rk-forge doctor ==\n' >&2

# host build essentials
for c in git make gcc bc bison flex dtc cpio qemu-system-arm mkimage; do
  if check_cmd "$c"; then log_ok "$c"; else log_warn "missing: $c"; MISSING+=("$c"); fi
done

# cross toolchain
if check_toolchain; then log_ok "toolchain: ${CROSS_COMPILE}gcc"; else
  log_warn "missing cross toolchain: ${CROSS_COMPILE}gcc"; MISSING+=("gcc-arm-linux-gnueabihf")
fi

# python helper for kernel build scripts
if python3 -c 'import elftools' 2>/dev/null; then log_ok "python3-pyelftools"; else
  log_warn "missing: python3-pyelftools"; MISSING+=("python3-pyelftools")
fi

# WSL2 advisory (not an error)
if grep -qi microsoft /proc/version 2>/dev/null; then
  log_info "WSL2 detected: USB flashing (rkdeveloptool) needs usbipd-win on Windows; SD-card flashing works directly."
fi

if [[ ${#MISSING[@]} -eq 0 ]]; then
  log_ok "all dependencies present"
  exit 0
fi

# command -> Debian/Ubuntu package mapping
declare -A PKG=(
  [dtc]=device-tree-compiler [mkimage]=u-boot-tools [qemu-system-arm]=qemu-system-arm
  [bison]=bison [flex]=flex [cpio]=cpio [bc]=bc [git]=git [make]=make [gcc]=gcc
)
APT=(); seen=()
for m in "${MISSING[@]}"; do
  pkg="${PKG[$m]:-$m}"
  for s in "${seen[@]:-}"; do [[ "$s" == "$pkg" ]] && continue 2; done
  seen+=("$pkg"); APT+=("$pkg")
done
# libs the kernel/u-boot builds always want
for extra in libssl-dev libncurses-dev; do
  for s in "${seen[@]:-}"; do [[ "$s" == "$extra" ]] && continue 2; done
  APT+=("$extra")
done

printf '\nFix with:\n' >&2
printf 'sudo apt install %s\n' "${APT[*]}"   # to stdout — copy-pasteable / Python-capturable
exit 1
