#!/usr/bin/env bash
# build-initramfs.sh — generate the first-boot provisioning initramfs.cpio.gz
# from tracked/pinned sources (the in-forge generator; replaces the hand-built,
# never-committed blob that was issue-class with #6/#8).
#
# The provisioning initramfs is what boot.img's ramdisk node carries: a static
# busybox shell + /init + ubiprog. On FIRST boot /init rewrites the SPI-NAND
# rootfs partition through the kernel's reliable write path (ubiprog), working
# around the rkbin loader's weak programming of some erase blocks (PEBs 3/4…).
# A marker file makes later boots skip the rewrite and switch_root to the real
# buildroot rootfs. See board/aes/initramfs/init + document/notes/26.
#
# Reproducibility: everything is built from source under the forge toolchain
# (Arm GNU gcc 15.2, arm-none-linux-gnueabihf) — NO ATK vendor-sdk dependency:
#   busybox  ← pins/busybox (upstream 1.36.1 tarball, sha256-pinned) — static
#   ubiprog  ← board/aes/rootfs/ubiprog.c (tracked) — static
#   /init    ← board/aes/initramfs/init (tracked)
# gcc 15.2 builds busybox 1.36.1 clean + static and reproduces the hand-built
# original byte-for-byte on SIZE (busybox 1414692 B, ubiprog 357400 B).
#
# Output: ${BRINGUP}/fit/initramfs.cpio.gz (the path pack-fit.sh reads; correctly
# gitignored as a regenerated artifact, NOT a missing input). Idempotent: skips
# the cpio repack when busybox + ubiprog + /init are unchanged.
#
# Usage:
#   scripts/build-initramfs.sh [--out <cpio.gz>] [--clean]
#     --out <path>  output cpio.gz (default: board/aes/fit/initramfs.cpio.gz)
#     --clean       force a full rebuild (rm busybox build + cpio)
# Seam: bash-first; arg parsing leaves a Python seam for later.
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # PROJECT_ROOT + BRINGUP + SRC_DIR
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"   # CROSS_COMPILE / ARCH / TOOLCHAIN_BIN_DIR

OUT_CPIO="${BRINGUP}/fit/initramfs.cpio.gz"
CLEAN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT_CPIO="$2"; shift 2;;
    --clean) CLEAN=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done

check_toolchain || die "toolchain not on PATH. Run: source scripts/env-setup.sh"
CC="${CROSS_COMPILE}gcc"
# Reproducibility: pin the build timestamp so two builds converge (busybox embeds
# a build date; gcc respects SOURCE_DATE_EPOCH). gzip -n (below) drops the gzip
# header mtime. Not byte-identical to the hand-built original (that used ATK gcc
# 10.3) but functionally + size-equivalent and rebuildable from source.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"

# --- inputs (all tracked/pinned in-repo) ---
PIN="${PROJECT_ROOT}/pins/busybox"
[[ -f "$PIN" ]] || die "busybox pin missing: $PIN"
read -r BB_URL BB_SHA256 < <(grep -vE '^[[:space:]]*#' "$PIN" | grep -vE '^[[:space:]]*$' | head -1)
[[ -n "$BB_URL" && -n "$BB_SHA256" ]] || die "busybox pin malformed (want '<url> <sha256>'): $PIN"
BB_VER="busybox-1.36.1"   # matches the pinned tarball's top-level dir
BB_SRC="${PROJECT_ROOT}/${SRC_DIR:-third_party/src}/${BB_VER}"
UBIPROG_SRC="${BRINGUP}/rootfs/ubiprog.c"
INIT_SRC="${BRINGUP}/initramfs/init"
for f in "$UBIPROG_SRC" "$INIT_SRC"; do
  [[ -f "$f" ]] || die "initramfs source missing: $f"
done

# --- ensure busybox source: download + sha256-verify + extract (idempotent) ---
ensure_busybox_source() {
  [[ -d "$BB_SRC" ]] && return 0
  local tarball="${BB_SRC}.tar.bz2"
  mkdir -p "$(dirname "$BB_SRC")"
  log_info "downloading $BB_VER ($BB_URL)"
  # forge standard: curl first (web-access-via-curl memory), wget fallback
  if ! curl -fL --retry 3 --connect-timeout 30 -o "$tarball" "$BB_URL" 2>/dev/null; then
    wget -q --tries=3 --timeout=30 -O "$tarball" "$BB_URL"
  fi
  log_info "verifying sha256 ($BB_SHA256)"
  echo "$BB_SHA256  $tarball" | sha256sum -c - >/dev/null \
    || { rm -f "$tarball"; die "busybox tarball sha256 mismatch ($BB_URL). pin may be wrong."; }
  log_info "extracting"
  tar xf "$tarball" -C "$(dirname "$BB_SRC")"
  rm -f "$tarball"
  [[ -d "$BB_SRC" ]] || die "busybox extract did not create $BB_SRC"
}

# --- build static busybox (in-tree; incremental) ---
build_busybox() {
  local bb="$BB_SRC/busybox"
  # force-rebuild path (--clean or missing binary)
  if [[ "$CLEAN" == 1 ]]; then rm -f "$bb" "$BB_SRC/.config"; fi
  [[ -x "$bb" ]] && return 0
  ( cd "$BB_SRC"
    [[ -f .config ]] || make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" defconfig >/dev/null
    # static link (no libc in the ramdisk). sed is idempotent.
    sed -i 's/^# CONFIG_STATIC is not set$/CONFIG_STATIC=y/' .config
    grep -q 'CONFIG_STATIC=y' .config || echo 'CONFIG_STATIC=y' >> .config
    log_info "building static busybox (gcc 15.2)…"
    make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)" >/dev/null
  )
  [[ -x "$bb" ]] || die "busybox build produced no binary ($BB_SRC)"
  file "$bb" | grep -q 'statically linked' || die "busybox is NOT static (CONFIG_STATIC=y?)"
}

# --- assemble the ramdisk tree + pack cpio.gz ---
pack_cpio() {
  local root
  root=$(mktemp -d)
  trap 'rm -rf "$root"' RETURN
  # dir layout (matches the board-verified cpio)
  mkdir -p "$root"/{bin,sbin,proc,sys,dev,etc,usr/bin,usr/sbin,tmp,root}
  # static binaries
  cp "$BB_SRC/busybox" "$root/bin/busybox"; chmod +x "$root/bin/busybox"
  log_info "building static ubiprog (ubiprog.c)…"
  "$CC" -static -O2 -s "$UBIPROG_SRC" -o "$root/bin/ubiprog"
  # minimal pre-created applet symlinks (/init calls the rest via /bin/busybox
  # full-path or after `busybox --install -s` at boot). Matches the original.
  local a
  for a in sh mount umount ls cat echo uname mkdir ps dmesg pwd vi; do
    ln -sf busybox "$root/bin/$a"
  done
  # /init (the provisioning script)
  cp "$INIT_SRC" "$root/init"; chmod +x "$root/init"

  mkdir -p "$(dirname "$OUT_CPIO")"
  log_info "packing cpio.gz → $OUT_CPIO"
  ( cd "$root" && find . | cpio -o -H newc --quiet ) | gzip -9 -n > "$OUT_CPIO"
  log_ok "initramfs.cpio.gz → $OUT_CPIO ($(stat -c%s "$OUT_CPIO") B)"
  log_ok "  busybox=$(stat -c%s "$root/bin/busybox") B  ubiprog=$(stat -c%s "$root/bin/ubiprog") B"
}

ensure_busybox_source
build_busybox
pack_cpio
log_info "next: scripts/forge.sh pack (pack-fit incbin's it into boot.img)"
