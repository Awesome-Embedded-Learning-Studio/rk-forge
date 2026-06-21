#!/usr/bin/env bash
# flash-sd.sh — write the forge SD-card image (sd.img) to a physical SD card.
#
# Pairs with pack-sd.sh (which builds sd.img). SD is the SECOND boot media
# (parallel to SPI-NAND) — a development/recovery path. See document/notes/30.
#
# Safety: this overwrites the ENTIRE target device. It requires an explicit
# --device, refuses any mounted device, refuses the system disk, shows the
# candidate removable devices, and asks for confirmation before writing. The
# blast radius of a wrong device is total data loss on that disk, so the checks
# here err on the side of refusing.
#
# WSL2: the SD card shows up as /dev/sdX once attached via usbipd-win (or a
# pass-through). doctor.sh detects WSL2; the device must be visible in `lsblk`.
#
# Usage:
#   scripts/flash-sd.sh --device /dev/sdX [--img <path>] [--yes]
#     --device <dev>  target block device (REQUIRED, e.g. /dev/sdc). Refuses
#                     partitions (/dev/sdc1) — give the whole-disk node.
#     --img <path>    image to write (default: $OUT_DIR/sd.img)
#     --yes           skip the confirmation prompt (CI / confident re-flash)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + OUT_DIR (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"

DEVICE=""; IMG="${OUT_DIR}/sd.img"; ASSUME_YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) DEVICE="$2"; shift 2;;
    --img)    IMG="$2"; shift 2;;
    --yes|-y) ASSUME_YES=1; shift;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

command -v lsblk >/dev/null || die "lsblk not found (util-linux)"
command -v dd     >/dev/null || die "dd not found"

# list candidate block devices to guide the user when --device is missing.
_list_devices() {
  echo "  removable/block devices (lsblk):"
  lsblk -dno NAME,SIZE,TYPE,TRAN,MODEL,RM 2>/dev/null | sed 's/^/    /' || true
  echo "  pass one as --device /dev/<NAME>"
}

if [[ -z "$DEVICE" ]]; then
  log_warn "--device is required. Candidate devices:"
  _list_devices
  die "re-run with --device /dev/sdX"
fi
[[ -f "$IMG" ]]    || die "image not found: $IMG (run \`forge pack-sd\` first)"

# --- validate the device -------------------------------------------------------
[[ -b "$DEVICE" ]] || die "$DEVICE is not a block device"
# refuse a partition node (sdX1, mmcblk0p1): writing a whole-disk image to a
# partition node corrupts the partition table of the parent. Require the
# whole-disk node.
case "$DEVICE" in
  */*"p"[0-9]|*[0-9]) die "$DEVICE looks like a PARTITION (trailing digit). Give the whole-disk node (e.g. /dev/sdc, /dev/mmcblk0).";;
esac

# refuse if the device or any of its partitions is mounted anywhere.
if lsblk -no MOUNTPOINT "$DEVICE" 2>/dev/null | grep -q .; then
  die "$DEVICE (or a partition) is mounted — unmount it first:\n  sudo umount $DEVICE*"
fi

# refuse the system disk: the device whose partition holds / or /boot. Best-
# effort heuristic (in WSL2 the root fs is on a virtio layer, but a stray
# /dev/sda that's the host C: pass-through must never be overwritten).
for sysdev in $(awk '$2=="/" || $2=="/boot" || $2=="/boot/efi" {print $1}' /proc/mounts 2>/dev/null); do
  base=$(lsblk -no PKNAME "$sysdev" 2>/dev/null | head -1)
  [[ -n "$base" ]] || base=$(basename "$sysdev" | sed -E 's/[0-9]+$//; s/p$//')
  if [[ "/dev/$base" == "$DEVICE" || "$sysdev" == "$DEVICE"* ]]; then
    die "$DEVICE looks like the SYSTEM disk (holds $sysdev). Refusing to overwrite."
  fi
done

# --- confirm -------------------------------------------------------------------
DEV_SIZE=$(lsblk -bndo SIZE "$DEVICE" 2>/dev/null || echo 0)
DEV_MODEL=$(lsblk -ndo MODEL "$DEVICE" 2>/dev/null | xargs)
DEV_TRAN=$(lsblk -ndo TRANS  "$DEVICE" 2>/dev/null | xargs)
IMG_SIZE=$(stat -c%s "$IMG")
log_info "image: $IMG ($(( IMG_SIZE / 1024 / 1024 )) MiB)"
log_info "target: $DEVICE — $(( DEV_SIZE / 1024 / 1024 )) MiB ${DEV_MODEL}${DEV_TRAN:+ [$DEV_TRAN]}"
if (( DEV_SIZE > 0 && IMG_SIZE > DEV_SIZE )); then
  die "image ($IMG_SIZE B) is LARGER than $DEVICE ($DEV_SIZE B) — wrong device or image"
fi
if [[ "$ASSUME_YES" != 1 ]]; then
  echo    "  This OVERWRITES $DEVICE entirely. All data on it will be lost."
  printf  "  Type the device name (%s) to confirm: " "$DEVICE"
  read -r reply
  [[ "$reply" == "$DEVICE" ]] || die "confirmation did not match — aborted"
fi

# --- write ---------------------------------------------------------------------
log_info "dd → $DEVICE (bs=4M conv=fsync) …"
sudo dd if="$IMG" of="$DEVICE" bs=4M conv=fsync status=progress
sync
log_ok "done — sd.img written to $DEVICE"
log_info "eject/reinsert the card, then boot (see notes/30 for the manual boot sequence)"
exit 0
