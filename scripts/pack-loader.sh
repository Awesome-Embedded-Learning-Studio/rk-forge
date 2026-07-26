#!/usr/bin/env bash
# pack-loader.sh — reproduce the RK3506B NAND loader (MiniLoaderAll.bin / idblock)
# from rkbin blobs via Rockchip's boot_merger.
#
# Loader stage of forge's NAND packaging (notes/09 §二①). The loader = DDR init +
# usbplug + SPL blobs, wrapped in RK idblock format by boot_merger. The blobs are a
# HARD closed dependency (document/blobs.md); boot_merger is a deterministic Rockchip packer.
#
# Blob source — the P1 conquest: the PUBLIC rockchip-linux/rkbin submodule
# (third_party/rkbin) is the sole source, giving a fully-public, internally-
# consistent loader (DDR v1.06 + usbplug v1.03 + SPL v1.12) that needs ZERO
# vendor-sdk. The SPL↔tee hash pair must stay consistent: the public SPL v1.12
# pairs with tee v2.40 (pack-fit.sh resolves tee from the same source). The
# sfc-dll-saga "tee v2.40 = Bad hash" was a MIXING artifact (ATK SPL v1.11
# checking public tee v2.40); a fully-public chain verifies against its own hash.
# Board-test confirms.
#
# Do NOT mix blob sources between pack-loader.sh and pack-fit.sh (inconsistent
# SPL↔tee hash → "optee Bad hash").
#
# HONEST EDGE: the loader here is a structurally-valid idblock but is NOT
# byte-identical to the ATK-shipped verified-good loader (rk3506-vendor-loader.bin,
# 270784 B): boot_merger embeds a build timestamp + emits a slightly different
# (~6KB) idblock layout than whatever built the shipped one. Board-boot of the
# public forge-reproduced loader is confirmed; the shipped loader remains the
# regression baseline.
#
# Usage:
#   scripts/pack-loader.sh [--rkbin <dir>] [--out <dir>]
#     --rkbin <dir>   blob source with bin/rk35/* (default: third_party/rkbin
#                     public submodule — the sole blob source)
#     --out <dir>     output dir (default: board/aes/out)
#
# Seam: bash-first; arg parsing leaves a Python seam (config-driven) for later.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR + FORGE_RKBIN_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/rkbin.sh"    # rkbin_load: resolve {ddr,usbplug,spl,tee} from FORGE_RKBIN_DIR

# boot_merger is version-tolerant → always from the PUBLIC rkbin submodule.
RKBIN_PUBLIC="${_PROJECT_ROOT}/third_party/rkbin"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rkbin) FORGE_RKBIN_DIR="$2"; shift 2;;
    --out)   OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

BOOT_MERGER="${RKBIN_PUBLIC}/tools/boot_merger"              # packer is version-tolerant; always public
INI_TPL="${BRINGUP}/${LOADER_INI}"

[[ -x "$BOOT_MERGER" ]]|| die "boot_merger not found/executable: $BOOT_MERGER (init third_party/rkbin submodule)"
[[ -f "$INI_TPL" ]]    || die "loader ini template not found: $INI_TPL"

# Resolve the blob tuple from FORGE_RKBIN_DIR via lib/rkbin.sh (shared with
# pack-fit.sh → SPL<->tee hash pair stays consistent by construction).
rkbin_load
BLOB_DIR="$RKBIN_BLOB_DIR"; DDR_BIN="$RKBIN_DDR"; USBPLUG_BIN="$RKBIN_USBPLUG"; SPL_BIN="$RKBIN_SPL"
log_info "loader blobs: ddr=$DDR_BIN  usbplug=$USBPLUG_BIN  spl=$SPL_BIN  (from $FORGE_RKBIN_DIR)"

mkdir -p "$OUT_DIR"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"
ln -s "$BLOB_DIR" "$WORK/${RKBIN_BLOB_SUBDIR}"

# Substitute the ini template (vendor mk-fitimage.sh convention: @TOKEN@ sed).
# @BL31_BIN@ is optional (RK3568 has an ATF BL31 stage; RK3506 has none — the token
# is absent from the aes ini, so the sub is a no-op there).
INI="$WORK/RKBOOT.ini"
sed -e "s~@DDR_BIN@~$DDR_BIN~" \
    -e "s~@USBPLUG_BIN@~$USBPLUG_BIN~" \
    -e "s~@SPL_BIN@~$SPL_BIN~" \
    -e "s~@BL31_BIN@~${RKBIN_BL31:-}~" \
    -e "s~@LOADER_OUT@~loader.bin~" \
    -e "s~@IDB_OUT@~idblock.img~" \
    "$INI_TPL" > "$INI"

log_info "boot_merger …"
( cd "$WORK" && "$BOOT_MERGER" "$INI" >/dev/null 2>&1 )
[[ -f "$WORK/loader.bin" ]] || die "boot_merger produced no loader.bin"

cp "$WORK/loader.bin" "$OUT_DIR/MiniLoaderAll.bin"
log_ok "loader → $OUT_DIR/MiniLoaderAll.bin ($(stat -c%s "$OUT_DIR/MiniLoaderAll.bin") B)"

# Also capture the standalone idblock.img (what the boot ROM reads at SD/eMMC
# sector 0x40). boot_merger emits it alongside loader.bin (ini CREATE_IDB=true +
# IDB_PATH). loader.bin/MiniLoaderAll = idblock + the download-protocol tail
# (rkdeveloptool/RKDevTool); the SD-card raw-write path (pack-sd.sh) wants the
# bare idblock. NAND assemble-update.sh doesn't use it → capturing is free, no
# impact on the NAND flow. If boot_merger didn't emit it, carve from loader.bin
# later in pack-sd.sh (the idblock is the leading segment).
if [[ -f "$WORK/idblock.img" ]]; then
  cp "$WORK/idblock.img" "$OUT_DIR/idblock.img"
  log_ok "idblock → $OUT_DIR/idblock.img ($(stat -c%s "$OUT_DIR/idblock.img") B, for SD/eMMC raw write)"
else
  log_warn "boot_merger produced no standalone idblock.img (pack-sd.sh will carve it from MiniLoaderAll.bin)"
fi
log_warn "NOT byte-identical to ATK-shipped loader (boot_merger metadata + idblock layout); board-boot unverified (notes/09 §五④, document/blobs.md)."
