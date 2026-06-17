# BLOBS.md — closed-source binary inventory (honest, non-purist)

rk-forge is mainline-first and blob-minimizing, but **not blob-purist**: where a
closed blob is currently unavoidable, we use it, document it here, and track the
path to eliminating it. This file is the single source of truth for *what closed
firmware this project still depends on, and why*.

## Why we can't be pure (yet)

Rockchip boot needs DDR init before any open code runs. That init lives in
Rockchip's closed TPL/SPL blobs (`rkbin`). As of 2026 (FOSDEM 2026), there is no
fully-open DDR-init replacement for RK3506. So `rkbin` is a **hard dependency**.

Everything else — Linux kernel, U-Boot proper, the device tree — is **open and upstream**.

## Current closed blobs

| Blob | Source | What it does | Replaceable? |
|---|---|---|---|
| RK3506 DDR bin (`bin/rk35/*ddr*`) | github.com/rockchip-linux/rkbin | initializes DRAM before U-Boot | **No** (2026) — no open DDR init for RK3506 yet |
| TPL/SPL loader stages | rkbin | early boot feeding U-Boot proper | Partial — U-Boot proper is open; pre-U-Boot stages are not |

## How rk-forge tracks this

- `third_party/rkbin/` is a **checked-out, pinned submodule** (commit `ecb4fcb`) of
  the public `github.com/rockchip-linux/rkbin`. It is the **default blob source**
  for the loader (`scripts/pack-loader.sh`) and the uboot FIT's tee
  (`scripts/pack-fit.sh`) — giving a fully-public, internally-consistent loader
  (DDR v1.06 + usbplug v1.03 + SPL v1.12 + tee v2.40) that needs **zero**
  vendor-sdk. This is the P1 "fully-public loader" conquest.
- **ATK fallback** (`third_party/rkbin-atk/`, see below): the public rkbin has
  NEVER carried the ATK-snapshot blobs (usbplug v1.02 / SPL v1.11 / tee v2.10) —
  only newer v1.03/v1.12/v2.40. Those are committed locally as a regression
  baseline; `FORGE_RKBIN_DIR=third_party/rkbin-atk` rebuilds the known-good ATK
  loader. Boot of the **public** loader is board-test pending (the conquest's
  remaining verification step).
- `scripts/sdk-diff.sh` reports `rkbin` as the residue when comparing a vendor BSP
  vs our mainline port — i.e. *how much closed firmware remains*.
- Goal (future iteration): track / contribute to an open DDR-init effort so this
  table shrinks. Updates land here first.

### The tee-version nuance (correcting the sfc-dll-saga takeaway)

The verified-boot chain pairs SPL ↔ tee by hash. The saga's "tee v2.40 = Bad hash"
was a **mixing** artifact: the ATK SPL v1.11 (built to verify v2.10) reading the
public tee v2.40. A **fully-public** chain — public SPL v1.12 verifying public tee
v2.40, both from the same rkbin release — is internally consistent and should
verify. Board-test confirms. Never mix blob sources between `pack-loader.sh` and
`pack-fit.sh` (inconsistent SPL↔tee → "optee Bad hash").

## NAND packaging: closed binaries (not blobs, but not open)

The "source → flashable update.img" pipeline (notes/09) still calls three
stripped Rockchip x86-64 ELF tools with no source. They are **deterministic
packagers** (like `mkimage`), not firmware blobs — but they are closed:

| Tool | Path | Role | Replaceable? |
|---|---|---|---|
| `boot_merger` | `vendor-sdk/rkbin/tools/boot_merger` (ver 1.35) | wraps DDR+usbplug+SPL blobs into the RK idblock (loader) | Partial — the *blobs* are the hard dep; the packer has open reimplementations in some rkbin trees but not a clean drop-in |
| `afptool` | `vendor-sdk/tools/linux/Linux_Pack_Firmware/rockdev/afptool` (v2.29) | packs the RKAF container (manifest + partition images) inside update.img | No clean open source — community reimplementations exist (rkflashtool family), yak-shave |
| `rkImageMaker` | same dir (v2.29) | wraps RKAF with the RKFW header + loader → final update.img | Same as afptool |

`mkimage` (the FIT packer) is **open** and mainline — forge uses
`third_party/explore/uboot/tools/mkimage` (2026.07-rc4), not the vendor 2017.09
copy. See `scripts/pack-*.sh`.

### Loader byte-diff (honest edge)

`scripts/pack-loader.sh` reproduces the loader via `boot_merger` (always from the
public submodule). The **default** build uses the public blobs (DDR v1.06 + usbplug
v1.03 + SPL v1.12, 281024 B); the **ATK fallback** (`FORGE_RKBIN_DIR=rkbin-atk`)
uses v1.06 + v1.02 + v1.11. Neither is byte-identical to the ATK-shipped
`rk3506-vendor-loader.bin` (270784 B): boot_merger embeds a build timestamp and
emits a slightly different (~6 KB) idblock layout. **Board-boot of either
forge-reproduced loader is unverified** — the conquest's remaining step. The ATK
fallback (matching the shipped loader's blob family) is the safe baseline to fall
back to if the public loader doesn't boot; the shipped loader remains the ultimate
regression baseline until a board test confirms a forge-reproduced loader.

## Licensing

`rkbin` contents are **not redistributable source** (proprietary Rockchip firmware).
Do **not** copy blob files into this repo; reference them via the pinned submodule only.

**One exception — `third_party/rkbin-atk/`:** three ATK-snapshot blobs (usbplug
v1.02 / SPL v1.11 / tee v2.10) are **not in the public rkbin** (never have been) and
are not fetchable from any URL. They are committed locally as a loader fallback
(regression baseline), but their public-redistribution status is **unverified**.
⛔ **Do not push `third_party/rkbin-atk/` to `origin`** — local working archive only.
Delete it once the public loader is board-verified. See `third_party/rkbin-atk/README.md`.
