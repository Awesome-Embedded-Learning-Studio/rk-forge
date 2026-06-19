#!/usr/bin/env bash
# pack-fit.sh — build all FIT images (uboot + boot + boot-nand) with fit-pack.py.
#
# ALL three FITs are now packed by scripts/fit-pack.py — one pure-Python packing
# tool, no mkimage dependency for packing (decoupled from the mainline U-Boot
# build). The ATK vendor-sdk mkimage dependency (P4) is closed; mainline mkimage
# is retained only for the `mkimage -l` parse check below. See notes/20 (saga).
#
# Three FITs, matching the vendor package-file names:
#   uboot.img      ← rk3506-mainline.its    (u-boot-nodtb + tee + u-boot.dtb)
#       fit-pack.py Mode A — consumed by vendor SPL: data-offset (relative),
#       0x200-aligned external, root version+totalsize+timestamp.
#   boot.img       ← rk3506-kernel.its      (zImage + dtb + initramfs)
#   boot-nand.img  ← rk3506-kernel-nand.its (zImage + dtb, no ramdisk → UBIFS root)
#       fit-pack.py Mode B (--external-offset 0x800, = mkimage -p 0x800) — consumed
#       by mainline U-Boot bootm: data-position (absolute), contiguous external at
#       0x800, root /timestamp only.
#
# HONEST EDGE: fit-pack.py's output is structurally + hash-identical to the mkimage
# originals (selftest-proven per image) but not raw byte-identical — mkimage leaves
# a residual pre-fdt_pack gap and host timestamp/totalsize (+trailing pad in Mode B)
# that the consumers never read. Board-boot is the final confirmation.
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
FIT_PACK="${_PROJECT_ROOT}/scripts/fit-pack.py"      # pure-Python vendor-layout FIT packer — uboot FIT (vendor-SPL -E)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,24p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

[[ -x "$MKIMAGE" ]] || die "mainline mkimage not built: $MKIMAGE (build U-Boot first)"
[[ -f "$FIT_PACK" ]] || die "fit-pack.py missing: $FIT_PACK"

need() { [[ -f "$1" ]] || die "missing input: $1"; }
UBOOT_BIN="${EXPLORE}/uboot/u-boot-nodtb.bin"
UBOOT_DTB="${EXPLORE}/uboot/u-boot.dtb"
ZIMAGE="${EXPLORE}/linux/arch/arm/boot/zImage"
KERN_DTB="${EXPLORE}/linux/arch/arm/boot/dts/rockchip/rk3506b-aes.dtb"
INITRAMFS="${BRINGUP}/fit/initramfs.cpio.gz"
need "$UBOOT_BIN"; need "$UBOOT_DTB"; need "$ZIMAGE"; need "$KERN_DTB"; need "$INITRAMFS"

# tee blob: resolved from the SAME rkbin source as the loader (FORGE_RKBIN_DIR, default
# the public submodule) so the SPL↔tee verified-boot hash pair stays CONSISTENT.
#   public submodule → tee v2.40 (pairs with public SPL v1.12 in pack-loader.sh)
#   rkbin-atk fallback → tee v2.10 (pairs with ATK SPL v1.11; sha256 93603ca22c…)
# The sfc-dll-saga "tee v2.40 = Bad hash" was a MIXING artifact: ATK SPL v1.11 (which
# checks v2.10's hash) reading public tee v2.40. A fully-public chain — public SPL v1.12
# checking public tee v2.40, both from the same rkbin release — is internally consistent
# and should verify. Board-test is the confirmation. uboot is a loadable (not hash-locked),
# so tee is the ONLY thing whose hash must match the SPL. Do NOT mix blob sources between
# pack-loader.sh and pack-fit.sh.
FORGE_RKBIN_DIR="${FORGE_RKBIN_DIR:-${_PROJECT_ROOT}/third_party/rkbin}"
TEE=$(ls "$FORGE_RKBIN_DIR"/bin/rk35/rk3506_tee_v*.bin 2>/dev/null | grep -v _ta_ | sort -V | tail -1)
[[ -n "$TEE" && -f "$TEE" ]] || die "missing tee blob under $FORGE_RKBIN_DIR/bin/rk35 (need rk3506_tee_v*.bin; init submodule or run scripts/fetch-deps.sh atk-blobs)"
log_info "tee blob: $(basename "$TEE") (from $FORGE_RKBIN_DIR) — must pair with the SPL variant in pack-loader.sh"

mkdir -p "$OUT_DIR"
W1=$(mktemp -d); W2=$(mktemp -d)
trap 'rm -rf "$W1" "$W2" "${W3:-}"' EXIT

# --- uboot FIT (rk3506-mainline.its) ---------------------------------------
cp "$UBOOT_BIN" "$W1/uboot-nodtb.bin"
cp "$UBOOT_DTB" "$W1/u-boot.dtb"
cp "$TEE"       "$W1/tee.bin"
cp "${BRINGUP}/fit/rk3506-mainline.its" "$W1/"
# uboot FIT is packed by fit-pack.py, NOT mkimage: vendor SPL only parses the
# external-data layout vendor mkimage 2017.09 emits, and the ATK fork that produces
# it is non-public. fit-pack.py reproduces that layout in pure Python (FDT +
# 0x200-aligned external data + per-image sha256, /totalsize sized so Rockchip SPL
# loads the whole image). `fit-pack.py selftest` proves it structurally +
# hash-identical to vendor's output; board-boot is the final confirmation. The tee
# variant is resolved above from FORGE_RKBIN_DIR. The kernel FITs below are loaded
# by mainline U-Boot (accepts mainline mkimage FITs), so they stay on mainline mkimage.
log_info "packing uboot.img (fit-pack.py, vendor-SPL-compatible -E layout)…"
python3 "$FIT_PACK" pack "$W1/rk3506-mainline.its" "$W1/uboot.img"
cp "$W1/uboot.img" "$OUT_DIR/uboot.img"
"$MKIMAGE" -l "$OUT_DIR/uboot.img" >/dev/null || die "uboot.img failed FIT parse"
log_ok "uboot.img → $OUT_DIR/uboot.img ($(stat -c%s "$OUT_DIR/uboot.img") B)"

# --- boot FIT (rk3506-kernel.its) ------------------------------------------
cp "$ZIMAGE"    "$W2/zImage"
cp "$KERN_DTB"  "$W2/rk3506b-aes.dtb"
cp "$INITRAMFS" "$W2/initramfs.cpio.gz"
cp "${BRINGUP}/fit/rk3506-kernel.its" "$W2/"
# boot.img / boot-nand.img are packed by fit-pack.py too (Phase 2 — single packing
# tool for all FITs, decoupling pack-fit from the mainline U-Boot mkimage build).
# These are consumed by MAINLINE U-Boot (bootm), so they use Mode B: -E -p 0x800 →
# data-position (absolute), contiguous external data at 0x800, root /timestamp only
# (no version/totalsize — those are ATK-specific). `fit-pack.py selftest --vendor
# <img> --its <its>` proves structure+blob+hash parity with the mainline-mkimage output.
log_info "packing boot.img (fit-pack.py Mode B, --external-offset 0x800)…"
python3 "$FIT_PACK" pack --external-offset 0x800 "$W2/rk3506-kernel.its" "$W2/boot.img"
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
log_info "packing boot-nand.img (fit-pack.py Mode B --external-offset 0x800, no ramdisk)…"
python3 "$FIT_PACK" pack --external-offset 0x800 "$W3/rk3506-kernel-nand.its" "$W3/boot-nand.img"
cp "$W3/boot-nand.img" "$OUT_DIR/boot-nand.img"
"$MKIMAGE" -l "$OUT_DIR/boot-nand.img" >/dev/null || die "boot-nand.img failed FIT parse"
log_ok "boot-nand.img → $OUT_DIR/boot-nand.img ($(stat -c%s "$OUT_DIR/boot-nand.img") B, no ramdisk → UBIFS root)"

log_warn "all FITs now forge-packed (fit-pack.py); board-boot of these is the confirmation."
