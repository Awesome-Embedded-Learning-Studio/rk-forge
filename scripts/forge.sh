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
#   scripts/forge.sh setup      init rkbin submodule + fetch source trees + WiFi driver + apply patch series
#   scripts/forge.sh build      build the kernel (build-linux) + print uboot/buildroot cmds
#   scripts/forge.sh pack       generate initramfs + pack loader + FITs + stage/ubifs rootfs
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
#   --rootfs=buildroot|openwrt  rootfs/kernel profile (default: buildroot). The
#                               openwrt profile makes OpenWrt build the kernel+rootfs
#                               (musl, opkg/kmod); rk-forge still does the RK packing
#                               (uboot/loader/fit-pack/rkfw-pack). Flags may appear
#                               before OR after the subcommand.
#   --board=<id>                target board (default: aes). Selects config/boards/<id>.env
#                               (board constants: SOC/ARCH/DT_NAME/STORAGE/rkbin/toolchain).
#                               Registered: aes (RK3506B). Flags may appear before OR
#                               after the subcommand.
# Guard: ensure bash. The shebang handles the normal case; this catches an
# explicit `sh scripts/forge.sh` or any non-bash invocation (lib/*.sh rely on
# bash arrays + BASH_SOURCE). Re-exec ourselves under bash, preserving args.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -euo pipefail
_SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)

# Pre-scan --board <id> | --board=<id> BEFORE sourcing lib/env.sh (env.sh sources the
# active board's config/boards/<id>.env). FORGE_BOARD env var also honored; default aes.
# The main arg parser below re-handles --board (to consume it); this pre-scan only
# ensures FORGE_BOARD is set in time for env.sh.
export FORGE_BOARD="${FORGE_BOARD:-aes}"
_prev=""
for _a in "$@"; do
  [[ "$_prev" == "--board" ]] && FORGE_BOARD="$_a"
  case "$_a" in --board=*) FORGE_BOARD="${_a#--board=}";; esac
  _prev="$_a"
done
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/env.sh"     # PROJECT_ROOT + all paths + board config (FORGE_BOARD)
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/log.sh"
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/stage.sh"   # stage_up_to_date / stage_mark_done
# shellcheck disable=SC1091
source "${_SCRIPT_DIR}/lib/host.sh"    # forge_warn_windows_path (WSL PATH detection)

STATE_DIR="${OUT_DIR}/.forge-stage"
FORCE=0; NO_SKIP=0; CLEAN_FULL=0; CMD=""
export ROOTFS_PROFILE="${ROOTFS_PROFILE:-buildroot}"   # buildroot (default) | openwrt; exported so stage-rootfs.sh (subprocess) sees it

# --- argument parse (flags anywhere + one subcommand + its passthrough) ------
# Flags (--force/--no-skip/--full/--rootfs) may appear BEFORE or AFTER the
# subcommand (both `forge --rootfs=openwrt setup` and `forge setup --rootfs=openwrt`
# work). The first non-flag token is the subcommand; the rest are its passthrough
# (e.g. `assemble --nand`, `clean --full`).
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)   FORCE=1; shift;;
    --no-skip) NO_SKIP=1; shift;;
    --full)    CLEAN_FULL=1; shift;;
    --rootfs)  ROOTFS_PROFILE="$2"; shift 2;;
    --rootfs=*) ROOTFS_PROFILE="${1#--rootfs=}"; shift;;
    --board)   FORGE_BOARD="$2"; shift 2;;
    --board=*) FORGE_BOARD="${1#--board=}"; shift;;
    setup|build|pack|pack-sd|assemble|all|clean|status) CMD="$1"; shift; break;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) die "unknown arg: $1 (want a subcommand: setup|build|pack|pack-sd|assemble|all|clean|status)";;
  esac
done
[[ -n "$CMD" ]] || die "no subcommand (try: forge setup|build|pack|assemble|all|clean|status)"
# Re-scan args AFTER the subcommand for flags (--rootfs may follow it), then the
# first leftover non-flag is the assemble variant (--provision|--nand|--rescue|--sd).
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)   FORCE=1; shift;;
    --no-skip) NO_SKIP=1; shift;;
    --full)    CLEAN_FULL=1; shift;;
    --rootfs)  ROOTFS_PROFILE="$2"; shift 2;;
    --rootfs=*) ROOTFS_PROFILE="${1#--rootfs=}"; shift;;
    --board)   FORGE_BOARD="$2"; shift 2;;
    --board=*) FORGE_BOARD="${1#--board=}"; shift;;
    *) break;;   # first non-flag → leave for ASSEMBLE_VARIANT
  esac
done
# Validate ROOTFS_PROFILE AFTER both scans (flag may precede OR follow the subcommand).
[[ "$ROOTFS_PROFILE" == "buildroot" || "$ROOTFS_PROFILE" == "openwrt" ]] \
  || die "unknown --rootfs: $ROOTFS_PROFILE (want buildroot|openwrt)"
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
  # init git submodules FIRST. third_party/rkbin is the project's only submodule
  # (.gitmodules) but it's a HARD build dependency — the sole source of both
  # boot_merger (pack-loader.sh) AND the DDR/usbplug/SPL/tee blob tuple
  # (lib/rkbin.sh). A plain `git clone` (no --recursive) leaves the dir empty →
  # pack-loader dies "boot_merger not found (init third_party/rkbin submodule)"
  # (issue #8). fetch-deps.sh only covers the gitignored fetched-clones
  # (linux/uboot/buildroot/openwrt), NOT the submodule, so init it here explicitly.
  # Idempotent + fast; --init covers every registered submodule (rkbin today).
  log_info "[setup] init git submodules (third_party/rkbin — boot_merger + blob source)"
  git -C "$PROJECT_ROOT" submodule update --init

  # Fetch source trees per profile. The openwrt profile does NOT need the linux/
  # buildroot trees or the rtl8733bu driver drop — OpenWrt builds its own kernel
  # (its musl toolchain + quilt patches-7.1/) and wifi goes through OpenWrt's kmod
  # package system. It only needs uboot (rk-forge's mainline U-Boot) + openwrt.
  if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
    log_info "[setup] fetching source trees (openwrt profile: linux + uboot + openwrt)"
    # linux: fetched ONLY to git-archive v7.1 → dl/linux-7.1.tar.gz. czz8888's
    # kernel-headers download URL is broken (GitHub archive name is v7.1.tar.gz,
    # not linux-7.1.tar.gz — download.pl 404s). build-openwrt.sh regenerates the
    # tarball via `git archive v7.1 | gzip -n` (hash matches czz8888's). OpenWrt
    # then builds its OWN kernel from that tarball + quilt patches-7.1; rk-forge's
    # patched linux tree is NOT used by the openwrt profile.
    bash "${_SCRIPT_DIR}/fetch-deps.sh" linux
    bash "${_SCRIPT_DIR}/fetch-deps.sh" uboot
    bash "${_SCRIPT_DIR}/fetch-deps.sh" openwrt
  else
    log_info "[setup] fetching source trees (buildroot profile: linux + uboot + buildroot)"
    bash "${_SCRIPT_DIR}/fetch-deps.sh" all
    if [[ -n "${WIFI_DRIVER:-}" ]]; then
      log_info "[setup] fetching WiFi driver drop (${WIFI_DRIVER})"
      bash "${_SCRIPT_DIR}/fetch-${WIFI_DRIVER}-driver.sh"
    fi
  fi

  # apply the patch series into each tree, but only if it's still at the base
  # (unpatched). apply-series.sh commits via `git am`, so guard on HEAD==base.
  # pins ref may be an annotated tag (linux = v7.1). `git rev-parse <tag>` returns
  # the TAG-OBJECT sha, but HEAD after `git clone --branch <tag>` is the COMMIT sha
  # — peel the tag to its commit with ^{commit} (no-op for commit-sha pins like
  # uboot/openwrt). The awk filter strips pins/* comments + blank lines.
  local linux_base uboot_base openwrt_base
  linux_base=$(awk '!/^#/ && NF{print $2}' "${_PROJECT_ROOT}/pins/${FORGE_BOARD}/linux")
  uboot_base=$(awk '!/^#/ && NF{print $2}' "${_PROJECT_ROOT}/pins/${FORGE_BOARD}/uboot")
  openwrt_base=$(awk '!/^#/ && NF{print $2}' "${_PROJECT_ROOT}/pins/${FORGE_BOARD}/openwrt")

  if [[ "$ROOTFS_PROFILE" != "openwrt" ]]; then
    if [[ "$(git -C "$LINUX_DIR" rev-parse HEAD)" == "$(git -C "$LINUX_DIR" rev-parse "${linux_base}^{commit}")" ]]; then
      log_info "[setup] applying linux patch series"
      ( cd "$LINUX_DIR" && bash "${_SCRIPT_DIR}/apply-series.sh" --component linux )
    else
      log_info "[setup] linux tree already patched ($(git -C "$LINUX_DIR" describe --tags 2>/dev/null || git -C "$LINUX_DIR" rev-parse --short HEAD)) — skip apply"
    fi
  fi

  if [[ "$(git -C "$UBOOT_DIR" rev-parse HEAD)" == "$(git -C "$UBOOT_DIR" rev-parse "${uboot_base}^{commit}")" ]]; then
    log_info "[setup] applying uboot patch series"
    ( cd "$UBOOT_DIR" && bash "${_SCRIPT_DIR}/apply-series.sh" --component uboot )
  else
    log_info "[setup] uboot tree already patched — skip apply"
  fi

  # openwrt overlay: a SMALL rk-forge delta (Device/aes + config tweaks) applied
  # via git am. The KERNEL patches (0001-0016) are NOT applied here — OpenWrt's
  # quilt applies patches-7.1/ at build time. apply-series.sh is component-agnostic.
  if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
    if [[ "$(git -C "$OPENWRT_DIR" rev-parse HEAD)" == "$(git -C "$OPENWRT_DIR" rev-parse "${openwrt_base}^{commit}")" ]]; then
      log_info "[setup] applying openwrt overlay (Device/aes + config)"
      ( cd "$OPENWRT_DIR" && bash "${_SCRIPT_DIR}/apply-series.sh" --component openwrt )
    else
      log_info "[setup] openwrt tree already overlayed ($(git -C "$OPENWRT_DIR" rev-parse --short HEAD)) — skip apply"
    fi
  fi
  log_ok "setup complete (profile=$ROOTFS_PROFILE)"
}

stage_build() {
  forge_warn_windows_path
  if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
    # openwrt profile: OpenWrt builds the kernel (zImage+aes.dtb) AND the rootfs
    # (musl busybox+procd+kmod tree) in its own build_dir. Skip build-linux.sh —
    # OpenWrt's kernel feeds pack-fit.sh via KERNEL_ARTIFACT_DIR (set in
    # stage_pack). U-Boot is still rk-forge's mainline build (reused, board-verified).
    log_info "[build] OpenWrt kernel+rootfs (build-openwrt.sh — OpenWrt builds the kernel)"
    bash "${_SCRIPT_DIR}/build-openwrt.sh"
    log_info "[build] U-Boot (build-uboot.sh — rk-forge mainline, reused)"
    bash "${_SCRIPT_DIR}/build-uboot.sh"
  else
    log_info "[build] kernel (build-linux.sh — make is internally incremental)"
    bash "${_SCRIPT_DIR}/build-linux.sh"
    log_info "[build] U-Boot (build-uboot.sh — SOURCE_DATE_EPOCH → byte-reproducible)"
    bash "${_SCRIPT_DIR}/build-uboot.sh"
    log_info "[build] rootfs (build-rootfs.sh — buildroot + WSL clean PATH)"
    bash "${_SCRIPT_DIR}/build-rootfs.sh"
  fi
  log_ok "build complete (profile=$ROOTFS_PROFILE)"
}

stage_pack() {
  mkdir -p "$OUT_DIR"
  # openwrt profile: OpenWrt built the kernel in its build_dir — point
  # KERNEL_ARTIFACT_DIR there so pack-fit.sh reads OpenWrt's zImage+aes.dtb.
  # (buildroot profile leaves KERNEL_ARTIFACT_DIR at its default = LINUX_DIR.)
  if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
    export KERNEL_ARTIFACT_DIR="$(find "$OPENWRT_DIR/build_dir" -type d -name 'linux-7.*' -path '*linux-rockchip_rk3506*' 2>/dev/null | head -1)"
    [[ -n "$KERNEL_ARTIFACT_DIR" && -f "$KERNEL_ARTIFACT_DIR/arch/arm/boot/zImage" ]] \
      || die "OpenWrt kernel build dir not found under $OPENWRT_DIR/build_dir/linux-rockchip_rk3506 (run: forge build --rootfs=openwrt)"
    log_info "[pack] KERNEL_ARTIFACT_DIR=$KERNEL_ARTIFACT_DIR (OpenWrt kernel)"
  fi
  run_stage pack-loader \
    "${BRINGUP}/${LOADER_INI}" "${FORGE_RKBIN_DIR}/${RKBIN_BLOB_SUBDIR}" \
    "${_SCRIPT_DIR}/pack-loader.sh" "${_SCRIPT_DIR}/lib/rkbin.sh" \
    -- bash "${_SCRIPT_DIR}/pack-loader.sh"
  # stage-rootfs + pack-ubifs run BEFORE build-initramfs: the provisioning
  # initramfs embeds rootfs.ubi.img.gz (for from-source ubiprog), so it needs
  # rootfs.ubi.img packed first. stage-rootfs.sh branches on ROOTFS_PROFILE:
  # buildroot extracts rootfs.tar (+ 8733bu.ko); openwrt rsyncs TARGET_DIR
  # (kmod already in lib/modules/). The openwrt fingerprint input is the
  # .openwrt-built marker (touched by build-openwrt.sh) so a re-build re-stage.
  if [[ "$ROOTFS_PROFILE" == "openwrt" ]]; then
    run_stage stage-rootfs \
      "${OUT_DIR}/.openwrt-built" "${_SCRIPT_DIR}/stage-rootfs.sh" \
      -- bash "${_SCRIPT_DIR}/stage-rootfs.sh"
  else
    run_stage stage-rootfs \
      "${BUILDROOT}/output/images/rootfs.tar" \
      "${LINUX_DIR}/drivers/net/wireless/realtek/rtl8733bu/8733bu.ko" \
      "${_SCRIPT_DIR}/stage-rootfs.sh" \
      -- bash "${_SCRIPT_DIR}/stage-rootfs.sh"
  fi
  run_stage pack-ubifs \
    "${OUT_DIR}/rootfs" "${_SCRIPT_DIR}/pack-ubifs.sh" "${_PROJECT_ROOT}/config/forge.env" \
    "${_PROJECT_ROOT}/config/boards/${FORGE_BOARD}.env" \
    -- bash "${_SCRIPT_DIR}/pack-ubifs.sh"
  # build-initramfs AFTER pack-ubifs: the provisioning ramdisk now embeds
  # rootfs.ubi.img.gz so ubiprog can re-flash mtd5 from RAM on first boot
  # (from-source: kills cross-image residue + the loader's weak write). The
  # rootfs.ubi.img input re-triggers this stage when the rootfs changes.
  # Generated from tracked/pinned sources (busybox + ubiprog.c + /init) — the
  # in-forge generator that replaced the never-committed hand-built blob
  # (clean-clone blocker, issue #6/#8 class).
  run_stage build-initramfs \
    "${BRINGUP}/initramfs/init" "${BRINGUP}/rootfs/ubiprog.c" \
    "${_PROJECT_ROOT}/pins/busybox" "${OUT_DIR}/rootfs.ubi.img" \
    "${_SCRIPT_DIR}/build-initramfs.sh" \
    -- bash "${_SCRIPT_DIR}/build-initramfs.sh"
  # pack-fit reads zImage+aes.dtb from KERNEL_ARTIFACT_DIR (LINUX_DIR for buildroot,
  # OpenWrt's build_dir for openwrt) and incbin's initramfs.cpio.gz from
  # build-initramfs above. FIT templates + load addrs are rk-forge's board-verified
  # ones (NOT OpenWrt's 0x03200000/0x02000000 — those are for its uboot).
  run_stage pack-fit \
    "${BRINGUP}/fit/${SOC}-mainline.its" "${BRINGUP}/fit/${SOC}-kernel.its" \
    "${BRINGUP}/fit/${SOC}-kernel-nand.its" "${KERNEL_ARTIFACT_DIR}/arch/${ARCH}/boot/${KERN_IMG}" \
    "${KERNEL_ARTIFACT_DIR}/arch/${ARCH}/boot/dts/rockchip/${DT_NAME}.dtb" \
    "${UBOOT_DIR}/u-boot-nodtb.bin" "${UBOOT_DIR}/u-boot.dtb" \
    "${BRINGUP}/fit/initramfs.cpio.gz" \
    "${_SCRIPT_DIR}/pack-fit.sh" \
    -- bash "${_SCRIPT_DIR}/pack-fit.sh"
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
  local sd_defcfg="${UBOOT_DIR}/configs/${UBOOT_DEFCONFIG_SD}"
  run_stage build-uboot-sd \
    "$sd_defcfg" "${_SCRIPT_DIR}/build-uboot.sh" \
    -- bash "${_SCRIPT_DIR}/build-uboot.sh" --variant sd
  run_stage pack-fit-sd \
    "${OUT_DIR}/u-boot-sd-nodtb.bin" "${OUT_DIR}/u-boot-sd.dtb" \
    "${BRINGUP}/fit/${SOC}-mainline.its" "${_SCRIPT_DIR}/pack-fit.sh" \
    -- bash "${_SCRIPT_DIR}/pack-fit.sh" --variant sd
  run_stage pack-sd \
    "${OUT_DIR}/idblock.img" "${OUT_DIR}/uboot.img" "${OUT_DIR}/boot.img" \
    "${OUT_DIR}/rootfs" "${_SCRIPT_DIR}/pack-sd.sh" "${_PROJECT_ROOT}/config/forge.env" \
    "${_PROJECT_ROOT}/config/boards/${FORGE_BOARD}.env" \
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
      "${OUT_DIR}/MiniLoaderAll.bin" "${BRINGUP}/${PARAMETER_SD}" \
      "${BRINGUP}/${PKGFILE_SD}" "${_SCRIPT_DIR}/assemble-update.sh" \
      -- bash "${_SCRIPT_DIR}/assemble-update.sh" --sd
    return
  fi
  run_stage assemble \
    "${OUT_DIR}/boot.img" "${OUT_DIR}/rootfs.ubi.img" "${OUT_DIR}/uboot.img" \
    "${OUT_DIR}/MiniLoaderAll.bin" "${BRINGUP}/${PARAMETER_NAND}" \
    "${_SCRIPT_DIR}/assemble-update.sh" \
    -- bash "${_SCRIPT_DIR}/assemble-update.sh" "$ASSEMBLE_VARIANT"
}

stage_status() {
  for s in build-initramfs pack-loader pack-fit stage-rootfs pack-ubifs build-uboot-sd pack-fit-sd pack-sd assemble assemble-sd; do
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
