#!/usr/bin/env bash
# pack-loader.sh — reproduce the RK3506B NAND loader (MiniLoaderAll.bin / idblock)
# from pinned rkbin blobs via Rockchip's boot_merger.
#
# Loader stage of forge's NAND packaging (notes/09 §二①). The loader = DDR init +
# usbplug + vendor SPL blobs, wrapped in RK idblock format by boot_merger. The
# blobs are a HARD closed dependency (BLOBS.md); boot_merger is a deterministic
# Rockchip packer (not a blob).
#
# HONEST EDGE: the loader here is a structurally-valid idblock but is NOT
# byte-identical to the ATK-shipped verified-good loader (rk3506-vendor-loader.bin,
# 270784 B): boot_merger embeds a build timestamp, and the pinned rkbin's
# boot_merger 1.35 emits a slightly different (~6KB) idblock layout than whatever
# built the shipped one. Same blob family (v1.06 / v1.02 / v1.11); bootability is
# board-test pending (notes/09 §五④).
#
# Usage:
#   scripts/pack-loader.sh [--rkbin <dir>] [--out <dir>]
#     --rkbin <dir>   rkbin tree with bin/rk35/* + tools/boot_merger
#                     (default: third_party/vendor-sdk/rkbin — has the ATK-verified
#                      v1.02/v1.11 blobs; explore/rkbin has newer v1.03/v1.12)
#     --out <dir>     output dir (default: third_party/bringup/out)
#
# Seam: bash-first; arg parsing leaves a Python seam (config-driven) for later.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_PROJECT_ROOT=$(cd "${_SCRIPT_DIR}/.." && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

RKBIN_DIR="${_PROJECT_ROOT}/third_party/vendor-sdk/rkbin"
OUT_DIR="${_PROJECT_ROOT}/third_party/bringup/out"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rkbin) RKBIN_DIR="$2"; shift 2;;
    --out)   OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

BLOB_DIR="${RKBIN_DIR}/bin/rk35"
BOOT_MERGER="${RKBIN_DIR}/tools/boot_merger"
INI_TPL="${_PROJECT_ROOT}/third_party/bringup/RKBOOT-RK3506B-aes.ini"

[[ -d "$BLOB_DIR" ]]   || die "rkbin blob dir not found: $BLOB_DIR"
[[ -x "$BOOT_MERGER" ]]|| die "boot_merger not found/executable: $BOOT_MERGER"
[[ -f "$INI_TPL" ]]    || die "loader ini template not found: $INI_TPL"

# Resolve blob versions by glob — version-agnostic across rkbin trees. Picks the
# highest version present (sort | tail -1).
resolve_blob() {  # <glob-suffix-pattern> <label>
  local pat="$1" label="$2" hit
  hit=$(ls "$BLOB_DIR"/$pat 2>/dev/null | sort | tail -1)
  [[ -n "$hit" ]] || die "$label blob not found under $BLOB_DIR (pattern: $pat)"
  basename "$hit"
}
DDR_BIN=$(resolve_blob  'rk3506b_ddr_750MHz_v1.*.bin' 'DDR')      # skips the _rt_ variant
USBPLUG_BIN=$(resolve_blob 'rk3506_usbplug_v1.*.bin' 'usbplug')
SPL_BIN=$(resolve_blob    'rk3506_spl_v1.*.bin'       'SPL')
log_info "loader blobs: ddr=$DDR_BIN  usbplug=$USBPLUG_BIN  spl=$SPL_BIN  (from $RKBIN_DIR)"

mkdir -p "$OUT_DIR"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"
ln -s "$BLOB_DIR" "$WORK/bin/rk35"

# Substitute the ini template (vendor mk-fitimage.sh convention: @TOKEN@ sed).
INI="$WORK/RKBOOT.ini"
sed -e "s~@DDR_BIN@~$DDR_BIN~" \
    -e "s~@USBPLUG_BIN@~$USBPLUG_BIN~" \
    -e "s~@SPL_BIN@~$SPL_BIN~" \
    -e "s~@LOADER_OUT@~loader.bin~" \
    -e "s~@IDB_OUT@~idblock.img~" \
    "$INI_TPL" > "$INI"

log_info "boot_merger …"
( cd "$WORK" && "$BOOT_MERGER" "$INI" >/dev/null 2>&1 )
[[ -f "$WORK/loader.bin" ]] || die "boot_merger produced no loader.bin"

cp "$WORK/loader.bin" "$OUT_DIR/MiniLoaderAll.bin"
log_ok "loader → $OUT_DIR/MiniLoaderAll.bin ($(stat -c%s "$OUT_DIR/MiniLoaderAll.bin") B)"
log_warn "NOT byte-identical to ATK-shipped loader (boot_merger metadata + idblock layout); board-boot unverified (notes/09 §五④, BLOBS.md)."
