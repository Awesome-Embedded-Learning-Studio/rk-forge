#!/usr/bin/env bash
# forge — rk-forge build/pack orchestrator (single entrypoint).
#
# Runs the build/pack stages in the right order (the DAG), replacing the manual
# "run these N scripts in exactly this sequence" dance that was rk-forge's #1
# usability pain (an imx-forge carry-over with no orchestrator). Each pack/assemble
# stage skips when its inputs are unchanged (content-hash via lib/stage.sh —
# rk-forge's answer to RK-SDK build.sh rebuilding everything every time).
#
# Usage:
#   scripts/forge.sh setup      fetch source trees + WiFi driver + apply patch series
#   scripts/forge.sh build      build the kernel (build-linux) + print uboot/buildroot cmds
#   scripts/forge.sh pack       pack loader + FITs + stage/ubifs rootfs
#   scripts/forge.sh pack-sd    pack a bootable SD-card image (sd.img) — reuses the
#                               NAND pack outputs (idblock/uboot.img/boot.img/rootfs)
#                               then lays out GPT + ext4 rootfs. SD-1 manual boot.
#   scripts/forge.sh assemble [--provision|--nand|--rescue|--sd]   assemble update.img
#                                  (--sd = RKFW for the Rockchip SD tool; this board's
#                                   ROM boots SD only from an RK-tool card)
#   scripts/forge.sh all        setup -> build -> pack -> assemble (--provision)
#   scripts/forge.sh clean [--full]  rm -rf out/ (+ stage state); --full also
#                                  mrproper linux/uboot + clean buildroot (full rebuild)
#   scripts/forge.sh status     show which stages are up-to-date
#
#   --force   re-run stages even if inputs are unchanged (skip the skip).
#   --no-skip run every stage unconditionally (no content-hash skipping).
# Guard: ensure bash. The shebang handles the normal case; this catches an
# explicit `sh scripts/forge.sh` or any non-bash invocation (lib/*.sh rely on
# bash arrays + BASH_SOURCE). Re-exec ourselves under bash, preserving args.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # PROJECT_ROOT + all paths (config/forge.env)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/stage.sh"   # stage_up_to_date / stage_mark_done
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/host.sh"    # forge_warn_windows_path (WSL PATH detection)

STATE_DIR="${OUT_DIR}/.forge-stage"
FORCE=0; NO_SKIP=0; CLEAN_FULL=0; CMD=""

# --- argument parse (flags + one subcommand + its passthrough) ---------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)   FORCE=1; shift;;
    --no-skip) NO_SKIP=1; shift;;
    --full)    CLEAN_FULL=1; shift;;
    setup|build|pack|pack-sd|assemble|all|clean|status) CMD="$1"; shift; break;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1 (want a subcommand: setup|build|pack|pack-sd|assemble|all|clean|status)";;
  esac
done
[[ -n "$CMD" ]] || die "no subcommand (try: forge setup|build|pack|assemble|all|clean|status)"
ASSEMBLE_VARIANT="${1:---provision}"   # only meaningful for assemble/all

# --- run_stage: run a stage unless its inputs are unchanged ------------------
# run_stage <name> <input...> -- <cmd...>
run_stage() {
  local name="$1"; shift
  local -a inputs=()
  while [[ "$1" != "--" ]]; do inputs+=("$1"); shift; done
  shift  # consume --
  if [[ "$FORCE" == 0 && "$NO_SKIP" == 0 ]] && stage_up_to_date "$name" "$STATE_DIR" "${inputs[@]}"; then
    log_ok "$name: up-to-date (skip; --force to rerun)"
    return 0
  fi
  log_info "$name: running"
  "$@"
  stage_mark_done "$name" "$STATE_DIR" "${inputs[@]}"
  log_ok "$name: done"
}

# --- stages ------------------------------------------------------------------
stage_setup() {
  log_info "[setup] fetching source trees"
  bash "${_SCRIPT_DIR}/fetch-deps.sh" all
  log_info "[setup] fetching WiFi driver drop"
  bash "${_SCRIPT_DIR}/fetch-rtl8733bu-driver.sh"
  # apply the patch series into each tree, but only if it's still at the base
  # (unpatched). apply-series.sh commits via `git am`, so guard on HEAD==base.
  local linux_base uboot_base
  # pins ref may be an annotated tag (linux = v7.1). `git rev-parse <tag>` returns
  # the TAG-OBJECT sha, but HEAD after `git clone --branch <tag>` is the COMMIT sha
  # — the two never compare equal, so a bare rev-parse made this guard ALWAYS skip
  # apply on a clean clone → unpatched tree → "No rule to make target
  # rk3506b-aes.dtb" (issue #6: zImage builds fine since it needs no board DT).
  # Peel the tag to its commit with ^{commit} (no-op for the uboot commit-sha pin).
  # The awk filter also strips pins/* comments + blank lines (a bare $2 would collect
  # a multi-line blob and break rev-parse).
  linux_base=$(awk '!/^#/ && NF{print $2}' "${_PROJECT_ROOT}/pins/linux")
  uboot_base=$(awk '!/^#/ && NF{print $2}' "${_PROJECT_ROOT}/pins/uboot")
  if [[ "$(git -C "$LINUX_DIR" rev-parse HEAD)" == "$(git -C "$LINUX_DIR" rev-parse "${linux_base}^{commit}")" ]]; then
    log_info "[setup] applying linux patch series"
    ( cd "$LINUX_DIR" && bash "${_SCRIPT_DIR}/apply-series.sh" --component linux )
  else
    log_info "[setup] linux tree already patched ($(git -C "$LINUX_DIR" describe --tags 2>/dev/null || git -C "$LINUX_DIR" rev-parse --short HEAD)) — skip apply"
  fi
  if [[ "$(git -C "$UBOOT_DIR" rev-parse HEAD)" == "$(git -C "$UBOOT_DIR" rev-parse "${uboot_base}^{commit}")" ]]; then
    log_info "[setup] applying uboot patch series"
    ( cd "$UBOOT_DIR" && bash "${_SCRIPT_DIR}/apply-series.sh" --component uboot )
  else
    log_info "[setup] uboot tree already patched — skip apply"
  fi
  log_ok "setup complete"
}

stage_build() {
  forge_warn_windows_path
  log_info "[build] kernel (build-linux.sh — make is internally incremental)"
  bash "${_SCRIPT_DIR}/build-linux.sh"
  log_info "[build] U-Boot (build-uboot.sh — SOURCE_DATE_EPOCH → byte-reproducible)"
  bash "${_SCRIPT_DIR}/build-uboot.sh"
  log_info "[build] rootfs (build-rootfs.sh — buildroot + WSL clean PATH)"
  bash "${_SCRIPT_DIR}/build-rootfs.sh"
  log_ok "build complete (kernel + U-Boot + rootfs all automated)"
}

stage_pack() {
  mkdir -p "$OUT_DIR"
  run_stage pack-loader \
    "${BRINGUP}/RKBOOT-RK3506B-aes.ini" "${FORGE_RKBIN_DIR}/bin/rk35" \
    "${_SCRIPT_DIR}/pack-loader.sh" "${_SCRIPT_DIR}/lib/rkbin.sh" \
    -- bash "${_SCRIPT_DIR}/pack-loader.sh"
  run_stage pack-fit \
    "${BRINGUP}/fit/rk3506-mainline.its" "${BRINGUP}/fit/rk3506-kernel.its" \
    "${BRINGUP}/fit/rk3506-kernel-nand.its" "${LINUX_DIR}/arch/arm/boot/zImage" \
    "${LINUX_DIR}/arch/arm/boot/dts/rockchip/rk3506b-aes.dtb" \
    "${UBOOT_DIR}/u-boot-nodtb.bin" "${UBOOT_DIR}/u-boot.dtb" \
    "${_SCRIPT_DIR}/pack-fit.sh" \
    -- bash "${_SCRIPT_DIR}/pack-fit.sh"
  run_stage stage-rootfs \
    "${BUILDROOT}/output/images/rootfs.tar" \
    "${LINUX_DIR}/drivers/net/wireless/realtek/rtl8733bu/8733bu.ko" \
    "${_SCRIPT_DIR}/stage-rootfs.sh" \
    -- bash "${_SCRIPT_DIR}/stage-rootfs.sh"
  run_stage pack-ubifs \
    "${OUT_DIR}/rootfs" "${_SCRIPT_DIR}/pack-ubifs.sh" "${_PROJECT_ROOT}/config/forge.env" \
    -- bash "${_SCRIPT_DIR}/pack-ubifs.sh"
}

# SD-card image (parallel to NAND — second boot media, dev/recovery). Reuses the
# NAND pack outputs (idblock from pack-loader, uboot.img/boot.img from pack-fit,
# rootfs tree from stage-rootfs) — only the LAYOUT differs (GPT + ext4 rootfs,
# raw idblock/uboot/boot.img). Runs stage_pack first (each sub-stage skips if
# unchanged) so `forge pack-sd` is self-contained. See scripts/pack-sd.sh.
stage_pack_sd() {
  stage_pack
  mkdir -p "$OUT_DIR"
  # SD-2 autoboot: build the SD defconfig's uboot OUT-OF-TREE (does NOT touch the
  # NAND build artifacts in $UBOOT_DIR) and pack uboot-sd.img. The NAND uboot.img
  # + boot*.img come from stage_pack above; only the SD uboot FIT is added here.
  local sd_defcfg="${UBOOT_DIR}/configs/evb-rk3506_sd_defconfig"
  run_stage build-uboot-sd \
    "$sd_defcfg" "${_SCRIPT_DIR}/build-uboot.sh" \
    -- bash "${_SCRIPT_DIR}/build-uboot.sh" --variant sd
  run_stage pack-fit-sd \
    "${OUT_DIR}/u-boot-sd-nodtb.bin" "${OUT_DIR}/u-boot-sd.dtb" \
    "${BRINGUP}/fit/rk3506-mainline.its" "${_SCRIPT_DIR}/pack-fit.sh" \
    -- bash "${_SCRIPT_DIR}/pack-fit.sh" --variant sd
  run_stage pack-sd \
    "${OUT_DIR}/idblock.img" "${OUT_DIR}/uboot.img" "${OUT_DIR}/boot.img" \
    "${OUT_DIR}/rootfs" "${_SCRIPT_DIR}/pack-sd.sh" "${_PROJECT_ROOT}/config/forge.env" \
    -- bash "${_SCRIPT_DIR}/pack-sd.sh"
}

stage_assemble() {
  # --sd variant: RKFW for the Rockchip SD tool (board boots SD only from an
  # RK-tool card). Needs rootfs.ext4 from pack-sd → run the SD pack chain first,
  # then assemble with the SD parameter + ext4 rootfs. Distinct stage name so its
  # fingerprint doesn't collide with the NAND assemble.
  if [[ "$ASSEMBLE_VARIANT" == "--sd" ]]; then
    stage_pack_sd
    run_stage assemble-sd \
      "${OUT_DIR}/boot-sd.img" "${OUT_DIR}/rootfs.ext4" "${OUT_DIR}/uboot-sd.img" \
      "${OUT_DIR}/MiniLoaderAll.bin" "${BRINGUP}/parameter-sd-aes.txt" \
      "${BRINGUP}/package-file-sd.txt" "${_SCRIPT_DIR}/assemble-update.sh" \
      -- bash "${_SCRIPT_DIR}/assemble-update.sh" --sd
    return
  fi
  run_stage assemble \
    "${OUT_DIR}/boot.img" "${OUT_DIR}/rootfs.ubi.img" "${OUT_DIR}/uboot.img" \
    "${OUT_DIR}/MiniLoaderAll.bin" "${BRINGUP}/parameter-nand-aes.txt" \
    "${_SCRIPT_DIR}/assemble-update.sh" \
    -- bash "${_SCRIPT_DIR}/assemble-update.sh" "$ASSEMBLE_VARIANT"
}

stage_status() {
  for s in pack-loader pack-fit stage-rootfs pack-ubifs build-uboot-sd pack-fit-sd pack-sd assemble assemble-sd; do
    if [[ -f "${STATE_DIR}/${s}.fingerprint" ]]; then
      log_ok "$s: recorded"
    else
      log_info "$s: not run yet"
    fi
  done
}

# clean: remove out/ (pack artifacts + stage fingerprints). With --full, also
# mrproper the linux/uboot trees and clean buildroot — the basis for a full
# from-scratch rebuild (`forge all` afterwards recompiles kernel + U-Boot + rootfs).
stage_clean() {
  local full="${CLEAN_FULL:-0}"
  # --full may appear AFTER the subcommand (`forge clean --full`); the main arg
  # parser breaks on the subcommand, so re-parse it here. (`forge --full clean`
  # also works via the global CLEAN_FULL the main parser sets.)
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --full) full=1; shift;;
      *) shift;;
    esac
  done
  log_info "removing ${OUT_DIR} (pack artifacts + stage fingerprints)"
  rm -rf "$OUT_DIR"
  if [[ "$full" == 1 ]]; then
    # toolchain needed for mrproper (ARCH/CROSS_COMPILE); build scripts source it
    # themselves, but clean --full drives make directly here.
    # shellcheck disable=SC1091
    source "${_SCRIPT_DIR}/lib/toolchain.sh"
    check_toolchain || die "toolchain not on PATH (needed for mrproper). Run: source scripts/env-setup.sh"
    log_info "[--full] make mrproper linux + uboot + make clean buildroot"
    make -C "$LINUX_DIR"  ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" mrproper
    make -C "$UBOOT_DIR"  ARCH="$ARCH" CROSS_COMPILE="$CROSS_COMPILE" mrproper
    make -C "$BUILDROOT"  clean
    log_ok "source trees cleaned (full-rebuild basis)"
  fi
  log_ok "clean done (--full=$full)"
}

case "$CMD" in
  setup)    stage_setup ;;
  build)    stage_build ;;
  pack)     stage_pack ;;
  pack-sd)  stage_pack_sd ;;
  assemble) stage_assemble ;;
  all)      stage_setup; stage_build; stage_pack; ASSEMBLE_VARIANT="${ASSEMBLE_VARIANT}" stage_assemble
            log_ok "all done → ${OUT_DIR}/update.img" ;;
  clean)    stage_clean "$@" ;;
  status)   stage_status ;;
esac
