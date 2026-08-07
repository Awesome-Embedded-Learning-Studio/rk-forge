<div align="center">

# rk-forge

A per-board, full-stack mainline-Linux teaching + engineering project for Rockchip · RK3506B / RK3568 / RK3588
Mainline-first · honest on hardware · chasing fully-open

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Kernel](https://img.shields.io/badge/Kernel-mainline%207.1-blue?style=flat-square)](#what-this-is)
[![U-Boot](https://img.shields.io/badge/U--Boot-mainline%202026.07--rc4-blue?style=flat-square)](#what-this-is)
[![Mainline](https://img.shields.io/badge/Mainline-first%20%E2%9C%93-brightgreen?style=flat-square)](#what-this-is)
[![Boards](https://img.shields.io/badge/boards-RK3506B%20%C2%B7%20RK3568%20%C2%B7%20RK3588-brightgreen?style=flat-square)](#what-this-is)
[![WSL2](https://img.shields.io/badge/WSL2-tested-brightgreen?style=flat-square)](QUICK_START.md)
[![Docs](https://img.shields.io/badge/docs-online%20%E2%86%92-blue?style=flat-square)](https://awesome-embedded-learning-studio.github.io/rk-forge/)
[![Deploy](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml/badge.svg)](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml)

English · [中文](README.md)

</div>

---

## What this is

rk-forge runs **mainline** Linux 7.1 + U-Boot 2026.07 on three Rockchip boards, building a full-stack lane per board — from driver bring-up up to the application layer. It is **not** a distro image / Armbian / Yocto / vendor BSP: what's delivered is a reproducible build chain + an ordered patch library + a tutorial, not a finished product.

- **Mainline-first**: kernel / U-Boot are upstream, integrated not reinvented; `rkbin` is the only closed dependency (treated as a target, tracked for elimination).
- **Honest on hardware**: every capability is backed by on-board evidence; verified is verified, not-yet is not-yet, status is never painted green.
- **Chasing fully-open**: eliminate closed blobs layer by layer toward a fully-open stack (north star).

> Full positioning & design rationale: [blueprint.md](document/blueprint.md); architecture & build: [architecture.md](document/architecture.md) (both also under the "项目" menu on the [docs site](https://awesome-embedded-learning-studio.github.io/rk-forge/)).

## 🚀 Quick start

```bash
./scripts/doctor.sh            # check host deps + the cross toolchain (prints the apt line if missing)
source scripts/env-setup.sh    # export ARCH / CROSS_COMPILE
bash scripts/forge.sh all      # setup → build → pack → assemble → board/aes/out/update.img
```

Default board `aes` (RK3506B); other boards add `--board=rk3568-atk` / `rk3588-topeet` (auto-selects toolchain / storage / rootfs profile); OpenWrt adds `--rootfs=openwrt`. Full steps, flashing, and common pitfalls are in [QUICK_START.md](QUICK_START.md) and [document/tutorial/](document/tutorial/).

## Where to find what

| Looking for | Go to |
|---|---|
| How to use / tutorial | [document/tutorial/](document/tutorial/) |
| Per-board plan & progress (ROADMAP) | [document/planning/](document/planning/) |
| mainline-vs-vendor gaps, **what's verified** | [document/sdk-diff.md](document/sdk-diff.md) |
| closed-blob inventory & elimination path | [document/blobs.md](document/blobs.md) |
| pitfalls | [document/pitfalls/](document/pitfalls/) |
| on-board logs / timeline | [document/logs/](document/logs/) · [document/notes/](document/notes/) |
| positioning & design rationale | [document/blueprint.md](document/blueprint.md) |
| architecture & build | [document/architecture.md](document/architecture.md) |
| contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Repository layout

```
scripts/                      forge.sh (single entry) + lib/ + build-*/pack-* .sh + apply-series.sh + pure-Python packers
patches/<board>/{linux,uboot}/series   per-board ordered patch series (git format-patch [PATCH] subjects)
board/                        per-board build workspace + config (aes · rk3568-atk · rk3588-topeet)
third_party/                  rkbin (pinned submodule) · buildroot · src/<board>/ (mainline source trees)
reference/                    per-board vendor SDKs (reference/extraction pool, NOT a build dependency)
config/                       forge.env · toolchain.conf (declarative config)
document/                     tutorial · planning · sdk-diff · blobs · pitfalls · logs · notes
```

> This is the **current** layout; an in-place refactor is underway toward a cleaner shape (no `config/` dir, `board/→boards/` self-containing `board.yaml`+`patches/`, all products under a root `out/`). Target structure: [document/architecture.md](document/architecture.md).

## 📄 License

MIT, see [LICENSE](LICENSE). Patches originating from GPL SDKs retain GPL-2.0 and are marked in the patch header. `rkbin` is Rockchip proprietary firmware, referenced as a pinned submodule only — **not copied into this repo**, not redistributed.

---

<div align="center">

[⭐ Star](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge) · [🍴 Fork](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/fork) · [📢 Issues](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues)

</div>
