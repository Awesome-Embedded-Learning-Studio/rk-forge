#!/usr/bin/env bash
# stage-rootfs.sh — stage the buildroot UBIFS rootfs tree at out/rootfs/.
#
# The STANDARD forge rootfs is buildroot (busybox+glibc+sysvinit, with the
# post-build mtdrawdump/mtdbb + the overlay fstab that keeps syslog in RAM so
# the UBIFS NAND doesn't get churned — see buildroot-external/overlay/etc/fstab
# + the RW saga). mk-rootfs.sh is a separate static-busybox handcraft, NOT this.
#
# Flow: buildroot output/images/rootfs.tar  →  extract to out/rootfs  →
#       scripts/pack-ubifs.sh  →  scripts/assemble-update.sh --provision
# (see buildroot-external/README.md "Wire the rootfs into NAND packaging").
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

BRINGUP="${_PROJECT_ROOT}/third_party/bringup"
BUILDROOT="${_PROJECT_ROOT}/third_party/buildroot"
OUT_DIR="${BRINGUP}/out"
ROOTFS_TAR="${BUILDROOT}/output/images/rootfs.tar"
ASSETS="${_PROJECT_ROOT}/assets"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,18p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -f "$ROOTFS_TAR" ]] || die "missing buildroot rootfs.tar (build it first per buildroot-external/README.md): $ROOTFS_TAR"

ROOT="${OUT_DIR}/rootfs"
rm -rf "$ROOT"
mkdir -p "$ROOT"
log_info "extracting buildroot rootfs.tar → $ROOT"
tar xf "$ROOTFS_TAR" -C "$ROOT"
# sanity: buildroot marker + the overlay fstab landed
grep -q "Welcome to rk-forge buildroot" "$ROOT/etc/issue" 2>/dev/null \
  || log_info "note: /etc/issue is not the buildroot one"
grep -q "/var/log.*tmpfs" "$ROOT/etc/fstab" 2>/dev/null \
  || log_info "note: /var/log tmpfs overlay not applied (rebuild buildroot with BR2_ROOTFS_OVERLAY)"
log_ok "buildroot rootfs staged ($(du -sh "$ROOT" | cut -f1))"

# drop the audio test mp3 (Phase E) for on-board playback (mpg123 /root/...).
if [[ -f "$ASSETS/sample-3s.mp3" ]]; then
  mkdir -p "$ROOT/root"
  cp "$ASSETS/sample-3s.mp3" "$ROOT/root/sample-3s.mp3"
  log_ok "sample-3s.mp3 → root/ ($(stat -c%s "$ROOT/root/sample-3s.mp3") B)"
fi

# Phase WiFi: stage the out-of-tree RTL8733BU driver + firmware into the rootfs.
# The .ko is built in the kernel tree (CONFIG_RTL8733BU=m); firmware comes from
# the ATK overlay (rtl8733bu_fw + rtl8733bu_config — canonical chip names). The
# S99wifi init script (overlay/etc/init.d) insmods it after switch_root, when
# /lib/firmware is readable for request_firmware(). See document/notes/29.
LINUX="${_PROJECT_ROOT}/third_party/explore/linux"
KO="${LINUX}/drivers/net/wireless/realtek/rtl8733bu/8733bu.ko"
ATK_FW="${_PROJECT_ROOT}/third_party/vendor-sdk/buildroot/board/alientek/atk-dlrk3506/fs-overlay/usr/lib/firmware"
if [[ -f "$KO" ]]; then
  mkdir -p "$ROOT/lib/modules"
  cp "$KO" "$ROOT/lib/modules/8733bu.ko"
  log_ok "8733bu.ko → lib/modules/ ($(stat -c%s "$ROOT/lib/modules/8733bu.ko") B)"
else
  log_info "note: 8733bu.ko not built yet — run kernel module build first (WiFi will be absent)"
fi
mkdir -p "$ROOT/lib/firmware"
for fw in rtl8733bu_fw rtl8733bu_config; do
  if [[ -f "${ATK_FW}/${fw}" ]]; then
    cp "${ATK_FW}/${fw}" "$ROOT/lib/firmware/${fw}"
  else
    log_info "note: missing firmware ${fw} (ATK overlay moved?)"
  fi
done
[[ -f "$ROOT/lib/firmware/rtl8733bu_fw" ]] \
  && log_ok "firmware rtl8733bu_fw + rtl8733bu_config → lib/firmware/"

log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
log_info "next: scripts/pack-ubifs.sh  →  $OUT_DIR/rootfs.ubi.img"
