#!/usr/bin/env bash
# pack-fit.sh — build the uboot + boot FIT images with MAINLINE mkimage.
#
# The headline mainline substitution in forge's NAND packaging (notes/09 §二②③):
# vendor built both FITs with rkbin/tools/mkimage (2017.09); we use mainline
# U-Boot's own tools/mkimage (2026.07-rc4). Format-level compatibility is proven
# (mainline mkimage -l parses vendor FITs; -E and -p 0x800 are both supported).
#
# Two FITs, matching the vendor package-file names:
#   uboot.img ← rk3506-mainline.its  (u-boot-nodtb + tee + u-boot.dtb)   VENDOR mkimage -E
#       (vendor SPL parses only vendor mkimage's -E external-data layout — using
#        mainline mkimage here → SPL reads optee at wrong offset → "optee Bad hash"
#        → falls back to residual vendor uboot → can't boot mainline kernel)
#   boot.img  ← rk3506-kernel.its    (zImage + dtb + initramfs)          mainline mkimage -E -p 0x800
#       (loaded by mainline U-Boot, which accepts mainline mkimage FITs)
#
# HONEST EDGE: these mainline-mkimage FITs are standard FIT, but whether the
# vendor SPL's FIT parser actually boots them is board-test pending — our
# currently-booting .itb was built with vendor mkimage. Same ITS, same -E/-p; low risk.
#
# Usage:
#   scripts/pack-fit.sh [--out <dir>]
# Inputs resolve from canonical build outputs (explore/uboot, explore/linux, rkbin)
# + the ITS/initramfs under third_party/bringup/. Rebuild those first if stale.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

EXPLORE="${_PROJECT_ROOT}/third_party/explore"
BRINGUP="${_PROJECT_ROOT}/third_party/bringup"
OUT_DIR="${BRINGUP}/out"
MKIMAGE="${EXPLORE}/uboot/tools/mkimage"            # mainline 2026.07-rc4 — kernel FIT (loaded by mainline U-Boot)
VENDOR_MKIMAGE="${_PROJECT_ROOT}/third_party/vendor-sdk/u-boot/tools/mkimage"  # vendor 2017.09 — uboot FIT (vendor-SPL -E layout)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,24p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -x "$MKIMAGE" ]] || die "mainline mkimage not built: $MKIMAGE (build U-Boot first)"
[[ -x "$VENDOR_MKIMAGE" ]] || die "vendor mkimage not found: $VENDOR_MKIMAGE (needed for uboot FIT — vendor SPL needs its -E external-data layout)"

need() { [[ -f "$1" ]] || die "missing input: $1"; }
UBOOT_BIN="${EXPLORE}/uboot/u-boot-nodtb.bin"
UBOOT_DTB="${EXPLORE}/uboot/u-boot.dtb"
ZIMAGE="${EXPLORE}/linux/arch/arm/boot/zImage"
KERN_DTB="${EXPLORE}/linux/arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
INITRAMFS="${BRINGUP}/fit/initramfs.cpio.gz"
need "$UBOOT_BIN"; need "$UBOOT_DTB"; need "$ZIMAGE"; need "$KERN_DTB"; need "$INITRAMFS"

# tee blob: prefer forge explore/rkbin, fall back to vendor-sdk/rkbin.
# tee MUST be vendor v2.10 (rk3506_tee_v2.10.bin, 125904 B). vendor SPL's verified
# boot checks the optee hash and v2.10 is what it expects (方案 B, proven on board).
# explore/rkbin v2.40 has a different hash → SPL rejects the FIT ("optee Bad hash")
# → falls back to a residual vendor uboot → vendor uboot can't boot mainline kernel
# → hang. uboot is a loadable (not hash-locked), so the ONLY thing that must match
# the SPL is this tee. Do NOT "upgrade" to v2.40.
TEE="${_PROJECT_ROOT}/third_party/vendor-sdk/rkbin/bin/rk35/rk3506_tee_v2.10.bin"
[[ -f "$TEE" ]] || die "missing vendor tee (rk3506_tee_v2.10.bin, 125904 B) — required by vendor SPL verified boot"

mkdir -p "$OUT_DIR"
W1=$(mktemp -d); W2=$(mktemp -d)
trap 'rm -rf "$W1" "$W2" "${W3:-}"' EXIT

# --- uboot FIT (rk3506-mainline.its) ---------------------------------------
cp "$UBOOT_BIN" "$W1/uboot-nodtb.bin"
cp "$UBOOT_DTB" "$W1/u-boot.dtb"
cp "$TEE"       "$W1/tee.bin"
cp "${BRINGUP}/fit/rk3506-mainline.its" "$W1/"
# uboot FIT MUST use vendor mkimage (2017.09) -E: vendor SPL only parses the
# external-data layout vendor mkimage emits. mainline mkimage's -E puts optee data
# at a different offset → SPL reads mis-aligned bytes → "optee Bad hash" (e.g.
# 7b78fe4e instead of the expected 93603ca22c = vendor tee v2.10's sha256) → SPL
# rejects the FIT → falls back to a residual vendor uboot → can't boot mainline
# kernel → hang. (方案 B, board-proven.) Kernel FIT below is loaded by mainline
# U-Boot (which accepts mainline mkimage FITs), so it stays on mainline mkimage.
log_info "packing uboot.img (vendor mkimage -E, vendor-SPL-compatible layout)…"
( cd "$W1" && "$VENDOR_MKIMAGE" -f rk3506-mainline.its -E uboot.img >/dev/null )
cp "$W1/uboot.img" "$OUT_DIR/uboot.img"
"$MKIMAGE" -l "$OUT_DIR/uboot.img" >/dev/null || die "uboot.img failed FIT parse"
log_ok "uboot.img → $OUT_DIR/uboot.img ($(stat -c%s "$OUT_DIR/uboot.img") B)"

# --- boot FIT (rk3506-kernel.its) ------------------------------------------
cp "$ZIMAGE"    "$W2/zImage"
cp "$KERN_DTB"  "$W2/rk3506b-aes.dtb"
cp "$INITRAMFS" "$W2/initramfs.cpio.gz"
cp "${BRINGUP}/fit/rk3506-kernel.its" "$W2/"
log_info "packing boot.img (mainline mkimage -E -p 0x800)…"
( cd "$W2" && "$MKIMAGE" -f rk3506-kernel.its -E -p 0x800 boot.img >/dev/null )
cp "$W2/boot.img" "$OUT_DIR/boot.img"
"$MKIMAGE" -l "$OUT_DIR/boot.img" >/dev/null || die "boot.img failed FIT parse"
log_ok "boot.img → $OUT_DIR/boot.img ($(stat -c%s "$OUT_DIR/boot.img") B, with initramfs)"

# --- boot FIT, NAND-rootfs variant (no ramdisk → kernel mounts UBIFS root) ---
# Sibling of boot.img: same zImage+dtb, but NO ramdisk node. Without an
# initramfs /init to hijack boot, the kernel honors bootargs root=ubi0:rootfs,
# attaches UBI on mtd5, mounts the UBIFS rootfs, then execs /sbin/init. Use this
# for the persistent-rootfs boot; keep boot.img (with initramfs) as the fallback
# rescue shell (swap which one you write to the boot partition).
W3=$(mktemp -d)
cp "$ZIMAGE"   "$W3/zImage"
cp "$KERN_DTB" "$W3/rk3506b-aes.dtb"
cp "${BRINGUP}/fit/rk3506-kernel-nand.its" "$W3/"
log_info "packing boot-nand.img (mkimage -E -p 0x800, no ramdisk)…"
( cd "$W3" && "$MKIMAGE" -f rk3506-kernel-nand.its -E -p 0x800 boot-nand.img >/dev/null )
cp "$W3/boot-nand.img" "$OUT_DIR/boot-nand.img"
"$MKIMAGE" -l "$OUT_DIR/boot-nand.img" >/dev/null || die "boot-nand.img failed FIT parse"
log_ok "boot-nand.img → $OUT_DIR/boot-nand.img ($(stat -c%s "$OUT_DIR/boot-nand.img") B, no ramdisk → UBIFS root)"

log_warn "mainline-mkimage FITs + UBIFS rootfs: board-boot pending (this step)."
