#!/usr/bin/env bash
# pack-emmc.sh — build the ext4 rootfs image (rootfs.ext4) for eMMC boards (rk3568).
#
# eMMC rootfs = ext4 (NOT UBIFS like aes/NAND, NOT a provisioning initramfs). The
# kernel mounts it directly per bootargs (root=/dev/mmcblk1pN). This script takes
# the staged rootfs tree ($OUT_DIR/rootfs, from stage-rootfs.sh extracting buildroot's
# rootfs.tar) and packs it into a fixed-size ext4 image with `mke2fs -d` — the same
# root-free, no-losetup/no-mount/no-sudo, structurally-reproducible approach as
# pack-sd.sh's rootfs.ext4 step (identical UUID/hash_seed so the two media share one
# ext4 recipe). Output → assemble-update.sh --emmc.
#
# Usage:
#   scripts/pack-emmc.sh [--out <dir>] [--rootfs-mib <N>]
# Inputs: $OUT_DIR/rootfs/ (from stage-rootfs). Output: $OUT_DIR/rootfs.ext4.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

ROOTFS_MIB=256          # ext4 rootfs image size (the eMMC partition must be ≥ this)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)        OUT_DIR="$2"; shift 2;;
    --rootfs-mib) ROOTFS_MIB="$2"; shift 2;;
    -h|--help) sed -n '2,16p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

need_tool() { command -v "$1" >/dev/null || die "missing host tool: $1 (apt: e2fsprogs)"; }
need_tool mke2fs

ROOT="${OUT_DIR}/rootfs"
[[ -d "$ROOT" ]] || die "missing staged rootfs tree: $ROOT (run \`forge pack\` first — stage-rootfs)"

mkdir -p "$OUT_DIR"
ROOTFS_EXT4="${OUT_DIR}/rootfs.ext4"
log_info "building ext4 rootfs (${ROOTFS_MIB} MiB) from $ROOT …"
# -F allow regular file (not a block dev); -b 4k default block; -d populates from the
# staged tree. Fixed UUID + hash_seed for structural reproducibility (the superblock
# write-time is host-dependent → NOT byte-identical across runs, same caveat as
# pack-sd.sh). Mirrors pack-sd.sh's mke2fs invocation verbatim so SD and eMMC share
# one ext4 rootfs recipe.
mke2fs -q -F -t ext4 -b 4096 -L rootfs \
  -U 11111111-2222-3333-4444-555555555555 \
  -E hash_seed=66666666-7777-8888-9999-aaaaaaaaaaaa \
  -d "$ROOT" "$ROOTFS_EXT4" "${ROOTFS_MIB}M" \
  || die "mke2fs rootfs.ext4 failed"
log_ok "rootfs.ext4 → $ROOTFS_EXT4 ($(stat -c%s "$ROOTFS_EXT4") B)"
log_info "next: scripts/forge.sh assemble --emmc"
