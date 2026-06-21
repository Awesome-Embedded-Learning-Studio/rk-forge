#!/usr/bin/env bash
# pack-sd.sh — build a bootable SD-card image (sd.img) for the RK3506B aes board.
#
# SD boot is the SECOND boot media (parallel to SPI-NAND, not a replacement) — a
# development/recovery path. This is the SD-1 milestone: a bootable image that
# reaches a busybox shell via a few hand-typed U-Boot lines (SD-2 = autoboot,
# a separate uboot defconfig, is the follow-up). See document/notes/30.
#
# == SD boot protocol (confirmed by the build config, not just the vendor log) ==
# BootROM reads the idblock at SD sector 0x40 (0x40) → DDR init + SPL.
# SPL loads the uboot FIT from sector 0x2000 — this is HARDCODED in the evb-rk3506
# defconfig: CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x2000. So uboot.img goes
# raw at sector 0x2000 (4 MiB). The same idblock + uboot.img as NAND — SD reuses
# them, only the LAYOUT differs.
# U-Boot then loads the kernel FIT (boot.img) via `mmc read` (RAW, no filesystem:
# the minimal defconfig has CONFIG_CMD_MMC but no ext4/FAT/load cmds — same raw
# philosophy as NAND's `mtd read`). The ext4 rootfs is a GPT partition mounted by
# the KERNEL (root=/dev/mmcblk0p1), so U-Boot needs no ext4 driver.
#
# == Layout (all offsets sector-512; clean MiB alignment where it matters) ==
#   sector   0-33      GPT primary
#   sector   64 (0x40) idblock            (raw; ~204 KiB, from pack-loader.sh)
#   sector   8192 (0x2000)  uboot.img FIT (raw; SPL loads here)
#   sector   16384 (0x4000) boot.img FIT  (raw; U-Boot mmc read loads it)
#   sector   65536 (0x10000) GPT p1 rootfs (ext4, from the staged buildroot tree)
#   [backup GPT at the image tail]
# The 32 MiB before p1 holds idblock + uboot + the kernel FIT (~19 MiB used) with
# headroom. p1 is a fixed-size ext4 (default 256 MiB); resize2fs on the card to
# grow into the full SD capacity.
#
# == Root-free + reproducible ==
# No losetup/mount (no sudo): each partition is a standalone ext4 built with
# `mke2fs -d` (populates from a dir), then dd'd into the image at its offset.
# sgdisk lays the GPT directly on the image file. Deterministic offsets; the ext4
# superblock write-time is host-dependent so sd.img is NOT byte-identical across
# runs (like buildroot) — structure/content is deterministic. See notes/30.
#
# Usage:
#   scripts/pack-sd.sh [--out <dir>] [--rootfs-mib <N>] [--size-mib <N>]
# Inputs: $OUT_DIR/{idblock.img,uboot.img,boot.img,rootfs/}  (from pack-loader,
#         pack-fit, stage-rootfs). Run `forge pack` (or the individual stages)
#         first. Output: $OUT_DIR/sd.img (+ rootfs.ext4 intermediate).
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

ROOTFS_MIB=256          # ext4 rootfs partition size (resize2fs on card to grow)
SIZE_MIB=0              # 0 = auto (32 MiB header + rootfs + 8 MiB GPT tail)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)        OUT_DIR="$2"; shift 2;;
    --rootfs-mib) ROOTFS_MIB="$2"; shift 2;;
    --size-mib)   SIZE_MIB="$2"; shift 2;;
    -h|--help) sed -n '2,46p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

# --- layout constants (sectors of 512 B; see header for the rationale) ---------
IDBLOCK_SECTOR=64
UBOOT_SECTOR=8192        # 0x2000 — CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR
BOOTIMG_SECTOR=16384     # 0x4000 — raw kernel FIT, mmc read by U-Boot
ROOTFS_SECTOR=65536      # 0x10000 — GPT p1, 32 MiB alignment, clears boot.img
HEADER_MIB=32            # region before p1 (idblock + uboot + boot.img slot)
TAIL_MIB=8               # backup GPT + alignment slack at the image tail
SECTOR=512

need_tool() { command -v "$1" >/dev/null || die "missing host tool: $1 (apt: gdisk e2fsprogs)"; }
need_tool mke2fs; need_tool sgdisk; need_tool dd; need_tool truncate

IDBLOCK="${OUT_DIR}/idblock.img"
UBOOT="${OUT_DIR}/uboot.img"
BOOT="${OUT_DIR}/boot.img"
ROOT="${OUT_DIR}/rootfs"
for f in "$IDBLOCK" "$UBOOT" "$BOOT"; do
  [[ -r "$f" ]] || die "missing: $f (run \`forge pack\` first — pack-loader + pack-fit)"
done
[[ -d "$ROOT" ]] || die "missing staged rootfs tree: $ROOT (run \`forge pack\` first — stage-rootfs)"

mkdir -p "$OUT_DIR"

# --- Step A: ext4 rootfs from the staged buildroot tree (mke2fs -d) -------------
ROOTFS_EXT4="${OUT_DIR}/rootfs.ext4"
log_info "building ext4 rootfs (${ROOTFS_MIB} MiB) from $ROOT …"
# -F allow regular file (not a block dev); -b 4k default block; -d populates.
# Fixed UUID + hash_seed for structural reproducibility (superblock write-time
# still varies → see header "NOT byte-identical").
mke2fs -q -F -t ext4 -b 4096 -L rootfs \
  -U 11111111-2222-3333-4444-555555555555 \
  -E hash_seed=66666666-7777-8888-9999-aaaaaaaaaaaa \
  -d "$ROOT" "$ROOTFS_EXT4" "${ROOTFS_MIB}M" \
  || die "mke2fs rootfs.ext4 failed"
log_ok "rootfs.ext4 → $ROOTFS_EXT4 ($(stat -c%s "$ROOTFS_EXT4") B)"

# --- Step B: assemble sd.img (GPT + raw blobs + rootfs partition) --------------
SD_IMG="${OUT_DIR}/sd.img"
TOTAL_MIB="$SIZE_MIB"
if [[ "$TOTAL_MIB" == 0 ]]; then
  TOTAL_MIB=$(( HEADER_MIB + ROOTFS_MIB + TAIL_MIB ))
fi
log_info "laying out sd.img (${TOTAL_MIB} MiB): GPT + raw blobs + rootfs p1 …"
rm -f "$SD_IMG"
truncate -s "${TOTAL_MIB}M" "$SD_IMG"

# GPT: one partition "rootfs" (ext4), start ROOTFS_SECTOR, size ROOTFS_MIB.
# 8300 = Linux filesystem type. idblock/uboot/boot.img live RAW before p1 (in the
# GPT "reserved" gap) — they are not partition entries.
sgdisk --zap-all "$SD_IMG" >/dev/null 2>&1 || die "sgdisk zap-all failed"
sgdisk --new=1:${ROOTFS_SECTOR}:+${ROOTFS_MIB}M \
       --change-name=1:rootfs \
       --typecode=1:8300 \
       "$SD_IMG" >/dev/null 2>&1 || die "sgdisk create partition failed"

# Raw-write the boot blobs at their fixed sector offsets (bs=1M seek = byte/1MiB
# for the MiB-aligned ones; bs=512 seek for the 32 KiB idblock).
dd if="$IDBLOCK" of="$SD_IMG" bs=$SECTOR seek=$IDBLOCK_SECTOR conv=notrunc status=none
dd if="$UBOOT"    of="$SD_IMG" bs=1M seek=$(( UBOOT_SECTOR * SECTOR / 1024 / 1024 )) conv=notrunc status=none
dd if="$BOOT"     of="$SD_IMG" bs=1M seek=$(( BOOTIMG_SECTOR * SECTOR / 1024 / 1024 )) conv=notrunc status=none
# rootfs.ext4 into p1 at the partition offset.
dd if="$ROOTFS_EXT4" of="$SD_IMG" bs=1M seek=$(( ROOTFS_SECTOR * SECTOR / 1024 / 1024 )) conv=notrunc status=none

# --- self-check (board-independent, no root needed) ----------------------------
log_info "self-check: partition table + blob offsets"
sgdisk -p "$SD_IMG" 2>/dev/null | sed -n '1,20p'
# verify each blob landed at its offset (read back the first sector, compare magic/size)
check_offset() {  # <file> <byte-offset> <label>
  local f="$1" off="$2" label="$3" got sz
  sz=$(stat -c%s "$f")
  got=$(dd if="$SD_IMG" bs=1 skip="$off" count="$sz" iflag=skip_bytes,count_bytes status=none | sha256sum | cut -c1-16)
  local want; want=$(sha256sum "$f" | cut -c1-16)
  [[ "$got" == "$want" ]] && log_ok "$label: ${sz} B @ byte $off verified" \
    || die "$label mismatch at byte $off (got $got want $want)"
}
check_offset "$IDBLOCK" $(( IDBLOCK_SECTOR * SECTOR ))  "idblock"
check_offset "$UBOOT"    $(( UBOOT_SECTOR  * SECTOR ))  "uboot.img"
check_offset "$BOOT"     $(( BOOTIMG_SECTOR * SECTOR )) "boot.img"

log_ok "sd.img → $SD_IMG ($(stat -c%s "$SD_IMG") B = $(( $(stat -c%s "$SD_IMG") / 1024 / 1024 )) MiB)"
cat <<EOF

  Boot sequence (SD-1, manual — see notes/30):
    1. dd sd.img to the SD card (scripts/flash-sd.sh --device /dev/sdX)
    2. insert + power on → SPL → U-Boot (2s countdown: press a key to stop)
    3. at the => prompt:
         => mmc dev 0
         => mmc read 0x04000000 0x4000 0x5000
         => setenv bootargs 'console=ttyS0,1500000 root=/dev/mmcblk0p1 rootwait rw'
         => bootm 0x04000000
    4. kernel boots → mounts ext4 rootfs → busybox shell
EOF
