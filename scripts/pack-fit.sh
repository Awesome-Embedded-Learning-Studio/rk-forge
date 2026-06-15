#!/usr/bin/env bash
# pack-fit.sh — build the uboot + boot FIT images with MAINLINE mkimage.
#
# The headline mainline substitution in forge's NAND packaging (notes/09 §二②③):
# vendor built both FITs with rkbin/tools/mkimage (2017.09); we use mainline
# U-Boot's own tools/mkimage (2026.07-rc4). Format-level compatibility is proven
# (mainline mkimage -l parses vendor FITs; -E and -p 0x800 are both supported).
#
# Two FITs, matching the vendor package-file names:
#   uboot.img ← rk3506-mainline.its  (u-boot-nodtb + tee + u-boot.dtb)   mkimage -E
#   boot.img  ← rk3506-kernel.its    (zImage + dtb + initramfs)          mkimage -E -p 0x800
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
MKIMAGE="${EXPLORE}/uboot/tools/mkimage"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,24p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -x "$MKIMAGE" ]] || die "mainline mkimage not built: $MKIMAGE (build U-Boot first)"

need() { [[ -f "$1" ]] || die "missing input: $1"; }
UBOOT_BIN="${EXPLORE}/uboot/u-boot-nodtb.bin"
UBOOT_DTB="${EXPLORE}/uboot/u-boot.dtb"
ZIMAGE="${EXPLORE}/linux/arch/arm/boot/zImage"
KERN_DTB="${EXPLORE}/linux/arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
INITRAMFS="${BRINGUP}/fit/initramfs.cpio.gz"
need "$UBOOT_BIN"; need "$UBOOT_DTB"; need "$ZIMAGE"; need "$KERN_DTB"; need "$INITRAMFS"

# tee blob: prefer forge explore/rkbin, fall back to vendor-sdk/rkbin.
TEE=""
for t in "${EXPLORE}/rkbin/bin/rk35/rk3506_tee_v2.40.bin" \
         "${_PROJECT_ROOT}/third_party/vendor-sdk/rkbin/bin/rk35/rk3506_tee_v2.40.bin"; do
  [[ -f "$t" ]] && TEE="$t" && break
done
[[ -n "$TEE" ]] || die "missing tee blob (rk3506_tee_v2.40.bin)"

mkdir -p "$OUT_DIR"
W1=$(mktemp -d); W2=$(mktemp -d)
trap 'rm -rf "$W1" "$W2"' EXIT

# --- uboot FIT (rk3506-mainline.its) ---------------------------------------
cp "$UBOOT_BIN" "$W1/uboot-nodtb.bin"
cp "$UBOOT_DTB" "$W1/u-boot.dtb"
cp "$TEE"       "$W1/tee.bin"
cp "${BRINGUP}/fit/rk3506-mainline.its" "$W1/"
log_info "packing uboot.img (mainline mkimage -E)…"
( cd "$W1" && "$MKIMAGE" -f rk3506-mainline.its -E uboot.img >/dev/null )
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
log_ok "boot.img → $OUT_DIR/boot.img ($(stat -c%s "$OUT_DIR/boot.img") B)"

log_warn "mainline-mkimage FITs: board-boot unverified (notes/09 §五①)."
