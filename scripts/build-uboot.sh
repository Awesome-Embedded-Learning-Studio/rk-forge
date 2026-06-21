#!/usr/bin/env bash
# build-uboot.sh — build mainline U-Boot for the aes board (RK3506B).
#
# Replaces the exit-1 stub. Builds the artifacts pack-fit.sh consumes:
# u-boot-nodtb.bin + u-boot.dtb + tools/mkimage, from the aes board defconfig
# (evb-rk3506_defconfig, added by patches/uboot/0001) on the patched tree.
#
# Reproducibility: SOURCE_DATE_EPOCH is pinned to the tree's HEAD commit date so
# the build timestamp embedded in the U-Boot version string is deterministic →
# two builds from the same commit produce byte-identical binaries (U-Boot embeds
# "Mon DD YYYY - HH:MM:SS" otherwise, defeating byte-compare).
#
# binman: the full `make` also runs binman to build the COMBINED image
# (u-boot.bin / u-boot.itb), which needs the rkbin TPL/SPL blobs and fails with
# "Some images are invalid" (Error 103) without them. pack-fit uses the SEPARATE
# pieces (built before binman), so we tolerate the binman failure (the verified
# manual build did too).
#
# Usage:
#   scripts/build-uboot.sh [--clean] [--tree <dir>]
#     --clean   make mrproper first (clean rebuild; default keeps the build tree)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + UBOOT_DIR
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"

UBOOT_DIR_LOCAL="$UBOOT_DIR"; CLEAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean) CLEAN=1; shift;;
    --tree) UBOOT_DIR_LOCAL="$2"; shift 2;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
check_toolchain || die "toolchain not on PATH. Run: source scripts/env-setup.sh"
[[ -d "$UBOOT_DIR_LOCAL" ]] || die "U-Boot tree not found: $UBOOT_DIR_LOCAL"

# Reproducibility: pin the build timestamp to the HEAD commit date.
SDE="$(git -C "$UBOOT_DIR_LOCAL" log -1 --format=%ct HEAD)"
export SOURCE_DATE_EPOCH="$SDE"
log_info "SOURCE_DATE_EPOCH=$SDE ($(git -C "$UBOOT_DIR_LOCAL" log -1 --format=%ci HEAD))"

cd "$UBOOT_DIR_LOCAL"
if [[ "$CLEAN" == 1 ]]; then
  log_info "make mrproper (clean rebuild)"
  make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" mrproper
fi

log_info "make evb-rk3506_defconfig (the aes board config from patches/uboot/0001)"
make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" evb-rk3506_defconfig

log_info "make -j$(nproc) (binman combined-image failure tolerated; real dts/compile/link errors are FATAL)"
# `make all` builds the separate pieces pack-fit needs (u-boot-nodtb.bin,
# u-boot.dtb, tools/mkimage) AND runs binman for the combined image (u-boot.itb),
# which needs the rkbin rockchip-tpl blob → "Error 103 / missing external blobs".
# We never use that combined image (pack-loader builds the loader from rkbin
# blobs; pack-fit packs uboot.img from the separate pieces), so binman's failure
# is tolerated. (Building only the separate-piece targets was tried but
# `make tools/mkimage` hits a path-resolution error standalone; make all is the
# robust path.)
#
# *** DO NOT MASK REAL ERRORS *** The old version piped make through grep with
# `|| true` and then only checked `[[ -e u-boot.dtb ]]`. That PASSES on a STALE
# artifact left by a prior build, so a dts parse error (e.g. an undefined
# SRST_H_SDMMC reset symbol — reset header not included) was silently swallowed
# and u-boot.dtb stayed stale while this script reported success. The fix below
# captures the FULL make log and scans it for real error signatures (dtc/gcc/ld
# errors), excluding the known binman noise — a real failure now dies hard.
BINMAN_NOISE='BINMAN |simple-bin|rockchip-tpl|external blob|external TPL|faked external|images are invalid|Error 103|binman_stamp|/binman/|rockchip-linux/rkbin'
BUILD_LOG="$(mktemp)"
make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)" > "$BUILD_LOG" 2>&1 || true
# show progress minus the tolerated binman noise (so the console isn't flooded)
grep -vE "$BINMAN_NOISE" "$BUILD_LOG" || true

# Real-error gate: dtc (FATAL/Lexical/Syntax error), gcc (error:), or ld
# (undefined reference). These never appear in the tolerated binman noise, so a
# match here is a genuine build failure — die with the offending lines + keep
# the log for diagnosis.
REAL_ERRS="$(grep -E 'FATAL ERROR|Lexical error|Syntax error|error:|undefined reference' "$BUILD_LOG" \
  | grep -vE "$BINMAN_NOISE" || true)"
if [[ -n "$REAL_ERRS" ]]; then
  printf '%s\n' "$REAL_ERRS" >&2
  die "U-Boot build FAILED (real dts/compile/link error — NOT the tolerated binman failure). Full log: $BUILD_LOG"
fi
rm -f "$BUILD_LOG"

# verify the artifacts pack-fit needs
for f in u-boot-nodtb.bin u-boot.dtb tools/mkimage; do
  [[ -e "$f" ]] || die "expected artifact missing after build: $f"
done
log_ok "U-Boot built (SOURCE_DATE_EPOCH=$SDE):"
log_ok "  u-boot-nodtb.bin → $(stat -c%s u-boot-nodtb.bin) B  sha256=$(sha256sum u-boot-nodtb.bin | cut -c1-16)"
log_ok "  u-boot.dtb       → $(stat -c%s u-boot.dtb) B  sha256=$(sha256sum u-boot.dtb | cut -c1-16)"
log_ok "  tools/mkimage    → $(stat -c%s tools/mkimage) B  sha256=$(sha256sum tools/mkimage | cut -c1-16)"
log_info "version: $(strings u-boot-nodtb.bin | grep -m1 'U-Boot 2')"
log_info "next: scripts/forge.sh pack (pack-fit picks these up)"
