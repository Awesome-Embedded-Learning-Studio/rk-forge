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

- `third_party/rkbin/` is registered as a submodule (`.gitmodules`), but is
  **not yet checked out** (only a `.gitkeep` placeholder). The blobs actually in
  use live in two local clones (both gitignored): `third_party/explore/rkbin`
  (newer v1.03/v1.12) and `third_party/vendor-sdk/rkbin` (the ATK-verified
  v1.02/v1.11 that the shipped loader was built from). **TODO:** `submodule
  update --init` + pin the verified commit so there's one canonical rkbin.
- `scripts/sdk-diff.sh` reports `rkbin` as the residue when comparing a vendor BSP
  vs our mainline port — i.e. *how much closed firmware remains*.
- Goal (future iteration): track / contribute to an open DDR-init effort so this
  table shrinks. Updates land here first.

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

`scripts/pack-loader.sh` reproduces the loader from the ATK-verified blobs
(DDR v1.06 + usbplug v1.02 + SPL v1.11) via `boot_merger`, but the output is
**not byte-identical** to the ATK-shipped `rk3506-vendor-loader.bin` (270784 B):
boot_merger embeds a build timestamp and emits a slightly different (~6 KB)
idblock layout than whatever built the shipped one. Same blob family → boot
plausibly works, but **board-boot of the forge-reproduced loader is unverified**.
The shipped loader remains the regression baseline until a board test confirms.

## Licensing

`rkbin` contents are **not redistributable source** (proprietary Rockchip firmware).
Do **not** copy blob files into this repo; reference them via the pinned submodule only.
