#!/usr/bin/env bash
# pack-loader.sh — reproduce the RK3506B NAND loader (MiniLoaderAll.bin / idblock)
# from rkbin blobs via Rockchip's boot_merger.
#
# Loader stage of forge's NAND packaging (notes/09 §二①). The loader = DDR init +
# usbplug + SPL blobs, wrapped in RK idblock format by boot_merger. The blobs are a
# HARD closed dependency (BLOBS.md); boot_merger is a deterministic Rockchip packer.
#
# Blob source — the P1 conquest: defaults to the PUBLIC rockchip-linux/rkbin
# submodule (third_party/rkbin), giving a fully-public, internally-consistent
# loader (DDR v1.06 + usbplug v1.03 + SPL v1.12) that needs ZERO vendor-sdk. The
# SPL↔tee hash pair must stay consistent: the public SPL v1.12 pairs with tee v2.40
# (pack-fit.sh resolves tee from the same source). The sfc-dll-saga "tee v2.40 =
# Bad hash" was a MIXING artifact (ATK SPL v1.11 checking public tee v2.40); a
# fully-public chain verifies against its own hash. Board-test is the confirmation.
#
# ATK fallback: override FORGE_RKBIN_DIR (or --rkbin) to third_party/rkbin-atk
# (gitignored, populated by scripts/fetch-deps.sh atk-blobs) to rebuild the
# ATK-verified loader (v1.06 / v1.02 / v1.11 + tee v2.10) — the regression baseline
# kept until the public loader is board-verified. Do NOT mix blob sources between
# pack-loader.sh and pack-fit.sh (inconsistent SPL↔tee hash → "optee Bad hash").
#
# HONEST EDGE: the loader here is a structurally-valid idblock but is NOT
# byte-identical to the ATK-shipped verified-good loader (rk3506-vendor-loader.bin,
# 270784 B): boot_merger embeds a build timestamp + emits a slightly different
# (~6KB) idblock layout than whatever built the shipped one. Bootability is
# board-test pending (notes/09 §五④, BLOBS.md) for BOTH the public and ATK variants.
#
# Usage:
#   scripts/pack-loader.sh [--rkbin <dir>] [--out <dir>]
#     --rkbin <dir>   blob source with bin/rk35/* (default: third_party/rkbin
#                     public submodule; pass third_party/rkbin-atk for ATK fallback)
#     --out <dir>     output dir (default: third_party/bringup/out)
#
# Seam: bash-first; arg parsing leaves a Python seam (config-driven) for later.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR + FORGE_RKBIN_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

# boot_merger is version-tolerant → always from the PUBLIC rkbin, independent of
# which blob source FORGE_RKBIN_DIR points at (public vs rkbin-atk).
RKBIN_PUBLIC="${_PROJECT_ROOT}/third_party/rkbin"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rkbin) FORGE_RKBIN_DIR="$2"; shift 2;;
    --out)   OUT_DIR="$2"; shift 2;;
    -h|--help) sed -n '2,28p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

BLOB_DIR="${FORGE_RKBIN_DIR}/bin/rk35"
BOOT_MERGER="${RKBIN_PUBLIC}/tools/boot_merger"              # packer is version-tolerant; always public
INI_TPL="${_PROJECT_ROOT}/third_party/bringup/RKBOOT-RK3506B-aes.ini"

[[ -d "$BLOB_DIR" ]]   || die "rkbin blob dir not found: $BLOB_DIR (init submodule? scripts/fetch-deps.sh atk-blobs?)"
[[ -x "$BOOT_MERGER" ]]|| die "boot_merger not found/executable: $BOOT_MERGER (init third_party/rkbin submodule)"
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
log_info "loader blobs: ddr=$DDR_BIN  usbplug=$USBPLUG_BIN  spl=$SPL_BIN  (from $FORGE_RKBIN_DIR)"

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
