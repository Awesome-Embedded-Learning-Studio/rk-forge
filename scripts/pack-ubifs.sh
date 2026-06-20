#!/usr/bin/env bash
# pack-ubifs.sh — pack out/rootfs into a flashable UBI image (out/rootfs.ubi.img).
#
# Two-step NAND rootfs packaging:
#   1. mkfs.ubifs  — rootfs tree → a single-volume UBIFS (rootfs.ubifs)
#   2. ubinize     — wrap that volume into a raw UBI image for one-shot
#                    programming of the whole rootfs MTD partition.
#
# W25N04KV SPI-NAND geometry (datasheet; the kernel spi-nand driver probes the
# same values at runtime):
#   page (min I/O) = 2048        W25N04KV: 2 KiB data page (+128 B OOB)
#   erase block    = 128 KiB     64 pages × 2 KiB
#   LEB            = 124 KiB     PEB − 2×min_io (EC + VID header, 1 page each)
#   rootfs partition = 0xae00000 174 MiB (DT partition@2740000)
#   -c (max LEB)   = 1400        < 1425 PEB in the partition; leaves ~25 PEB for
#                                UBI wear-leveling + bad-block reserve.
# vol_flags=autoresize: UBI grows the single rootfs volume to fill the partition.
#
# Boot side: DT chosen.bootargs sets ubi.mtd=5 root=ubi0:rootfs rootfstype=ubifs
# rootwait. (mtd5 = rootfs by DT fixed-partitions order: uboot0/misc1/vnvm2/
# recovery3/boot4/rootfs5/userdata6 — confirm on board with /proc/mtd.)
#
# Usage:
#   scripts/pack-ubifs.sh [--out <dir>]
# Prereq: $OUT_DIR/rootfs populated — by stage-rootfs.sh in the forge DAG
#        (buildroot rootfs.tar → out/rootfs); or scripts/mk-rootfs.sh for the
#        legacy static-busybox handcraft.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR + NAND_* geometry (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

ROOT="${OUT_DIR}/rootfs"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_DIR="$2"; ROOT="${OUT_DIR}/rootfs"; shift 2;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
command -v mkfs.ubifs >/dev/null || die "mkfs.ubifs missing (apt install mtd-utils)"
command -v ubinize    >/dev/null || die "ubinize missing (apt install mtd-utils)"
[[ -d "$ROOT" && -f "$ROOT/bin/busybox" ]] \
  || die "rootfs tree missing — run \`forge pack\` (stage-rootfs.sh builds it); or scripts/mk-rootfs.sh for the legacy handcraft"

UBIFS="${OUT_DIR}/rootfs.ubifs"
UBI="${OUT_DIR}/rootfs.ubi.img"

log_info "mkfs.ubifs  (min_io=${NAND_MIN_IO} leb=${NAND_LEB} max_leb=${NAND_MAX_LEB}, tree=$(du -sh "$ROOT" | cut -f1))…"
mkfs.ubifs -x none -m "$NAND_MIN_IO" -e "$NAND_LEB" -c "$NAND_MAX_LEB" -r "$ROOT" "$UBIFS" 2>&1 | sed 's/^/  /'

CFG=$(mktemp --suffix=.cfg)
trap 'rm -f "$CFG"' EXIT
cat > "$CFG" <<EOF
# ubinize volume descriptor for the rootfs (single volume, fills the partition).
[rootfs_vol]
mode=ubi
vol_id=0
vol_type=dynamic
vol_name=rootfs
vol_alignment=1
vol_flags=autoresize
image=${UBIFS}
EOF
log_info "ubinize  (peb=${NAND_PEB} → rootfs.ubi.img)…"
ubinize -m "$NAND_MIN_IO" -p "$NAND_PEB" "$CFG" -o "$UBI" 2>&1 | sed 's/^/  /'
[[ -f "$UBI" ]] || die "ubinize produced no image"
log_ok "rootfs.ubi.img → $UBI ($(numfmt --to=iec $(stat -c%s "$UBI")))"
log_info "flash this to the rootfs MTD partition (mtd5); see scripts output for board steps."
