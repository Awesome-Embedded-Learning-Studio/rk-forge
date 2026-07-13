#!/usr/bin/env bash
# stage-rootfs.sh — stage the rootfs tree at out/rootfs/ for pack-ubifs.sh.
#
# Profile-driven (ROOTFS_PROFILE, set by forge.sh):
#   buildroot (default) — extract buildroot's rootfs.tar + stage 8733bu.ko + WiFi FW
#   openwrt             — rsync OpenWrt's TARGET_DIR (musl busybox+procd+kmod tree;
#                         kmod packages already installed under lib/modules/ by
#                         OpenWrt's package/install, so NO manual .ko staging)
#
# Both produce $OUT_DIR/rootfs/ (a tree with /bin/busybox), consumed unchanged by
# pack-ubifs.sh (NAND) and pack-sd.sh (SD) — the rootfs-format-agnostic seam.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + BUILDROOT/OPENWRT_DIR/OUT_DIR/LINUX_DIR
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

ROOTFS_PROFILE="${ROOTFS_PROFILE:-buildroot}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

ROOT="${OUT_DIR}/rootfs"
rm -rf "$ROOT"
mkdir -p "$ROOT"

# Firmware staging is shared by both profiles: the RTL8733BU blobs are a
# belt-and-suspenders fallback (the driver loads FW from a built-in C array at
# runtime — log boot-sdl-202606201050 L613 — so /lib/firmware files are unused
# but harmless). Sourced from the forge-local firmware/rtl8733bu/ dir, NOT the
# ATK vendor-sdk path (keeps the rootfs build self-contained).
stage_wifi_firmware() {
  mkdir -p "$ROOT/lib/firmware"
  local fw_dir="${RTL8733BU_FW_DIR:-${_PROJECT_ROOT}/firmware/rtl8733bu}"
  for fw in rtl8733bu_fw rtl8733bu_config; do
    [[ -f "${fw_dir}/${fw}" ]] && cp "${fw_dir}/${fw}" "$ROOT/lib/firmware/${fw}"
  done
  if [[ -f "$ROOT/lib/firmware/rtl8733bu_fw" ]]; then
    log_ok "firmware rtl8733bu_fw + rtl8733bu_config → lib/firmware/ (unused-at-runtime fallback)"
  else
    log_info "note: no firmware/rtl8733bu/ blobs — harmless (driver loads FW from built-in array)"
  fi
}

if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
  # OpenWrt's TARGET_DIR is the live rootfs tree (musl + busybox + procd + the
  # selected kmod packages already installed under lib/modules/<ver>/ by OpenWrt's
  # package/install). rsync it — OpenWrt's own image recipes consume TARGET_DIR the
  # same way. No tarball round-trip. Path: build_dir/target-<arch>_musl/root-rk3506.
  OW_TARGET_DIR="$(find "$OPENWRT_DIR/build_dir" -name 'root-rockchip' -type d 2>/dev/null | head -1)"
  [[ -n "$OW_TARGET_DIR" && -f "$OW_TARGET_DIR/bin/busybox" ]] \
    || die "OpenWrt TARGET_DIR missing/incomplete: ${OW_TARGET_DIR:-<not found>} (run: forge build --rootfs=openwrt)"
  log_info "rsync OpenWrt TARGET_DIR → $ROOT"
  rsync -a "$OW_TARGET_DIR/" "$ROOT/"
  log_ok "OpenWrt rootfs staged ($(du -sh "$ROOT" | cut -f1))"
  # kmod packages (incl. rtl8733bu if configured as a kmod) are already in
  # lib/modules/ — NO manual .ko staging (unlike buildroot, which doesn't run
  # OpenWrt's kmod install). Only the WiFi firmware fallback is staged.
  stage_wifi_firmware
  log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
  log_info "next: scripts/pack-ubifs.sh → $OUT_DIR/rootfs.ubi.img"
  exit 0
fi

# --- buildroot profile (the standard forge rootfs) ---------------------------
# buildroot (busybox+glibc+sysvinit, with the post-build mtdrawdump/mtdbb + the
# overlay fstab that keeps syslog in RAM so the UBIFS NAND doesn't get churned —
# see buildroot-external/overlay/etc/fstab + the RW saga).
ROOTFS_TAR="${BUILDROOT}/output/images/rootfs.tar"
[[ -f "$ROOTFS_TAR" ]] || die "missing buildroot rootfs.tar (build it first per buildroot-external/README.md): $ROOTFS_TAR"

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

stage_wifi_firmware

log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
log_info "next: scripts/pack-ubifs.sh → $OUT_DIR/rootfs.ubi.img"
