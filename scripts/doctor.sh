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

# host build essentials actually used by forge (mkimage comes from the U-Boot
# tree, NOT the host; qemu-system-arm isn't used — both were over-cautious
# carryovers). mkfs.ubifs/ubinize (pack-ubifs) + sgdisk (pack-sd) ARE needed.
for c in git make gcc bc bison flex dtc cpio mkfs.ubifs ubinize sgdisk; do
  if check_cmd "$c"; then log_ok "$c"; else log_warn "missing: $c"; MISSING+=("$c"); fi
done

# cross toolchain (Arm GNU Toolchain — NOT an apt package; don't add to the apt
# MISSING list, print a separate remediation instead)
TC_MISSING=0
if check_toolchain; then log_ok "toolchain: ${CROSS_COMPILE}gcc"; else
  log_warn "missing cross toolchain: ${CROSS_COMPILE}gcc (Arm GNU Toolchain — NOT apt)"
  log_warn "  install Arm GNU 15.2.Rel1 so \${TOOLCHAIN_BIN_DIR} (config/toolchain.conf) exists"
  log_warn "  download: https://developer.arm.com/downloads  →  GNU Toolchain"
  TC_MISSING=1
fi

# python helper for kernel build scripts
if python3 -c 'import elftools' 2>/dev/null; then log_ok "python3-pyelftools"; else
  log_warn "missing: python3-pyelftools"; MISSING+=("python3-pyelftools")
fi

# WSL2 advisory (not an error)
if grep -qi microsoft /proc/version 2>/dev/null; then
  log_info "WSL2 detected: USB flashing (rkdeveloptool) needs usbipd-win on Windows; SD-card flashing works directly."
fi

if [[ ${#MISSING[@]} -eq 0 && "$TC_MISSING" == 0 ]]; then
  log_ok "all dependencies present"
  exit 0
fi

# command -> Debian/Ubuntu package mapping (host deps only; the cross toolchain
# is Arm GNU, handled separately above — not apt-installable)
declare -A PKG=(
  [dtc]=device-tree-compiler [mkfs.ubifs]=mtd-utils [ubinize]=mtd-utils [sgdisk]=gdisk
  [bison]=bison [flex]=flex [cpio]=cpio [bc]=bc [git]=git [make]=make [gcc]=gcc
)
APT=(); seen=()
if [[ ${#MISSING[@]} -gt 0 ]]; then
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
  printf '\nFix host deps with:\n' >&2
  printf 'sudo apt install %s\n' "${APT[*]}"   # to stdout — copy-pasteable / Python-capturable
fi
[[ "$TC_MISSING" == 1 ]] && printf '\n(cross toolchain: see the Arm GNU note above, not apt)\n' >&2
exit 1
