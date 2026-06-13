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

- `third_party/rkbin/` pins the exact blob commit (submodule gitlink).
- `scripts/sdk-diff.sh` reports `rkbin` as the residue when comparing a vendor BSP
  vs our mainline port — i.e. *how much closed firmware remains*.
- Goal (future iteration): track / contribute to an open DDR-init effort so this
  table shrinks. Updates land here first.

## Licensing

`rkbin` contents are **not redistributable source** (proprietary Rockchip firmware).
Do **not** copy blob files into this repo; reference them via the pinned submodule only.
