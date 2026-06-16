#!/usr/bin/env bash
# assemble-update.sh — assemble a flashable RK update.img from forge-built
# partition images, using Rockchip's afptool + rkImageMaker.
#
# update.img stage of forge's NAND packaging (notes/09 §二⑥ + §三). Two vendor
# packers (both stripped x86-64 ELF, no source — see BLOBS.md):
#   afptool  -pack   → RKAF container (package-file manifest + partition images)
#   rkImageMaker      → wraps RKAF with the RKFW header + loader
# Both are deterministic packers (like boot_merger); for a non-secure build the
# output is unsigned and reproducible.
#
# Two variants, selected by the manifest (package-file-aes.txt vs -nand.txt):
#  default      — loader + parameter + uboot + boot(initramfs). rootfs/recovery/
#                 oem/userdata OMITTED; we boot from initramfs in boot.img, so
#                 flashing writes only uboot+boot and leaves NAND rootfs untouched.
#                 (Same selective flash the Windows RKDevTool flow did by checking
#                 only those rows.) Rescue-shell variant.
#  --nand       — boot becomes the no-ramdisk FIT (kernel mounts UBIFS root) and
#                 rootfs=rootfs.ubi.img is added, so flashing writes uboot + boot
#                 + rootfs in one go — the persistent-NAND-rootfs boot path.
#
# Board-independent proof: after packing, the script unpacks its OWN output
# (rkImageMaker -unpack + afptool -unpack) and verifies the expected partitions
# are present with matching sizes. No board needed to trust the pipeline.
#
# Usage:
#   scripts/assemble-update.sh [--out <dir>] [--nand] [--no-verify]
# Prereq: pack-loader.sh + pack-fit.sh have populated $OUT_DIR
#        (for --nand: also scripts/mk-rootfs.sh + scripts/pack-ubifs.sh).
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

BRINGUP="${_PROJECT_ROOT}/third_party/bringup"
OUT_DIR="${BRINGUP}/out"
PACK="${_PROJECT_ROOT}/third_party/vendor-sdk/tools/linux/Linux_Pack_Firmware/rockdev"
VERIFY=1
NAND=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    --nand) NAND=1; shift;;
    --loader) LOADER="$2"; shift 2;;
    --no-verify) VERIFY=0; shift;;
    -h|--help) sed -n '2,32p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

AFPTOOL="${PACK}/afptool"
RKIMGMAKER="${PACK}/rkImageMaker"
LOADER="${LOADER:-${OUT_DIR}/MiniLoaderAll.bin}"  # --loader overrides (e.g. ATK release rk3506_spl_loader_v1.06.111.bin)
UBOOT="${OUT_DIR}/uboot.img"
PARAMETER="${BRINGUP}/parameter-nand-aes.txt"
ROOTFS=""
if [[ "$NAND" == 1 ]]; then
  # NAND-rootfs variant: boot FIT without ramdisk (kernel mounts UBIFS root) +
  # the UBI image for the rootfs partition. Manifest adds the rootfs row.
  BOOT="${OUT_DIR}/boot-nand.img"
  PKGFILE="${BRINGUP}/package-file-nand.txt"
  ROOTFS="${OUT_DIR}/rootfs.ubi.img"
  UPDATE_OUT="${OUT_DIR}/update-nand.img"
  VARIANT="NAND-UBIFS"
else
  # Default: boot FIT with initramfs (rescue shell), rootfs partition untouched.
  BOOT="${OUT_DIR}/boot.img"
  PKGFILE="${BRINGUP}/package-file-aes.txt"
  UPDATE_OUT="${OUT_DIR}/update.img"
  VARIANT="initramfs"
fi
for f in "$AFPTOOL" "$RKIMGMAKER" "$LOADER" "$UBOOT" "$BOOT" "$PARAMETER" "$PKGFILE" ${ROOTFS:+"$ROOTFS"}; do
  [[ -r "$f" ]] || die "missing: $f (run pack-loader.sh + pack-fit.sh first; for --nand also mk-rootfs.sh + pack-ubifs.sh)"
done

ROCKDEV=$(mktemp -d); VFY=""
trap 'rm -rf "$ROCKDEV" "$VFY"' EXIT
mkdir -p "$ROCKDEV/Image"
cp "$PKGFILE"   "$ROCKDEV/package-file"
cp "$LOADER"    "$ROCKDEV/Image/MiniLoaderAll.bin"
cp "$PARAMETER" "$ROCKDEV/Image/parameter.txt"
cp "$UBOOT"     "$ROCKDEV/Image/uboot.img"
cp "$BOOT"      "$ROCKDEV/Image/boot.img"   # boot-nand.img staged as boot.img to match the manifest
[[ -n "$ROOTFS" ]] && cp "$ROOTFS" "$ROCKDEV/Image/rootfs.img"

log_info "afptool -pack (RKAF container, variant=$VARIANT)…"
( cd "$ROCKDEV" && "$AFPTOOL" -pack ./ Image/update.raw.img >/dev/null 2>&1 )
[[ -f "$ROCKDEV/Image/update.raw.img" ]] || die "afptool produced no update.raw.img"

# Chip tag: read 4 bytes at offset 21 of the loader, reverse → "RKxxxx" — this is
# the vendor mk-updateimg.sh method (device/rockchip/common/scripts/). The RK3506B
# loader's CHIP_NAME is RK350F (RKBOOT-RK3506B-aes.ini), so TAG=RK350F, NOT
# "RK3506". Hardcoding -RK3506 writes a tag that mismatches the loader → RKDevTool
# upgrade-firmware chip-verify fails ("校验芯片失败,请使用工具生成"). NB:
# rockdev/rk3506-mkupdate.sh hardcodes RK3506 but is a stale/simplified helper;
# mk-updateimg.sh (reads the tag from the loader) is authoritative.
TAG="RK$(dd if="$LOADER" bs=1 count=4 skip=21 status=none | rev)"
log_info "rkImageMaker -$TAG (RKFW header + loader)…"
"$RKIMGMAKER" -$TAG "$LOADER" "$ROCKDEV/Image/update.raw.img" "$UPDATE_OUT" \
  -os_type:androidos >/dev/null 2>&1
[[ -f "$UPDATE_OUT" ]] || die "rkImageMaker produced no $UPDATE_OUT"
log_ok "$(basename "$UPDATE_OUT") → $UPDATE_OUT ($(stat -c%s "$UPDATE_OUT") B, variant=$VARIANT)"

# --- round-trip self-check (board-independent) ----------------------------
if [[ "$VERIFY" == 1 ]]; then
  log_info "round-trip self-check (unpack own output)…"
  VFY=$(mktemp -d)
  "$RKIMGMAKER" -unpack "$UPDATE_OUT" "$VFY" >/dev/null 2>&1 \
    || die "self-check FAIL: rkImageMaker -unpack"
  "$AFPTOOL" -unpack "$VFY/firmware.img" "$VFY" >/dev/null 2>&1 \
    || die "self-check FAIL: afptool -unpack"
  PARTS=(parameter.txt uboot.img boot.img)
  PAIRS=("uboot.img:$UBOOT" "boot.img:$BOOT")
  [[ -n "$ROOTFS" ]] && { PARTS+=(rootfs.img); PAIRS+=("rootfs.img:$ROOTFS"); }
  for part in "${PARTS[@]}"; do
    [[ -f "$VFY/$part" ]] || die "self-check FAIL: $part missing after unpack"
  done
  for pair in "${PAIRS[@]}"; do
    p=${pair%%:*}; src=${pair#*:}
    a=$(stat -c%s "$VFY/$p"); b=$(stat -c%s "$src")
    [[ "$a" == "$b" ]] || die "self-check FAIL: $p size $a != source $b"
  done
  log_ok "self-check OK: $(basename "$UPDATE_OUT") round-trips to {parameter, uboot, boot${ROOTFS:+, rootfs}} with matching sizes"
fi

log_info "flash from Linux:  rkdeveloptool db <loader>  ;  rkdeveloptool uf $UPDATE_OUT"
log_warn "rkdeveloptool SPI-NAND support on RK3506B = board-test pending (notes/09 §七)."
