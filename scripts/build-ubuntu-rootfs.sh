#!/usr/bin/env bash
# build-ubuntu-rootfs.sh — build the Ubuntu 26.04 aarch64 rootfs tarball for the ubuntu profile.
#
# Strategy (user picked ubuntu-base + apt over debootstrap):
#   1. fetch ubuntu-base-<ver>-base-arm64.tar.gz from cdimage.ubuntu.com (~30MB; cached in
#      $OUT_DIR/dl/)
#   2. extract to a work dir (as root — the tarball stores root-owned files)
#   3. chroot in via qemu-user-static binfmt + apt install the package list
#      (board/<board>/ubuntu/packages.list) — systemd/init, ssh, netplan, mesa (Panthor),
#      linux-firmware (brcmfmac FW for AP6xxx), dev tools
#   4. post-config: fstab (root on /dev/mmcblk?p3), hostname, root account + firstboot
#      resize, resolv.conf, apt cleanup
#   5. tar up → $OUT_DIR/ubuntu-rootfs.tar + touch $OUT_DIR/.ubuntu-rootfs-built
#
# Dependencies (NOT auto-installed — forge is sudo-free by design, this script is the one
# exception because chroot needs root + qemu for foreign-arch apt):
#   sudo apt install qemu-user-static           # binfmt_misc arm64 handler (apt pulls binfmt-support)
#   network access to cdimage.ubuntu.com + ports.ubuntu.com (arm64 archive)
# Run as root (the script re-execs under sudo if invoked as a normal user).
#
# Usage:
#   sudo scripts/build-ubuntu-rootfs.sh [--clean] [--version 26.04]
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR + BRINGUP + FORGE_BOARD
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

# --- re-exec under sudo if not root (chroot + foreign apt need CAP_SYS_ADMIN) ---
if [[ "${EUID}" -ne 0 ]]; then
  log_info "re-execing under sudo (chroot + qemu apt need root)…"
  exec sudo -E "$0" "$@"
fi

UBUNTU_VERSION="${UBUNTU_VERSION:-26.04}"
CLEAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)   CLEAN=1; shift;;
    --version) UBUNTU_VERSION="$2"; shift 2;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

# arm64 Ubuntu uses the ports archive (not archive.ubuntu.com); the chroot sources.list is
# rewritten below to point there. ubuntu-base's /etc/os-release carries the codename; we do
# NOT hardcode it here (26.04 codename confirmed at first run).
DL_DIR="${OUT_DIR}/dl"
WORK_DIR="${OUT_DIR}/ubuntu-rootfs.work"
ROOTFS_TAR="${OUT_DIR}/ubuntu-rootfs.tar"
BUILT_MARKER="${OUT_DIR}/.ubuntu-rootfs-built"
PKG_LIST="${BRINGUP}/ubuntu/packages.list"
BASE_URL="https://cdimage.ubuntu.com/ubuntu-base/releases/${UBUNTU_VERSION}/release"
BASE_TGZ="ubuntu-base-${UBUNTU_VERSION}-base-arm64.tar.gz"

need_tool() { command -v "$1" >/dev/null || die "missing host tool: $1 (apt: qemu-user-static)"; }
need_tool qemu-aarch64-static
[[ -f "$PKG_LIST" ]] || die "missing package list: $PKG_LIST"

mkdir -p "$DL_DIR" "$OUT_DIR"

# --- 1. fetch ubuntu-base (cached) ---
if [[ ! -f "${DL_DIR}/${BASE_TGZ}" ]]; then
  log_info "downloading ${BASE_TGZ} (~30MB)…"
  curl -fL -o "${DL_DIR}/${BASE_TGZ}.partial" "${BASE_URL}/${BASE_TGZ}"
  mv "${DL_DIR}/${BASE_TGZ}.partial" "${DL_DIR}/${BASE_TGZ}"
fi
log_ok "ubuntu-base cached: ${DL_DIR}/${BASE_TGZ}"

# --- 2. extract (clean work dir) ---
if [[ "$CLEAN" == 1 ]]; then rm -rf "$WORK_DIR"; fi
if [[ -d "$WORK_DIR" ]]; then
  log_info "reusing existing work dir ($WORK_DIR); use --clean to start fresh"
else
  mkdir -p "$WORK_DIR"
  log_info "extracting ubuntu-base → $WORK_DIR"
  tar xf "${DL_DIR}/${BASE_TGZ}" -C "$WORK_DIR"
fi

# --- 3. chroot + apt install ---
# Copy the qemu static interpreter into the chroot (binfmt looks it up by absolute path
# inside the chroot's namespace). Bind-mount /proc /sys /dev + resolv.conf for apt network.
cp "$(command -v qemu-aarch64-static)" "${WORK_DIR}/usr/bin/"
mount --bind /proc "${WORK_DIR}/proc"
mount --bind /sys  "${WORK_DIR}/sys"
mount --bind /dev  "${WORK_DIR}/dev"
# shellcheck disable=SC2016
cp /etc/resolv.conf "${WORK_DIR}/etc/resolv.conf" 2>/dev/null || true

cleanup() {
  umount "${WORK_DIR}/proc" 2>/dev/null || true
  umount "${WORK_DIR}/sys"  2>/dev/null || true
  umount "${WORK_DIR}/dev"  2>/dev/null || true
}
trap cleanup EXIT

# Rewrite sources.list to the arm64 ports archive (ubuntu-base may point at a wrong mirror).
# Read the codename from the extracted rootfs so we don't hardcode 26.04's codename.
CODENAME="$(. "${WORK_DIR}/etc/os-release"; echo "${VERSION_CODENAME:-$UBUNTU_VERSION}")"
log_info "ubuntu codename: ${CODENAME}"
# 国内镜像（清华 tuna）优先 + 官方 ports 兜底。先清掉 ubuntu-base 自带的 deb822
# (ubuntu.sources) 避免和这里的老格式 sources.list 重复。
rm -f "${WORK_DIR}/etc/apt/sources.list" "${WORK_DIR}/etc/apt/sources.list.d/ubuntu.sources"
cat > "${WORK_DIR}/etc/apt/sources.list" <<EOF
deb [arch=arm64] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports ${CODENAME} main restricted universe multiverse
deb [arch=arm64] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports ${CODENAME}-updates main restricted universe multiverse
deb [arch=arm64] http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports ${CODENAME}-security main restricted universe multiverse
# 官方 ports 源兜底（万一镜像缺包）
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports ${CODENAME} main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports ${CODENAME}-updates main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports ${CODENAME}-security main restricted universe multiverse
EOF

log_info "apt update + install packages (qemu chroot)…"
chroot "$WORK_DIR" /usr/bin/apt-get update
# shellcheck disable=SC2046
chroot "$WORK_DIR" /usr/bin/apt-get install -y --no-install-recommends \
  $(grep -hE '^[a-zA-Z0-9]' "$PKG_LIST" | sed 's/#.*//')
chroot "$WORK_DIR" /usr/bin/apt-get clean

# --- 4. post-config ---
# fstab: root on the 3rd partition of the eMMC device. The mmcblk device number is confirmed
# on hardware (mmcblk1p3 by analogy with rk3568-atk; adjust if RK3588 enumerates as mmcblk0).
cat > "${WORK_DIR}/etc/fstab" <<'EOF'
/dev/mmcblk1p3  /        ext4   defaults,noatime              0 1
proc            /proc    proc   defaults                      0 0
tmpfs           /tmp     tmpfs  defaults,nosuid,nodev         0 0
tmpfs           /var/log tmpfs  defaults,nosuid,nodev         0 0
EOF
echo "rk3588-topeet" > "${WORK_DIR}/etc/hostname"
# Vendor-compatible Rockchip FIQ debugger console on UART2.
mkdir -p "${WORK_DIR}/etc/systemd/system/getty.target.wants"
ln -sf /lib/systemd/system/serial-getty@.service \
  "${WORK_DIR}/etc/systemd/system/getty.target.wants/serial-getty@ttyFIQ0.service"
# root login with no password (MVP — set a real password before shipping)
chroot "$WORK_DIR" /usr/bin/passwd -d root || true

# GDM intentionally does not expose root as a desktop login.  Create the
# conventional development account in newly built tarballs; stage-rootfs.sh
# repeats this idempotently for older cached tarballs.  Credentials are
# charliechen/chen0303 and GDM autologin is enabled for bring-up only.
if ! chroot "$WORK_DIR" /usr/bin/id -u charliechen >/dev/null 2>&1; then
  chroot "$WORK_DIR" /usr/sbin/useradd -m -U -u 1000 -s /bin/bash \
    -c 'Charlie Chen' -G adm,sudo,audio,video,render,input,plugdev,netdev charliechen
fi
printf '%s\n' 'charliechen:chen0303' | chroot "$WORK_DIR" /usr/sbin/chpasswd
mkdir -p "$WORK_DIR/var/lib/AccountsService/users" "$WORK_DIR/etc/gdm3"
printf '%s\n' '[User]' 'SystemAccount=false' \
  > "$WORK_DIR/var/lib/AccountsService/users/charliechen"
chmod 0600 "$WORK_DIR/var/lib/AccountsService/users/charliechen"
printf '%s\n' \
  '[daemon]' \
  'AutomaticLoginEnable = true' \
  'AutomaticLogin = charliechen' \
  '' \
  '[security]' \
  '' \
  '[debug]' \
  > "$WORK_DIR/etc/gdm3/custom.conf"

# remove the qemu static from the final rootfs (not needed on real arm64)
rm -f "${WORK_DIR}/usr/bin/qemu-aarch64-static"

# --- 5. tar up ---
cleanup
trap - EXIT
log_info "packing ubuntu-rootfs.tar…"
tar -C "$WORK_DIR" --owner=0 --group=0 -cf "$ROOTFS_TAR" .
touch "$BUILT_MARKER"
log_ok "Ubuntu rootfs → $ROOTFS_TAR ($(du -sh "$ROOTFS_TAR" | cut -f1))"
log_info "next: forge pack (stage-rootfs → pack-emmc) assembles the ext4"
