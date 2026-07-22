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
# Variants (the NAND and SD autoboot images are built from DIFFERENT defconfigs):
#   --variant nand  (default) — evb-rk3506_defconfig, mtd-read bootcmd (NAND boot)
#                   IN-TREE build in $UBOOT_DIR (pack-fit reads u-boot-nodtb.bin /
#                   u-boot.dtb / tools/mkimage there for the NAND uboot.img).
#   --variant sd              — evb-rk3506_sd_defconfig, mmc-read bootcmd (SD boot,
#                   SD-2 autoboot). Built IN-TREE in a THROWAWAY git worktree (a
#                   pristine working tree at the same HEAD — which already has the
#                   sd defconfig from patch 0005) so the SD build NEVER touches the
#                   NAND artifacts in $UBOOT_DIR. (An out-of-tree `make O=` was
#                   tried first but Kbuild refuses it when the source tree already
#                   has in-tree artifacts — "The source tree is not clean" — and we
#                   won't mrproper the NAND tree.) Output u-boot-sd-nodtb.bin +
#                   u-boot-sd.dtb are copied to $OUT_DIR for pack-fit --variant sd;
#                   tools/mkimage is shared with the NAND build.
#
# Usage:
#   scripts/build-uboot.sh [--clean] [--tree <dir>] [--variant nand|sd]
#     --clean   make mrproper first (nand); no-op for sd (the worktree is fresh)
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # _PROJECT_ROOT + UBOOT_DIR/OUT_DIR
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/toolchain.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/progress.sh"   # FORGE_PROGRESS_PY + forge_progress_run

UBOOT_DIR_LOCAL="$UBOOT_DIR"; CLEAN=0; VARIANT="nand"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean) CLEAN=1; shift;;
    --tree) UBOOT_DIR_LOCAL="$2"; shift 2;;
    --variant) VARIANT="$2"; shift 2;;
    -h|--help) sed -n '2,34p' "$0"; exit 0;;
    *) die "unknown arg: $1";;
  esac
done
[[ "$VARIANT" == "nand" || "$VARIANT" == "sd" ]] \
  || die "unknown variant: $VARIANT (want nand|sd)"
check_toolchain || die "toolchain not on PATH. Run: source scripts/env-setup.sh"
[[ -d "$UBOOT_DIR_LOCAL" ]] || die "U-Boot tree not found: $UBOOT_DIR_LOCAL"

# Variant config: defconfig + build dir (in-tree vs worktree) + output paths.
case "$VARIANT" in
  nand)
    DEFCONFIG="$UBOOT_DEFCONFIG"
    BUILD_DIR="$UBOOT_DIR_LOCAL"        # in-tree
    MKIMAGE="$UBOOT_DIR_LOCAL/tools/mkimage"
    ;;
  sd)
    DEFCONFIG="$UBOOT_DEFCONFIG_SD"
    MKIMAGE="$UBOOT_DIR_LOCAL/tools/mkimage"   # share the NAND-built host tool
    [[ -x "$MKIMAGE" ]] \
      || die "NAND tools/mkimage missing at $MKIMAGE — run build-uboot.sh (default nand) first"
    ;;
esac
log_info "variant=$VARIANT  defconfig=$DEFCONFIG"

# sd: create a throwaway git worktree at the same HEAD (has the sd defconfig from
# 0005) and build in-tree there — the NAND artifacts in $UBOOT_DIR stay untouched.
# WT is emptied for nand (the trap's worktree cleanup is a no-op then).
WT=""
if [[ "$VARIANT" == "sd" ]]; then
  WT=$(mktemp -d -t uboot-sd-wt-XXXXXX)
  BUILD_DIR="$WT"
  log_info "git worktree (isolated SD in-tree build): $WT"
  git -C "$UBOOT_DIR_LOCAL" worktree add --detach "$WT" HEAD
fi
BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"; if [[ -n "$WT" ]]; then git -C "$UBOOT_DIR_LOCAL" worktree remove "$WT" --force 2>/dev/null || rm -rf "$WT"; fi' EXIT

# Reproducibility: pin the build timestamp to the HEAD commit date (same HEAD for
# both variants — switching defconfig doesn't move the tree's HEAD).
SDE="$(git -C "$UBOOT_DIR_LOCAL" log -1 --format=%ct HEAD)"
export SOURCE_DATE_EPOCH="$SDE"
log_info "SOURCE_DATE_EPOCH=$SDE ($(git -C "$UBOOT_DIR_LOCAL" log -1 --format=%ci HEAD))"

# clean: nand = make mrproper (in-tree); sd = no-op (worktree is pristine each run)
if [[ "$CLEAN" == 1 ]]; then
  if [[ "$VARIANT" == "nand" ]]; then
    log_info "make mrproper (clean NAND rebuild)"
    ( cd "$UBOOT_DIR_LOCAL" && make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" mrproper )
  else
    log_info "--clean is a no-op for --variant sd (the worktree is fresh each run)"
  fi
fi

log_info "make $DEFCONFIG (in $BUILD_DIR)"
( cd "$BUILD_DIR" && make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" "$DEFCONFIG" )

log_info "make -j$(nproc) (binman combined-image failure tolerated; real dts/compile/link errors are FATAL)"
# `make all` builds the separate pieces pack-fit needs (u-boot-nodtb.bin,
# u-boot.dtb, tools/mkimage) AND runs binman for the combined image (u-boot.itb),
# which needs the rkbin rockchip-tpl blob → "Error 103 / missing external blobs".
# We never use that combined image (pack-loader builds the loader from rkbin
# blobs; pack-fit packs uboot.img from the separate pieces), so binman's failure
# is tolerated.
#
# *** DO NOT MASK REAL ERRORS *** capture the FULL make log and scan it for real
# error signatures (dtc/gcc/ld), excluding the known binman noise — a real
# failure dies hard. (The old version piped through grep + `|| true` + only
# checked `[[ -e u-boot.dtb ]]`, which PASSED on a stale artifact — silently
# swallowing a dts parse error. See git history.)
BINMAN_NOISE='BINMAN |simple-bin|rockchip-tpl|ROCKCHIP_TPL=|binary and build with|One possible source|Required binary blob|See the documentation|external blob|external TPL|faked external|images are invalid|Error 103|binman_stamp|/binman/|rockchip-linux/rkbin|ddr\.bin'
UB_MAKE=( make ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" -j"$(nproc)" )
if [[ -t 1 ]] && [[ "${FORGE_PROGRESS:-1}" == "1" ]] && [[ -f "$FORGE_PROGRESS_PY" ]] && command -v python3 >/dev/null 2>&1; then
  # TTY + progress: bar over the make output (kernel parser — U-Boot is kbuild),
  # tee to BUILD_LOG so the real-error gate below still has the full log.
  # BINMAN_NOISE → --ignore-errors so the tolerated binman failures (the whole
  # blob-missing block: Error 103 / images are invalid / Required binary blob /
  # ROCKCHIP_TPL= / "binary and build with" / "One possible source" / ddr.bin)
  # neither triggers a false error dump nor shows on the live raw line.
  printf '[INFO] counting build units (make -n)…\n' >&2
  # `{ make -k -n || true; }` — -k keeps the dry-run enumerating past sub-make
  # errors (else it truncates → undercount); || true swallows the non-zero exit
  # so pipefail doesn't zero the total (same as lib/progress.sh's pre-scan).
  # buildmeter --count-only stderr is NOT silenced — on a TTY it shows the
  # pre-scan spinner; it only writes stderr on a TTY (CI unaffected). The
  # make-side ( ... ) 2>/dev/null still swallows make -n noise.
  UB_TOTAL=$( { ( cd "$BUILD_DIR" && "${UB_MAKE[@]}" -k -n ) 2>/dev/null || true; } \
    | python3 "$FORGE_PROGRESS_PY" --count-only kernel || true )
  UB_BUF=""
  command -v stdbuf >/dev/null 2>&1 && UB_BUF="stdbuf -oL"
  if [[ "$UB_TOTAL" -gt 0 ]] 2>/dev/null; then
    ( cd "$BUILD_DIR" && $UB_BUF "${UB_MAKE[@]}" ) 2>&1 | tee "$BUILD_LOG" \
      | python3 "$FORGE_PROGRESS_PY" kernel --total "$UB_TOTAL" --log "$BUILD_LOG" \
        --ignore-errors "$BINMAN_NOISE" || true
  else
    ( cd "$BUILD_DIR" && $UB_BUF "${UB_MAKE[@]}" ) 2>&1 | tee "$BUILD_LOG" \
      | python3 "$FORGE_PROGRESS_PY" kernel --log "$BUILD_LOG" \
        --ignore-errors "$BINMAN_NOISE" || true
  fi
else
  # non-TTY / disabled: capture to log + show non-noise (original flow)
  ( cd "$BUILD_DIR" && "${UB_MAKE[@]}" ) > "$BUILD_LOG" 2>&1 || true
  grep -vE "$BINMAN_NOISE" "$BUILD_LOG" || true
fi

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

# verify the artifacts pack-fit needs (nand: in-tree; sd: in the worktree)
ART_NODTB="$BUILD_DIR/u-boot-nodtb.bin"
ART_DTB="$BUILD_DIR/u-boot.dtb"
for f in "$ART_NODTB" "$ART_DTB" "$MKIMAGE"; do
  [[ -e "$f" ]] || die "expected artifact missing after build: $f"
done

# SD variant: copy the separate pieces to $OUT_DIR for pack-fit --variant sd.
# (tools/mkimage is NOT copied — pack-fit uses the one in $UBOOT_DIR, shared with
#  the NAND build; the SD defconfig differs from NAND only in bootcmd.)
if [[ "$VARIANT" == "sd" ]]; then
  mkdir -p "$OUT_DIR"
  cp "$ART_NODTB" "$OUT_DIR/u-boot-sd-nodtb.bin"
  cp "$ART_DTB"   "$OUT_DIR/u-boot-sd.dtb"
  log_ok "U-Boot (SD) built → $OUT_DIR/u-boot-sd-nodtb.bin + u-boot-sd.dtb"
  log_ok "  u-boot-sd-nodtb.bin → $(stat -c%s "$OUT_DIR/u-boot-sd-nodtb.bin") B  sha256=$(sha256sum "$OUT_DIR/u-boot-sd-nodtb.bin" | cut -c1-16)"
  log_ok "  u-boot-sd.dtb       → $(stat -c%s "$OUT_DIR/u-boot-sd.dtb") B  sha256=$(sha256sum "$OUT_DIR/u-boot-sd.dtb" | cut -c1-16)"
  log_info "version: $(strings "$OUT_DIR/u-boot-sd-nodtb.bin" | grep -m1 'U-Boot 2')"
  log_info "next: scripts/forge.sh assemble --sd (pack-fit --variant sd picks these up)"
else
  log_ok "U-Boot built (SOURCE_DATE_EPOCH=$SDE):"
  log_ok "  u-boot-nodtb.bin → $(stat -c%s "$ART_NODTB") B  sha256=$(sha256sum "$ART_NODTB" | cut -c1-16)"
  log_ok "  u-boot.dtb       → $(stat -c%s "$ART_DTB") B  sha256=$(sha256sum "$ART_DTB" | cut -c1-16)"
  log_ok "  tools/mkimage    → $(stat -c%s "$MKIMAGE") B  sha256=$(sha256sum "$MKIMAGE" | cut -c1-16)"
  log_info "version: $(strings "$ART_NODTB" | grep -m1 'U-Boot 2')"
  log_info "next: scripts/forge.sh pack (pack-fit picks these up)"
fi
