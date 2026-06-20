#!/usr/bin/env bash
# mk-rootfs.sh — assemble the UBIFS rootfs tree at out/rootfs/ from forge sources.
#
# This is the rootfs that gets persisted to NAND's rootfs partition (DT
# partition@2740000, 174 MiB) and mounted by the kernel via bootargs
# root=ubi0:rootfs rootfstype=ubifs. Its /sbin/init is busybox's built-in init
# (CONFIG_INIT=y in the defconfig build — the applet is present in the binary).
#
# Reuses the ALREADY-VERIFIED static busybox from the mainline initramfs
# (third_party/bringup/fit/initramfs.cpio.gz): a defconfig build with the full
# applet set baked into one binary. We add applet symlinks + the /etc config
# source (third_party/bringup/rootfs/etc) + empty mount points. No busybox
# recompile. devtmpfs is auto-mounted by the kernel (CONFIG_DEVTMPFS_MOUNT=y), so
# /dev is already populated before init runs.
#
# Output tree (gitignored under out/) feeds scripts/pack-ubifs.sh.
#
# Usage:
#   scripts/mk-rootfs.sh [--out <dir>]
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + BRINGUP/OUT_DIR/BUILDROOT/ASSETS (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# Resolve the cross toolchain via config/toolchain.conf (exports CROSS_COMPILE,
# ARCH, PATH) so mtdrawdump/mtdbb track the active toolchain — no hardcoded path.
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"

INITRAMFS="${BRINGUP}/fit/initramfs.cpio.gz"
ETC_SRC="${BRINGUP}/rootfs/etc"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,21p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ -f "$INITRAMFS" ]] || die "missing initramfs (build per bringup/initramfs/README.md): $INITRAMFS"
[[ -d "$ETC_SRC" ]]   || die "missing etc source: $ETC_SRC"

ROOT="${OUT_DIR}/rootfs"
rm -rf "$ROOT"
log_info "assembling rootfs tree → $ROOT"
mkdir -p "$ROOT"/{bin,sbin,etc,proc,sys,dev,tmp,run,root,home,mnt,usr/bin,usr/sbin,var/log,var/run}

# --- busybox: reuse the verified static binary from initramfs ----------------
W=$(mktemp -d)
cp "$INITRAMFS" "$W/initramfs.cpio.gz"
( cd "$W" && gzip -d initramfs.cpio.gz && mkdir ext && cd ext && cpio -idm <../initramfs.cpio >/dev/null 2>&1 )
[[ -f "$W/ext/bin/busybox" ]] || die "no busybox in initramfs"
file "$W/ext/bin/busybox" | grep -qi 'statically linked' \
  || die "busybox not static — rebuild per bringup/initramfs/README.md"
cp "$W/ext/bin/busybox" "$ROOT/bin/busybox"
chmod 0755 "$ROOT/bin/busybox"
rm -rf "$W"
log_ok "busybox → bin/busybox ($(stat -c%s "$ROOT/bin/busybox") B, static armhf)"

# --- applet symlinks (defconfig ships all; no qemu needed to create links) ---
# Common applets from busybox defconfig. Extra symlinks are harmless (busybox
# only errors if an unknown applet is actually invoked). /sbin holds init +
# power-control so the kernel's default exec path /sbin/init works.
APPLETS_BIN="sh ash mount umount ls cat echo uname mkdir rmdir ps top dmesg pwd \
  vi ln cp mv rm chmod chown chgrp grep find free kill killall sleep hostname \
  sync dd hexdump md5sum sha256sum stat du df touch env id whoami head tail wc \
  sort uniq sed awk tar gzip gunzip xargs test true false date clear more \
  printf seq expr basename dirname tr cut paste tee mktemp ping ip ifconfig \
  route netstat wget mke2fs blkid lsmod insmod rmmod modprobe"
APPLETS_SBIN="init halt reboot poweroff mdev switch_root"
for a in $APPLETS_BIN;  do ln -sf busybox       "$ROOT/bin/$a"; done
for a in $APPLETS_SBIN; do ln -sf ../bin/busybox "$ROOT/sbin/$a"; done
ln -sf ../bin/busybox "$ROOT/linuxrc"
log_ok "applet symlinks: $(find "$ROOT/bin" "$ROOT/sbin" -type l | wc -l) links"

# --- mtdrawdump: static raw-dump inspector (SPI-NAND write-path forensics) ---
# Cross-compiled from source; statically linked so it runs on the busybox-only
# rootfs (no shared libc present). Uses the MEMREAD ioctl to read MTD erase
# blocks either with on-die ECC (default) or raw/no-ECC (-r), so we can tell a
# partially-erased block (sparse 0xFF + stale data) from a cleanly-programmed
# block whose bits flipped past ECC strength. Source lives alongside the rootfs
# config so the tool is rebuilt with the tree, not shipped as a binary blob.
MRD_SRC="${BRINGUP}/rootfs/mtdrawdump.c"
TC_GCC="$(command -v "${CROSS_COMPILE}gcc" || true)"
if [[ -f "$MRD_SRC" && -n "$TC_GCC" ]]; then
  "$TC_GCC" -O2 -static -s -o "$ROOT/bin/mtdrawdump" "$MRD_SRC" \
    || die "mtdrawdump compile failed"
  chmod 0755 "$ROOT/bin/mtdrawdump"
  log_ok "mtdrawdump → bin/mtdrawdump ($(stat -c%s "$ROOT/bin/mtdrawdump") B, static armhf)"
else
  log_info "skipping mtdrawdump (source or toolchain missing) — non-fatal"
fi

# --- mtdbb: bad-block forensics + management (mark/erase/test/scan) ---------
# Companion to mtdrawdump: once the ECC scan finds "hidden" bad blocks (blocks
# that program successfully but read back ECC-uncorrectable, so UBI never marks
# them), mtdbb marks them bad (MEMSETBADBLOCK) so UBI's next attach excludes
# them. Also erase+write+readback test (hard vs soft bad) + full ECC scan.
MTBB_SRC="${BRINGUP}/rootfs/mtdbb.c"
if [[ -f "$MTBB_SRC" && -x "$TC_GCC" ]]; then
  "$TC_GCC" -O2 -static -s -o "$ROOT/bin/mtdbb" "$MTBB_SRC" \
    || die "mtdbb compile failed"
  chmod 0755 "$ROOT/bin/mtdbb"
  log_ok "mtdbb → bin/mtdbb ($(stat -c%s "$ROOT/bin/mtdbb") B, static armhf)"
else
  log_info "skipping mtdbb (source or toolchain missing) — non-fatal"
fi

# --- /etc config source ------------------------------------------------------
cp -a "$ETC_SRC"/. "$ROOT/etc/"

# --- audio test tooling (Phase E) -------------------------------------------
# Pull the dynamic aplay/mpg123 binaries + their glibc runtime out of buildroot
# output/target (built with alsa-utils + mpg123) into the otherwise
# static-busybox handcraft rootfs, so the ES8388/sai1 sound card can be
# exercised (aplay -l / speaker-test / mpg123 the bundled mp3). busybox stays
# static; these shared libs only serve the dynamic audio tools.
BR_TARGET="${BUILDROOT}/output/target"
if [[ -d "$BR_TARGET" && -x "$BR_TARGET/usr/bin/aplay" ]]; then
	mkdir -p "$ROOT/usr/bin" "$ROOT/lib" "$ROOT/usr/lib"
	for b in aplay arecord amixer speaker-test mpg123; do
		[[ -x "$BR_TARGET/usr/bin/$b" ]] && cp "$BR_TARGET/usr/bin/$b" "$ROOT/usr/bin/"
	done
	# glibc runtime (ld-linux + libc/libm/…) + alsa-lib + libmpg123 shared libs.
	cp -a "$BR_TARGET"/lib/* "$ROOT/lib/" 2>/dev/null || true
	cp -a "$BR_TARGET"/usr/lib/libasound.so* "$BR_TARGET"/usr/lib/libmpg123.so* "$ROOT/usr/lib/" 2>/dev/null || true
	log_ok "audio tooling → $(ls "$ROOT/usr/bin/" 2>/dev/null | tr '\n' ' ')"
else
	log_info "skipping audio tooling (no buildroot aplay — run the buildroot build first)"
fi
[[ -f "$ASSETS/sample-3s.mp3" ]] && { cp "$ASSETS/sample-3s.mp3" "$ROOT/root/sample-3s.mp3"; log_ok "sample-3s.mp3 → root/"; }

# --- perms: sticky tmp dirs --------------------------------------------------
chmod 1777 "$ROOT/tmp"
log_ok "etc config + mount points ready"
log_info "tree size: $(du -sh "$ROOT" | cut -f1)"
log_info "next: scripts/pack-ubifs.sh  →  $OUT_DIR/rootfs.ubi.img"
