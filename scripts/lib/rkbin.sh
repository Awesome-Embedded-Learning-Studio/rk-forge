# scripts/lib/rkbin.sh — resolve the RK3506 rkbin blob tuple from ONE source.
#
# pack-loader.sh (DDR/usbplug/SPL) and pack-fit.sh (tee) BOTH source this so the
# resolution logic is single-sourced and the SPL<->tee hash pair stays
# consistent. The sfc-dll-saga "tee v2.40 = Bad hash" was a MIXING artifact
# (ATK SPL v1.11 checking public tee v2.40); a fully-public chain (SPL v1.12 +
# tee v2.40 from the same rkbin) verifies against its own hash.
#
# Source AFTER lib/env.sh (which sets FORGE_RKBIN_DIR). Call rkbin_load, then
# use $RKBIN_DDR / $RKBIN_USBPLUG / $RKBIN_SPL / $RKBIN_TEE / $RKBIN_BLOB_DIR.
#
# Cross-invocation note: pack-loader and pack-fit are separate processes — to
# avoid the SPL/tee source mix, run BOTH with the same FORGE_RKBIN_DIR (the
# default public rkbin, the sole blob source). The forge orchestrator enforces
# this; do not pass --rkbin to only one of them.

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

# resolve the full {ddr,usbplug,spl,tee} tuple from FORGE_RKBIN_DIR + export it.
rkbin_load() {
  [[ -n "${FORGE_RKBIN_DIR:-}" ]] || die "FORGE_RKBIN_DIR unset (source lib/env.sh)"
  [[ -d "$FORGE_RKBIN_DIR" ]] || die "rkbin source not found: $FORGE_RKBIN_DIR (init submodule / fetch-deps)"
  RKBIN_BLOB_DIR="${FORGE_RKBIN_DIR}/bin/rk35"
  [[ -d "$RKBIN_BLOB_DIR" ]] || die "no bin/rk35 under $RKBIN_BLOB_DIR ($FORGE_RKBIN_DIR)"
  RKBIN_DDR=$(rkbin_resolve     'rk3506b_ddr_750MHz_v1.*.bin' 'DDR')        # skips the _rt_ variant
  RKBIN_USBPLUG=$(rkbin_resolve 'rk3506_usbplug_v1.*.bin'    'usbplug')
  RKBIN_SPL=$(rkbin_resolve     'rk3506_spl_v1.*.bin'        'SPL')
  RKBIN_TEE=$(rkbin_resolve     'rk3506_tee_v*.bin'          'tee' '_ta_')   # exclude trust-anchor vars
  export RKBIN_BLOB_DIR RKBIN_DDR RKBIN_USBPLUG RKBIN_SPL RKBIN_TEE
}
