#!/usr/bin/env bash
# assemble-update.sh — assemble a flashable RK update.img from forge-built
# partition images, using Rockchip's afptool + rkImageMaker.
#
# update.img stage of forge's NAND packaging (notes/09 §二⑥ + §三). Two vendor
# packers (both stripped x86-64 ELF, no source — see BLOBS.md):
#   afptool  -pack   → RKAF container (package-file manifest + partition images)
#   rkImageMaker      → wraps RKAF with the RKFW header + loader
# Both are deterministic packagers (like boot_merger); for a non-secure build the
# output is unsigned and reproducible.
#
# The manifest (package-file-aes.txt) lists only what we produce today:
# bootloader(loader) + parameter + uboot + boot. rootfs/recovery/oem/userdata are
# OMITTED — we boot from initramfs inside boot.img, so flashing this update.img
# writes only uboot+boot and leaves the rest of NAND untouched. That is the same
# selective flash the Windows RKDevTool flow did by checking only those rows.
#
# Board-independent proof: after packing, the script unpacks its OWN output
# (rkImageMaker -unpack + afptool -unpack) and verifies the expected partitions
# are present with matching sizes. No board needed to trust the pipeline.
#
# Usage:
#   scripts/assemble-update.sh [--out <dir>] [--no-verify]
# Prereq: pack-loader.sh + pack-fit.sh have populated $OUT_DIR.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

BRINGUP="${_PROJECT_ROOT}/third_party/bringup"
OUT_DIR="${BRINGUP}/out"
PACK="${_PROJECT_ROOT}/third_party/vendor-sdk/tools/linux/Linux_Pack_Firmware/rockdev"
VERIFY=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2;;
    --no-verify) VERIFY=0; shift;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

AFPTOOL="${PACK}/afptool"
RKIMGMAKER="${PACK}/rkImageMaker"
LOADER="${OUT_DIR}/MiniLoaderAll.bin"
UBOOT="${OUT_DIR}/uboot.img"
BOOT="${OUT_DIR}/boot.img"
PARAMETER="${BRINGUP}/parameter-nand-aes.txt"
PKGFILE="${BRINGUP}/package-file-aes.txt"
for f in "$AFPTOOL" "$RKIMGMAKER" "$LOADER" "$UBOOT" "$BOOT" "$PARAMETER" "$PKGFILE"; do
  [[ -r "$f" ]] || die "missing: $f (run pack-loader.sh + pack-fit.sh first)"
done

ROCKDEV=$(mktemp -d); VFY=""
trap 'rm -rf "$ROCKDEV" "$VFY"' EXIT
mkdir -p "$ROCKDEV/Image"
cp "$PKGFILE"   "$ROCKDEV/package-file"
cp "$LOADER"    "$ROCKDEV/Image/MiniLoaderAll.bin"
cp "$PARAMETER" "$ROCKDEV/Image/parameter.txt"
cp "$UBOOT"     "$ROCKDEV/Image/uboot.img"
cp "$BOOT"      "$ROCKDEV/Image/boot.img"

log_info "afptool -pack (RKAF container)…"
( cd "$ROCKDEV" && "$AFPTOOL" -pack ./ Image/update.raw.img >/dev/null 2>&1 )
[[ -f "$ROCKDEV/Image/update.raw.img" ]] || die "afptool produced no update.raw.img"

# Chip tag: hardcoded RK3506 (matches vendor rockdev/rk3506-mkupdate.sh).
log_info "rkImageMaker -RK3506 (RKFW header + loader)…"
"$RKIMGMAKER" -RK3506 "$LOADER" "$ROCKDEV/Image/update.raw.img" "$OUT_DIR/update.img" \
  -os_type:androidos >/dev/null 2>&1
[[ -f "$OUT_DIR/update.img" ]] || die "rkImageMaker produced no update.img"
log_ok "update.img → $OUT_DIR/update.img ($(stat -c%s "$OUT_DIR/update.img") B)"

# --- round-trip self-check (board-independent) ----------------------------
if [[ "$VERIFY" == 1 ]]; then
  log_info "round-trip self-check (unpack own output)…"
  VFY=$(mktemp -d)
  "$RKIMGMAKER" -unpack "$OUT_DIR/update.img" "$VFY" >/dev/null 2>&1 \
    || die "self-check FAIL: rkImageMaker -unpack"
  "$AFPTOOL" -unpack "$VFY/firmware.img" "$VFY" >/dev/null 2>&1 \
    || die "self-check FAIL: afptool -unpack"
  for part in parameter.txt uboot.img boot.img; do
    [[ -f "$VFY/$part" ]] || die "self-check FAIL: $part missing after unpack"
  done
  for pair in "uboot.img:$UBOOT" "boot.img:$BOOT"; do
    p=${pair%%:*}; src=${pair#*:}
    a=$(stat -c%s "$VFY/$p"); b=$(stat -c%s "$src")
    [[ "$a" == "$b" ]] || die "self-check FAIL: $p size $a != source $b"
  done
  log_ok "self-check OK: update.img round-trips to {parameter, uboot, boot} with matching sizes"
fi

log_info "flash from Linux:  rkdeveloptool db <loader>  ;  rkdeveloptool uf $OUT_DIR/update.img"
log_warn "rkdeveloptool SPI-NAND support on RK3506B = board-test pending (notes/09 §七)."
