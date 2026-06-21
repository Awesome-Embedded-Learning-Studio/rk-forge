#!/usr/bin/env bash
# post-build.sh — buildroot post-build hook for rk3506_aes: compile the SFC/NAND
# forensics tools (mtdrawdump + mtdbb) into the target rootfs.
#
# buildroot's minimal rootfs doesn't ship these — the handcraft mk-rootfs.sh
# does (scripts/mk-rootfs.sh:84-108). They are the SFC/NAND write-path forensics
# mainstays (raw-dump + bad-block management), so rebuild them here with the SAME
# flags as mk-rootfs.sh: -O2 -static -s. Statically linked so they run regardless
# of the dynamic glibc runtime the buildroot rootfs otherwise uses.
#
# buildroot invokes:  $BR2_ROOTFS_POST_BUILD_SCRIPT  <TARGET_DIR>
# buildroot exports HOST_DIR / TARGET_DIR / STAGING_DIR etc., but NOT TARGET_CC,
# so we resolve the cross gcc via the host toolchain wrapper under $HOST_DIR/bin
# (points at the /opt Arm GNU 15.2 toolchain, same one mk-rootfs.sh uses). The
# external-tree path is $BR2_EXTERNAL_rkforge_PATH — buildroot keeps the
# external.desc name's case verbatim (name: rkforge → lowercase rkforge), so it
# is NOT BR2_EXTERNAL_RKFORGE_PATH.
set -euo pipefail

TARGET_DIR="${1:?usage: post-build.sh <TARGET_DIR>}"
: "${HOST_DIR:?buildroot must export HOST_DIR}"
: "${BR2_EXTERNAL_rkforge_PATH:?buildroot must export BR2_EXTERNAL_rkforge_PATH}"

# Cross gcc = buildroot's host toolchain wrapper. "*-gcc" matches the prefixed
# target wrapper (arm-none-linux-gnueabihf-gcc) and not the bare host gcc.
GCC="$(set -- "${HOST_DIR}"/bin/*-gcc; echo "$1")"
[[ -x "$GCC" ]] || { echo "post-build: no target gcc wrapper under ${HOST_DIR}/bin/*-gcc" >&2; exit 1; }

# Sources live in the sibling rootfs/ dir (bringup/rootfs/*.c) — one level
# above this BR2_EXTERNAL tree.
SRC_DIR="${BR2_EXTERNAL_rkforge_PATH}/../rootfs"
DEST="${TARGET_DIR}/usr/bin"
mkdir -p "$DEST"

build_static() {
  local src="$1" name="$2"
  [[ -f "$src" ]] || { echo "post-build: missing source $src" >&2; exit 1; }
  "$GCC" -O2 -static -s -o "$DEST/$name" "$src"
  chmod 0755 "$DEST/$name"
  echo "post-build: $name → $DEST/$name ($(stat -c%s "$DEST/$name") B, static armhf)"
}

build_static "$SRC_DIR/mtdrawdump.c" mtdrawdump
build_static "$SRC_DIR/mtdbb.c"      mtdbb
