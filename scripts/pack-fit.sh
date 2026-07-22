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
# Variants (the NAND and SD uboot images are built from DIFFERENT defconfigs but
# share the SAME FIT structure — rk3506-mainline.its, Mode A):
#   default (nand) — packs uboot.img + boot.img + boot-nand.img + boot-sd.img
#   --variant sd   — packs ONLY uboot-sd.img from $OUT_DIR/u-boot-sd-nodtb.bin +
#                    u-boot-sd.dtb (the out-of-tree SD build, build-uboot.sh
#                    --variant sd). The SD defconfig differs from NAND only in
#                    bootcmd, so the FIT layout is identical — just a different
#                    u-boot-nodtb.bin payload. boot*.img are NOT re-packed (they
#                    were produced by the default NAND run; they don't depend on
#                    the uboot defconfig).
#
# HONEST EDGE: fit-pack.py's output is structurally + hash-identical to the mkimage
# originals (selftest-proven per image) but not raw byte-identical — mkimage leaves
# a residual pre-fdt_pack gap and host timestamp/totalsize (+trailing pad in Mode B)
# that the consumers never read. Board-boot is the final confirmation.
#
# Usage:
#   scripts/pack-fit.sh [--out <dir>] [--variant nand|sd]
# Inputs resolve from canonical build outputs (src/uboot, src/linux, rkbin)
# + the ITS/initramfs under board/aes/. Rebuild those first if stale.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR/LINUX_DIR/UBOOT_DIR/BRINGUP (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/rkbin.sh"    # rkbin_load: resolve tee (same resolver as pack-loader.sh)

MKIMAGE="${UBOOT_DIR}/tools/mkimage"            # mainline 2026.07-rc4 — kernel FIT (loaded by mainline U-Boot)
FIT_PACK="${_PROJECT_ROOT}/scripts/fit-pack.py"      # pure-Python vendor-layout FIT packer — uboot FIT (vendor-SPL -E)
VARIANT="nand"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    --variant) VARIANT="$2"; shift 2;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ "$VARIANT" == "nand" || "$VARIANT" == "sd" ]] \
  || die "unknown variant: $VARIANT (want nand|sd)"

[[ -x "$MKIMAGE" ]] || die "mainline mkimage not built: $MKIMAGE (build U-Boot first)"
[[ -f "$FIT_PACK" ]] || die "fit-pack.py missing: $FIT_PACK"

need() { [[ -f "$1" ]] || die "missing input: $1"; }
if [[ "$VARIANT" == "sd" ]]; then
  # SD uboot from the out-of-tree build (build-uboot.sh --variant sd). Only the
  # uboot FIT is packed here — the SD defconfig differs from NAND only in bootcmd,
  # so the FIT structure (rk3506-mainline.its, Mode A) is identical, just a
  # different u-boot-nodtb.bin payload → uboot-sd.img. boot*.img are NOT touched.
  UBOOT_BIN="${OUT_DIR}/u-boot-sd-nodtb.bin"
  UBOOT_DTB="${OUT_DIR}/u-boot-sd.dtb"
  UBOOT_FIT="uboot-sd.img"
  need "$UBOOT_BIN"; need "$UBOOT_DTB"
else
  UBOOT_BIN="${UBOOT_DIR}/u-boot-nodtb.bin"
  UBOOT_DTB="${UBOOT_DIR}/u-boot.dtb"
  UBOOT_FIT="uboot.img"
  KERNEL_ARTIFACT_DIR="${KERNEL_ARTIFACT_DIR:-$LINUX_DIR}"   # openwrt profile overrides this to OpenWrt's build_dir (set by forge.sh stage_pack)
  ZIMAGE="${KERNEL_ARTIFACT_DIR}/arch/${ARCH}/boot/${KERN_IMG}"
  KERN_DTB="${KERNEL_ARTIFACT_DIR}/arch/${ARCH}/boot/dts/rockchip/${DT_NAME}.dtb"
  INITRAMFS="${BRINGUP}/fit/initramfs.cpio.gz"
  need "$UBOOT_BIN"; need "$UBOOT_DTB"; need "$ZIMAGE"; need "$KERN_DTB"; need "$INITRAMFS"
fi

# tee blob: resolved via lib/rkbin.sh (rkbin_load) from FORGE_RKBIN_DIR — the SAME
# resolver pack-loader.sh uses, so the SPL<->tee hash pair is consistent by
# construction. The saga "tee v2.40 = Bad hash" was a MIXING artifact (ATK SPL
# reading public tee); a fully-public chain (public SPL v1.12 + public tee v2.40
# from the same rkbin) verifies. uboot is a loadable (not hash-locked), so tee is
# the ONLY blob whose hash must match the SPL. Run pack-loader + pack-fit with the
# SAME FORGE_RKBIN_DIR (the default public rkbin is the sole source).
rkbin_load
TEE="${RKBIN_BLOB_DIR}/${RKBIN_TEE}"
log_info "tee blob: $RKBIN_TEE (from $FORGE_RKBIN_DIR) — pairs with the SPL from the same source"

mkdir -p "$OUT_DIR"
W1=$(mktemp -d); W2=$(mktemp -d)
trap 'rm -rf "$W1" "$W2" "${W3:-}" "${W4:-}"' EXIT

# --- uboot FIT (rk3506-mainline.its) ---------------------------------------
cp "$UBOOT_BIN" "$W1/uboot-nodtb.bin"
cp "$UBOOT_DTB" "$W1/u-boot.dtb"
cp "$TEE"       "$W1/tee.bin"
cp "${BRINGUP}/fit/${SOC}-mainline.its" "$W1/"
# uboot FIT is packed by fit-pack.py, NOT mkimage: vendor SPL only parses the
# external-data layout vendor mkimage 2017.09 emits, and the ATK fork that produces
# it is non-public. fit-pack.py reproduces that layout in pure Python (FDT +
# 0x200-aligned external data + per-image sha256, /totalsize sized so Rockchip SPL
# loads the whole image). `fit-pack.py selftest` proves it structurally +
# hash-identical to vendor's output; board-boot is the final confirmation. The tee
# variant is resolved above from FORGE_RKBIN_DIR. The kernel FITs below are loaded
# by mainline U-Boot (accepts mainline mkimage FITs), so they stay on mainline mkimage.
log_info "packing $UBOOT_FIT (fit-pack.py, vendor-SPL-compatible -E layout)…"
python3 "$FIT_PACK" pack "$W1/${SOC}-mainline.its" "$W1/$UBOOT_FIT"
cp "$W1/$UBOOT_FIT" "$OUT_DIR/$UBOOT_FIT"
"$MKIMAGE" -l "$OUT_DIR/$UBOOT_FIT" >/dev/null || die "$UBOOT_FIT failed FIT parse"
log_ok "$UBOOT_FIT → $OUT_DIR/$UBOOT_FIT ($(stat -c%s "$OUT_DIR/$UBOOT_FIT") B)"

# --variant sd: the SD defconfig's ONLY FIT is uboot-sd.img (the boot*.img are
# produced by the default NAND run and don't depend on the uboot defconfig). Done.
if [[ "$VARIANT" == "sd" ]]; then
  log_info "variant=sd: only $UBOOT_FIT packed (boot*.img unchanged from the default run)"
  exit 0
fi

# --- boot FIT (rk3506-kernel.its) ------------------------------------------
cp "$ZIMAGE"    "$W2/${KERN_IMG}"
cp "$KERN_DTB"  "$W2/${DT_NAME}.dtb"
cp "$INITRAMFS" "$W2/initramfs.cpio.gz"
cp "${BRINGUP}/fit/${SOC}-kernel.its" "$W2/"
# boot.img / boot-nand.img are packed by fit-pack.py too (Phase 2 — single packing
# tool for all FITs, decoupling pack-fit from the mainline U-Boot mkimage build).
# These are consumed by MAINLINE U-Boot (bootm), so they use Mode B: -E -p 0x800 →
# data-position (absolute), contiguous external data at 0x800, root /timestamp only
# (no version/totalsize — those are ATK-specific). `fit-pack.py selftest --vendor
# <img> --its <its>` proves structure+blob+hash parity with the mainline-mkimage output.
log_info "packing boot.img (fit-pack.py Mode B, --external-offset 0x800)…"
python3 "$FIT_PACK" pack --external-offset 0x800 "$W2/${SOC}-kernel.its" "$W2/boot.img"
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
cp "$ZIMAGE"   "$W3/${KERN_IMG}"
cp "$KERN_DTB" "$W3/${DT_NAME}.dtb"
cp "${BRINGUP}/fit/${SOC}-kernel-nand.its" "$W3/"
log_info "packing boot-nand.img (fit-pack.py Mode B --external-offset 0x800, no ramdisk)…"
python3 "$FIT_PACK" pack --external-offset 0x800 "$W3/${SOC}-kernel-nand.its" "$W3/boot-nand.img"
cp "$W3/boot-nand.img" "$OUT_DIR/boot-nand.img"
"$MKIMAGE" -l "$OUT_DIR/boot-nand.img" >/dev/null || die "boot-nand.img failed FIT parse"
log_ok "boot-nand.img → $OUT_DIR/boot-nand.img ($(stat -c%s "$OUT_DIR/boot-nand.img") B, no ramdisk → UBIFS root)"

# --- boot FIT, SD-rootfs variant (no ramdisk → kernel mounts the SD ext4 root) ---
# Sibling of boot-nand.img: same zImage+dtb, NO ramdisk node. boot.img (with the
# provisioning initramfs) would hijack boot — its /init attaches NAND ubi0:rootfs
# and switch_roots there, ignoring bootargs root= (see log
# boot-sdl-202606210958: cmdline said mmcblk0p3 but /init mounted NAND UBIFS).
# With NO initramfs, the kernel honors bootargs root=/dev/mmcblk0p3 and mounts
# the SD card's GPT p3 (ext4) as root → true all-SD boot. Same FIT structure as
# boot-nand.img (media-agnostic); only the bootargs differ (set by U-Boot).
W4=$(mktemp -d)
trap 'rm -rf "$W1" "$W2" "${W3:-}" "${W4:-}"' EXIT
cp "$ZIMAGE"   "$W4/${KERN_IMG}"
cp "$KERN_DTB" "$W4/${DT_NAME}.dtb"
cp "${BRINGUP}/fit/${SOC}-kernel-sd.its" "$W4/"
log_info "packing boot-sd.img (fit-pack.py Mode B --external-offset 0x800, no ramdisk)…"
python3 "$FIT_PACK" pack --external-offset 0x800 "$W4/${SOC}-kernel-sd.its" "$W4/boot-sd.img"
cp "$W4/boot-sd.img" "$OUT_DIR/boot-sd.img"
"$MKIMAGE" -l "$OUT_DIR/boot-sd.img" >/dev/null || die "boot-sd.img failed FIT parse"
log_ok "boot-sd.img → $OUT_DIR/boot-sd.img ($(stat -c%s "$OUT_DIR/boot-sd.img") B, no ramdisk → SD ext4 root)"

log_warn "all FITs now forge-packed (fit-pack.py); board-boot of these is the confirmation."
