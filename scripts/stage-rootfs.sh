#!/usr/bin/env bash
# stage-rootfs.sh — stage the buildroot UBIFS rootfs tree at out/rootfs/.
#
# The STANDARD forge rootfs is buildroot (busybox+glibc+sysvinit, with the
# post-build mtdrawdump/mtdbb + the overlay fstab that keeps syslog in RAM so
# the UBIFS NAND doesn't get churned — see buildroot-external/overlay/etc/fstab
# + the RW saga).
#
# Flow: buildroot output/images/rootfs.tar  →  extract to out/rootfs  →
#       scripts/pack-ubifs.sh  →  scripts/assemble-update.sh --provision
# (see buildroot-external/README.md "Wire the rootfs into NAND packaging").
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + BRINGUP/BUILDROOT/OUT_DIR/ASSETS (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

ROOTFS_TAR="${BUILDROOT}/output/images/rootfs.tar"

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

# audio test mp3 (Phase E, mpg123 /root/...): shipped via the buildroot overlay
# (overlay/root/sample-3s.mp3) — buildroot auto-copies it into rootfs/root/, so
# no manual cp here (was: cp from assets/).

# Phase WiFi: stage the RTL8733BU driver module into the rootfs.
# The .ko is built in-tree (CONFIG_RTL8733BU=m; the drop is materialized by
# scripts/fetch-rtl8733bu-driver.sh + wired by quilt patch 0016). The S99wifi
# init script (overlay/etc/init.d) insmods it after switch_root. See notes/29.
LINUX="${LINUX_DIR}"
KO="${LINUX}/drivers/net/wireless/realtek/rtl8733bu/8733bu.ko"
if [[ -f "$KO" ]]; then
  mkdir -p "$ROOT/lib/modules"
  cp "$KO" "$ROOT/lib/modules/8733bu.ko"
  log_ok "8733bu.ko → lib/modules/ ($(stat -c%s "$ROOT/lib/modules/8733bu.ko") B)"
else
  log_info "note: 8733bu.ko not built yet — run kernel module build first (WiFi will be absent)"
fi

# Firmware: best-effort from the forge-local firmware/rtl8733bu/ dir. UNUSED at
# runtime — the driver loads firmware from a built-in C array (log
# boot-sdl-202606201050 L613), so /lib/firmware files are a belt-and-suspenders
# fallback only. Sourcing here (NOT the ATK vendor-sdk path) keeps forge's rootfs
# build self-contained — reference/vendor-sdk is the extraction pool, not a build input.
# See firmware/rtl8733bu/README.md.
mkdir -p "$ROOT/lib/firmware"
FW_DIR="${RTL8733BU_FW_DIR:-${_PROJECT_ROOT}/firmware/rtl8733bu}"
for fw in rtl8733bu_fw rtl8733bu_config; do
  [[ -f "${FW_DIR}/${fw}" ]] && cp "${FW_DIR}/${fw}" "$ROOT/lib/firmware/${fw}"
done
if [[ -f "$ROOT/lib/firmware/rtl8733bu_fw" ]]; then
  log_ok "firmware rtl8733bu_fw + rtl8733bu_config → lib/firmware/ (unused-at-runtime fallback)"
else
  log_info "note: no firmware/rtl8733bu/ blobs — harmless (driver loads FW from built-in array)"
fi

log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
log_info "next: scripts/pack-ubifs.sh  →  $OUT_DIR/rootfs.ubi.img"
