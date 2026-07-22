# scripts/lib/rkbin.sh — resolve the rkbin blob tuple from ONE source, board-driven.
#
# pack-loader.sh (DDR/usbplug/SPL, +BL31 if present) and pack-fit.sh (tee) BOTH
# source this so the tuple is single-sourced and the SPL<->tee hash pair stays
# consistent. Source AFTER lib/env.sh (which sets FORGE_RKBIN_DIR + the board's
# RKBIN_* patterns from config/boards/<board>.env). Call rkbin_load, then use
# $RKBIN_DDR / $RKBIN_USBPLUG / $RKBIN_SPL / $RKBIN_TEE / $RKBIN_BL31 / $RKBIN_BLOB_DIR.
#
# Board tuple shapes:
#   aes  (RK3506B): {ddr, usbplug, spl, tee}         — NO BL31 (no ATF stage)
#   rk3568-atk    : {ddr, usbplug, spl, bl31(.elf), bl32/tee}  — has ATF BL31 stage
# Which patterns resolve is governed by RKBIN_*_PAT in the board config; RKBIN_BL31_PAT
# is OPTIONAL (unset → no BL31 resolution, RKBIN_BL31="").
#
# Cross-invocation note: pack-loader and pack-fit are separate processes — run BOTH
# with the same FORGE_RKBIN_DIR (the default public rkbin, the sole blob source).
# The forge orchestrator enforces this; do not pass --rkbin to only one of them.

# resolve the highest-version blob basename matching a pattern (version sort).
# optional 3rd arg = a grep -v exclusion (e.g. '_ta_' for tee trust-anchor vars).
rkbin_resolve() {  # <glob-pattern> <label> [exclude]
  local pat="$1" label="$2" exclude="${3:-}" hit
  if [[ -n "$exclude" ]]; then
    hit=$(ls "$RKBIN_BLOB_DIR"/$pat 2>/dev/null | grep -v "$exclude" | sort -V | tail -1)
  else
    hit=$(ls "$RKBIN_BLOB_DIR"/$pat 2>/dev/null | sort -V | tail -1)
  fi
  [[ -n "$hit" ]] || die "$label blob not found under $RKBIN_BLOB_DIR (pattern: $pat)"
  basename "$hit"
}

# resolve the full blob tuple from FORGE_RKBIN_DIR + the board's RKBIN_* patterns.
rkbin_load() {
  [[ -n "${FORGE_RKBIN_DIR:-}" ]] || die "FORGE_RKBIN_DIR unset (source lib/env.sh)"
  [[ -d "$FORGE_RKBIN_DIR" ]] || die "rkbin source not found: $FORGE_RKBIN_DIR (init submodule / fetch-deps)"
  [[ -n "${RKBIN_BLOB_SUBDIR:-}" ]] || die "RKBIN_BLOB_SUBDIR unset (set in config/boards/\${FORGE_BOARD}.env)"
  RKBIN_BLOB_DIR="${FORGE_RKBIN_DIR}/${RKBIN_BLOB_SUBDIR}"
  [[ -d "$RKBIN_BLOB_DIR" ]] || die "no ${RKBIN_BLOB_SUBDIR} under $FORGE_RKBIN_DIR ($RKBIN_BLOB_DIR)"
  RKBIN_DDR=$(rkbin_resolve     "${RKBIN_DDR_PAT}"     'DDR')
  RKBIN_USBPLUG=$(rkbin_resolve "${RKBIN_USBPLUG_PAT}" 'usbplug')
  RKBIN_SPL=$(rkbin_resolve     "${RKBIN_SPL_PAT}"     'SPL')
  RKBIN_TEE=$(rkbin_resolve     "${RKBIN_TEE_PAT}"     'tee' "${RKBIN_TEE_EXCLUDE:-}")
  # BL31 (ARM Trusted Firmware): only SoCs with an ATF stage (RK3568 yes, RK3506 no).
  # RKBIN_BL31_PAT unset → RKBIN_BL31="" (pack-loader skips the [BL31_OPTION] section).
  if [[ -n "${RKBIN_BL31_PAT:-}" ]]; then
    RKBIN_BL31=$(rkbin_resolve "${RKBIN_BL31_PAT}" 'BL31')
  else
    RKBIN_BL31=""
  fi
  export RKBIN_BLOB_DIR RKBIN_DDR RKBIN_USBPLUG RKBIN_SPL RKBIN_TEE RKBIN_BL31
}
