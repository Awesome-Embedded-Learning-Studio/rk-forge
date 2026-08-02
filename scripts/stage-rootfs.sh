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

# Ubuntu's source tar stores numeric root ownership.  forge intentionally runs
# without sudo, so preserve that metadata with a persistent fakeroot database;
# pack-emmc.sh reloads the same database before mke2fs reads this tree.
ROOTFS_FAKEROOT_STATE="${OUT_DIR}/.rootfs.fakeroot"
if [[ "$ROOTFS_PROFILE" == "ubuntu" && "${RK_FORGE_ROOTFS_FAKEROOT:-0}" != 1 ]]; then
  command -v fakeroot >/dev/null || die "missing host tool: fakeroot (needed to preserve Ubuntu rootfs ownership)"
  rm -f "$ROOTFS_FAKEROOT_STATE"
  log_info "staging Ubuntu rootfs under fakeroot (persistent ownership metadata)"
  export FAKEROOTDONTTRYCHOWN=1
  exec fakeroot -s "$ROOTFS_FAKEROOT_STATE" -- \
    env RK_FORGE_ROOTFS_FAKEROOT=1 ROOTFS_PROFILE="$ROOTFS_PROFILE" \
    bash "$0" --out "$OUT_DIR"
fi

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

if [[ "$ROOTFS_PROFILE" == "ubuntu" ]]; then
  # ubuntu profile: extract the Ubuntu rootfs tarball built by build-ubuntu-rootfs.sh
  # (ubuntu-base + apt via qemu-user-static chroot). For rk3588-topeet, WIFI_DRIVER is
  # empty — AP6xxx WiFi uses the mainline brcmfmac driver (in the kernel) + firmware from
  # the linux-firmware package already inside the tarball, so NO .ko staging here.
  UBUNTU_ROOTFS_TAR="${OUT_DIR}/ubuntu-rootfs.tar"
  [[ -f "$UBUNTU_ROOTFS_TAR" ]] \
    || die "missing ubuntu rootfs.tar (build it first: forge build --rootfs=ubuntu): $UBUNTU_ROOTFS_TAR"
  log_info "extracting ubuntu rootfs.tar → $ROOT"
  tar --numeric-owner --same-owner -xf "$UBUNTU_ROOTFS_TAR" -C "$ROOT"

  # The cached Ubuntu tar may predate the ttyFIQ0 port. Enforce the board's
  # console ownership at every staging pass so no ttyS2 getty can reopen the
  # same UART behind the FIQ debugger.
  if [[ "$FORGE_BOARD" == "rk3588-topeet" ]]; then
    # GDM does not offer root as a desktop login.  The cached rootfs tar predates
    # user provisioning, so enforce one conventional development account on
    # every staging pass.  The password is deliberately documented and must be
    # changed/locked before production deployment.
    if ! grep -q '^charliechen:' "$ROOT/etc/passwd"; then
      awk -F: '$3 == 1000 { found = 1 } END { exit !found }' "$ROOT/etc/passwd" && \
        die "cannot create charliechen user: UID 1000 already exists"
      awk -F: '$3 == 1000 { found = 1 } END { exit !found }' "$ROOT/etc/group" && \
        die "cannot create charliechen group: GID 1000 already exists"

      printf '%s\n' 'charliechen:x:1000:1000:Charlie Chen:/home/charliechen:/bin/bash' >> "$ROOT/etc/passwd"
      printf '%s\n' 'charliechen:$6$rkforge$B35cyT3RgiRXukvoxFiUgd.tgUmjHP5II67DT3VWmWZzf.p5GjiLEX6AZrAI.VbtuhHhXlFeyKZzzQ3m1B4I91:20500:0:99999:7:::' >> "$ROOT/etc/shadow"
      printf '%s\n' 'charliechen:x:1000:' >> "$ROOT/etc/group"
      printf '%s\n' 'charliechen:!::' >> "$ROOT/etc/gshadow"

      add_group_member() {
        local account_file="$1" group_name="$2" tmp_file
        tmp_file="${account_file}.rkforge-tmp"
        awk -F: -v OFS=: -v group_name="$group_name" '
          $1 == group_name {
            if ($4 == "")
              $4 = "charliechen"
            else if (("," $4 ",") !~ /,charliechen,/)
              $4 = $4 ",charliechen"
          }
          { print }
        ' "$account_file" > "$tmp_file"
        chmod --reference="$account_file" "$tmp_file"
        mv "$tmp_file" "$account_file"
      }
      for group_name in adm sudo audio video render input plugdev netdev; do
        grep -q "^${group_name}:" "$ROOT/etc/group" || die "missing Ubuntu group: $group_name"
        add_group_member "$ROOT/etc/group" "$group_name"
        add_group_member "$ROOT/etc/gshadow" "$group_name"
      done

      mkdir -p "$ROOT/home/charliechen"
      if [[ -d "$ROOT/etc/skel" ]]; then
        cp -a "$ROOT/etc/skel/." "$ROOT/home/charliechen/"
      fi
      chown -R 1000:1000 "$ROOT/home/charliechen"
      chmod 0750 "$ROOT/home/charliechen"
    fi

    mkdir -p "$ROOT/var/lib/AccountsService/users"
    printf '%s\n' '[User]' 'SystemAccount=false' \
      > "$ROOT/var/lib/AccountsService/users/charliechen"
    chmod 0600 "$ROOT/var/lib/AccountsService/users/charliechen"

    mkdir -p "$ROOT/etc/gdm3"
    printf '%s\n' \
      '[daemon]' \
      'AutomaticLoginEnable = true' \
      'AutomaticLogin = charliechen' \
      '' \
      '[security]' \
      '' \
      '[debug]' \
      > "$ROOT/etc/gdm3/custom.conf"

    mkdir -p "$ROOT/etc/systemd/system/getty.target.wants"
    rm -f "$ROOT/etc/systemd/system/getty.target.wants/serial-getty@ttyS2.service"
    ln -sf /lib/systemd/system/serial-getty@.service \
      "$ROOT/etc/systemd/system/getty.target.wants/serial-getty@ttyFIQ0.service"

    # ttyFIQ0 is IRQ-backed and cannot diagnose a global IRQ/hard lockup.  Keep
    # the independent DesignWare watchdog alive through systemd so a full hang
    # becomes a warm reset (which preserves the ramoops window), and make every
    # detector panic instead of merely printing into an unreachable console.
    mkdir -p "$ROOT/etc/systemd/system.conf.d" "$ROOT/etc/sysctl.d"
    printf '%s\n' \
      '[Manager]' \
      'RuntimeWatchdogSec=30s' \
      > "$ROOT/etc/systemd/system.conf.d/10-rk3588-lockup-diagnostics.conf"
    printf '%s\n' \
      'kernel.panic = 10' \
      'kernel.panic_on_oops = 1' \
      'kernel.softlockup_panic = 1' \
      'kernel.hardlockup_panic = 1' \
      'kernel.hung_task_panic = 1' \
      'kernel.hung_task_timeout_secs = 60' \
      'kernel.panic_on_rcu_stall = 1' \
      'kernel.watchdog_thresh = 10' \
      > "$ROOT/etc/sysctl.d/90-rk3588-lockup-diagnostics.conf"
  fi
  log_ok "Ubuntu rootfs staged ($(du -sh "$ROOT" | cut -f1))"
  log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
  log_info "next: scripts/pack-emmc.sh → $OUT_DIR/rootfs.ext4"
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

# Phase WiFi: stage the WiFi driver module into the rootfs (board-gated via
# WIFI_DRIVER). The .ko is built in-tree (CONFIG_<WIFI_DRIVER>=m; drop
# materialized by scripts/fetch-<driver>-driver.sh + wired by a quilt patch).
# The S99wifi init script (overlay/etc/init.d) insmods it after switch_root.
if [[ -n "${WIFI_DRIVER:-}" ]]; then
  WIFI_MOD="${WIFI_DRIVER#rtl}"
  LINUX="${LINUX_DIR}"
  KO="${LINUX}/drivers/net/wireless/realtek/${WIFI_DRIVER}/${WIFI_MOD}.ko"
  if [[ -f "$KO" ]]; then
    mkdir -p "$ROOT/lib/modules"
    cp "$KO" "$ROOT/lib/modules/${WIFI_MOD}.ko"
    log_ok "${WIFI_MOD}.ko → lib/modules/ ($(stat -c%s "$ROOT/lib/modules/${WIFI_MOD}.ko") B)"
  else
    log_info "note: ${WIFI_MOD}.ko not built yet — run kernel module build first (WiFi will be absent)"
  fi
  # Firmware: rtl8733bu loads FW from a built-in array (/lib/firmware files are
  # an unused belt-suspenders fallback); rtl8852bs is built-in-only (array_8852b_*
  # — no /lib/firmware staging at all, the .ko carries the FW). See notes/42.
  [[ "$WIFI_DRIVER" == "rtl8733bu" ]] && stage_wifi_firmware
fi

log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
log_info "next: scripts/pack-ubifs.sh → $OUT_DIR/rootfs.ubi.img"
