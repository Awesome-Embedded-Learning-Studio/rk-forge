# Changelog

## [Unreleased] — repo restructure (2026-06-13)
- Repo restructured to the mainline-first RK3506 layout (mirrors imx-forge's
  *positioning*, own structure — not a 1:1 copy).
- `apply-series.sh`: ordered quilt `series` via `git am` + true dry-run (`--check`)
  + atomic rollback — fixes imx-forge's "apply only the last patch, silent skip" debt
  (which was duplicated across 4 builder scripts).
- `doctor.sh` + `lib/{log,toolchain,stage}.sh` + `config/toolchain.conf`: standalone
  env checker with **no** interactive apt (Python-wrap-able seam); `stage.sh` adds
  content-hash incremental skipping (vs RK-SDK build.sh's full rebuilds).
- Premise corrections (independently verified): target mainline **7.0.x** (6.19 is EOL);
  U-Boot RK3506 SoC support **already upstream**; rk-forge's contribution = **board DT**.
- Added `BLOBS.md` (rkbin honesty), `third_party/vendor-sdk/` reference slot.
- Removed: `roadmap.md` (old RK3588-first / multi-SoC vision), `buildroot/`,
  `scripts/CI/`, `scripts/network/` placeholders.
