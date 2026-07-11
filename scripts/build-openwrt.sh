#!/usr/bin/env bash
# build-openwrt.sh — build OpenWrt kernel (zImage + aes.dtb) + rootfs tree for aes.
#
# OpenWrt is a full firmware builder: it builds its OWN musl toolchain, the
# kernel (linux 7.1 + the quilt patches-7.1/ that carry rk-forge's patches
# 0001-0016 byte-identical), and the rootfs (busybox+procd+kmod packages).
# rk-forge then takes OpenWrt's kernel artifacts (zImage+aes.dtb via
# KERNEL_ARTIFACT_DIR) + the rootfs tree (TARGET_DIR via stage-rootfs.sh) and
# does its own RK-specific packing (fit-pack.py + rkfw-pack.py + mainline U-Boot).
#
# Toolchain: OpenWrt builds its OWN (musl-based). Do NOT force the rk-forge
# external glibc toolchain — it would break the musl userspace AND the kmod
# vermagic (kmod packages pin to the kernel's .config hash, built by OpenWrt's
# own gcc). This is a deliberate divergence from the buildroot profile.
#
# Usage:
#   scripts/build-openwrt.sh [--reconfigure] [--clean]
#     --reconfigure  regen .config from the aes-nand seed before make
#     --clean        make clean first (full rebuild; slow)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OPENWRT_DIR + OUT_DIR + BRINGUP
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/host.sh"    # forge_warn_windows_path / forge_clean_path (WSL)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/progress.sh"   # forge_progress_run

RECONFIGURE=0; CLEAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reconfigure) RECONFIGURE=1; shift;;
    --clean) CLEAN=1; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ -d "$OPENWRT_DIR" ]] || die "openwrt tree not found: $OPENWRT_DIR (run: forge setup --rootfs=openwrt)"

forge_warn_windows_path
cd "$OPENWRT_DIR"

# 1. feeds (OpenWrt's package sources). Idempotent: skip if feeds/packages is
#    populated unless --reconfigure. `feeds update` fetches; `feeds install`
#    symlinks packages into package/feeds/ so .config can select them.
if [[ ! -d feeds/packages || "$RECONFIGURE" == 1 ]]; then
  log_info "feeds update -a && install -a (fetches luci/packages/routing/telephony)"
  PATH="$(forge_clean_path)" ./scripts/feeds update -a
  PATH="$(forge_clean_path)" ./scripts/feeds install -a
fi

# 2. .config seed (rk-forge-maintained). Selects the aes_nand device + TARGZ
#    rootfs + package set. `make defconfig` expands the seed into a full .config.
SEED="${BRINGUP}/openwrt/aes-nand.config"
[[ -f "$SEED" ]] || die "missing OpenWrt .config seed: $SEED"
if [[ "$RECONFIGURE" == 1 || ! -f .config ]]; then
  log_info "seeding .config from $SEED (make defconfig expands dependencies)"
  cp "$SEED" .config
  PATH="$(forge_clean_path)" make defconfig
fi

# 3. ensure dl/linux-7.1.tar.gz exists. czz8888's kernel-headers download URL is
#    broken (GitHub archive file is v7.1.tar.gz, not linux-7.1.tar.gz → download.pl
#    404s on every mirror). Regenerate via `git archive v7.1 | gzip -n` from the
#    rk-forge linux tree — the hash matches czz8888's LINUX_KERNEL_HASH exactly
#    (both are the deterministic git-archive of tag v7.1). Requires the linux tree
#    fetched by `forge setup --rootfs=openwrt`. (Hash from include/kernel-7.1.)
ensure_linux_tarball() {
  local tarball="$OPENWRT_DIR/dl/linux-7.1.tar.gz"
  local expected="ad7f8010a17ecd9959c79cba639dfbbc9dccbbfb7323c5f1d04421368939f18f"
  if [[ -f "$tarball" ]] && [[ "$(sha256sum "$tarball" | cut -d' ' -f1)" == "$expected" ]]; then
    log_info "dl/linux-7.1.tar.gz present (hash OK) — skip regenerate"
    return 0
  fi
  log_info "regenerating dl/linux-7.1.tar.gz via git archive v7.1 (czz8888 download URL is broken)"
  [[ -d "$LINUX_DIR/.git" ]] \
    || die "linux tree missing at $LINUX_DIR (run: forge setup --rootfs=openwrt)"
  mkdir -p "$OPENWRT_DIR/dl"
  ( cd "$LINUX_DIR" && git archive --format=tar --prefix=linux-7.1/ v7.1 | gzip -n ) > "$tarball" \
    || die "git archive v7.1 failed"
  [[ "$(sha256sum "$tarball" | cut -d' ' -f1)" == "$expected" ]] \
    || die "generated linux-7.1.tar.gz hash mismatch (expected $expected)"
  log_ok "dl/linux-7.1.tar.gz regenerated ($(stat -c%s "$tarball") B)"
}
ensure_linux_tarball

# 4. build (toolchain → kernel → packages → rootfs). First time ~30-90min,
#    downloads toolchain sources (the linux-7.1 tarball is local — see above).
#    OpenWrt uses its OWN musl toolchain (NOT the rk-forge glibc one — see header).
[[ "$CLEAN" == 1 ]] && { log_info "make clean"; PATH="$(forge_clean_path)" make clean >/dev/null; }
log_info "make -j$(nproc) (PATH cleaned; OpenWrt own musl toolchain; ~30-90min first time)"
PATH="$(forge_clean_path)" forge_progress_run kernel make -j"$(nproc)"

# 4. verify kernel artifacts (zImage + aes.dtb) — these feed pack-fit.sh via
#    KERNEL_ARTIFACT_DIR (resolved by forge.sh stage_pack to this build dir).
KDIR="$(find "$OPENWRT_DIR/build_dir/linux-rockchip_rk3506" -maxdepth 1 -name 'linux-*' -type d | head -1)"
[[ -n "$KDIR" ]] || die "OpenWrt kernel build dir not found (build failed?)"
ZIMAGE="$KDIR/arch/arm/boot/zImage"
AES_DTB="$KDIR/arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
for f in "$ZIMAGE" "$AES_DTB"; do
  [[ -f "$f" ]] || die "missing OpenWrt kernel artifact: $f (was the aes_nand device selected in .config?)"
done
# verify the rootfs tree (TARGET_DIR) for stage-rootfs.sh
OW_TARGET_DIR="$(find "$OPENWRT_DIR/build_dir" -maxdepth 2 -name 'root-rk3506' -type d | head -1)"
[[ -n "$OW_TARGET_DIR" && -f "$OW_TARGET_DIR/bin/busybox" ]] \
  || die "OpenWrt TARGET_DIR missing/incomplete: ${OW_TARGET_DIR:-<not found>}"

log_ok "OpenWrt zImage → $ZIMAGE ($(stat -c%s "$ZIMAGE") B)"
log_ok "OpenWrt aes.dtb → $AES_DTB"
log_ok "OpenWrt rootfs tree → $OW_TARGET_DIR ($(du -sh "$OW_TARGET_DIR" | cut -f1))"

# 5. marker for stage-rootfs fingerprint (forge.sh stage_pack watches this mtime
#    in the openwrt profile so a re-build re-stages the rootfs tree).
mkdir -p "$OUT_DIR"
touch "$OUT_DIR/.openwrt-built"
log_info "next: forge pack (pack-fit reads KERNEL_ARTIFACT_DIR; stage-rootfs rsyncs TARGET_DIR)"
