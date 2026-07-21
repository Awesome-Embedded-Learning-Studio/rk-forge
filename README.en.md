<div align="center">

# rk-forge

**A mainline-first embedded Linux workspace for Rockchip RK3506**
Ordered patch library · Honest gap report · forge build orchestrator · 0→1 tutorial

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Kernel](https://img.shields.io/badge/Kernel-mainline%207.1-blue?style=flat-square)](#-verified-on-hardware)
[![U-Boot](https://img.shields.io/badge/U--Boot-mainline%202026.07-blue?style=flat-square)](#-verified-on-hardware)
[![Mainline](https://img.shields.io/badge/Mainline-first%20%E2%9C%93-brightgreen?style=flat-square)](#-what-this-is)
[![Board](https://img.shields.io/badge/board-RK3506B%20verified-brightgreen?style=flat-square)](#-verified-on-hardware)
[![WSL2](https://img.shields.io/badge/WSL2-tested-brightgreen?style=flat-square)](QUICK_START.md)
[![Docs](https://img.shields.io/badge/docs-online%20%E2%86%92-blue?style=flat-square)](https://awesome-embedded-learning-studio.github.io/rk-forge/)
[![Deploy](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml/badge.svg)](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml)

English · [中文](README.md)

</div>

---

## What this is

rk-forge serves the **underserved RK3506**: bring up the latest mainline Linux, and **honestly report what's still missing**.

It is **not** yet another Armbian / Yocto / vendor BSP image. It does four things:

1. **Ordered patch library** — quilt-style `series`; `git am` lands real commits, bisectable, atomic rollback on failure (fixes the "apply only the last patch, silent skip on failure" disease).
2. **Honest gap report** — [document/sdk-diff.md](document/sdk-diff.md) tells you per subsystem: what the vendor BSP has / what mainline has / what's missing / whether it still boots.
3. **forge build orchestrator** — one `forge.sh all` runs `setup → build → pack → assemble`, with a DAG of dependencies and content-hash incremental skipping, replacing RK-SDK `build.sh`'s rebuild-everything-every-time experience.
4. **0→1 tutorial** — a reproducible path from a blank machine to RK3506 mainline booting to a UART login, each chapter backed by real on-board UART captures — never synthesized.

**Core thesis (verified, on hardware):** RK3506's SoC foundation — pinctrl + clock (since Linux 6.19) and U-Boot SoC support (merged via Jonas Karlman's v2 series) — is **entirely in mainline**. So for "mainline boot", the whole RK-SDK collapses into two things: ① `rkbin` (closed DDR-init blob, unavoidable — see [Honest blob policy](#-honest-blob-policy)); ② **a board device tree** (not upstream — rk-forge writes it). rk-forge's main contribution is that `.dts` + an honest path.

> Others sell cooked meals; rk-forge sells the recipe + the stove + a book that walks you through cooking — the dish nobody else makes.

📖 **Live docs site**: <https://awesome-embedded-learning-studio.github.io/rk-forge/>

---

## ✅ Verified on hardware

Not a slide deck — these are capabilities running on real hardware (AES-RK3506B, RK3506B / Cortex-A7×3). Full evidence logs in [document/logs/](document/logs/).

| Capability | Status | Notes |
|------------|--------|-------|
| Mainline U-Boot 2026.07-rc4 bring-up | ✅ on board | SPL → interactive prompt |
| Mainline Linux 7.1 SMP boot | ✅ on board | A7×3 up, ttyS0 console |
| UBIFS rootfs + RW persistence | ✅ on board | `/persist.log` survives cold reboot; UBIFS recovery OK |
| SPI-NAND R/W (W25N04KV + SFC) | ✅ on board | DLL tuning ported, 80MHz read stable, powergood + WPEN on write path |
| SD-card boot (pure SD, RKFW) | ✅ on board | kernel + rootfs both boot from SD ext4 to buildroot shell |
| Ethernet dual-port (gmac0 + gmac1) | ✅ on board | YT8512, RMII |
| SPI + MMC/SD | ✅ on board | on-board storage trio |
| I2C×3 + UART2 (RMIO crossbar) | ✅ on board | RMIO mux ported |
| Audio (ES8388 + SAI1 + DMA) | ✅ digital chain | sound card registered, aplay/mpg123 48k clean playback |
| WiFi (RTL8733BU, wlan0/wlan1) | ✅ on-board probe | out-of-tree driver onto 7.1, full probe |
| **OpenWrt rootfs profile** (opkg / kmod / LuCI) | ✅ on board | `--rootfs=openwrt`, alongside buildroot; OpenWrt builds kernel+rootfs (musl), vermagic matches by construction; NAND(UBIFS) + SD both verified |

The pre-U-Boot stages (DDR / secure) still borrow the `rkbin` blob — a hard reality of the RK platform; see [Honest blob policy](#-honest-blob-policy).

---

## 🚀 Quick start

```bash
./scripts/doctor.sh            # check host deps + the armhf cross toolchain (prints the apt line if missing)
source scripts/env-setup.sh    # export ARCH=arm / CROSS_COMPILE=arm-none-linux-gnueabihf-
bash scripts/forge.sh all      # setup → build → pack → assemble → board/aes/out/update.img
```

`forge` is the single-entry orchestrator. Common subcommands:

```bash
bash scripts/forge.sh setup            # fetch source trees + WiFi driver + apply the patch library
bash scripts/forge.sh status           # see which stages are up-to-date (incremental skip at a glance)
bash scripts/forge.sh assemble --sd    # build an SD-card image (RKFW; this board's ROM accepts only an RK-tool card)
bash scripts/forge.sh clean --full     # clean rebuild
```

> **Want OpenWrt (opkg / LuCI / kmod)?** Add `--rootfs=openwrt` to the same orchestrator to switch to the OpenWrt profile — OpenWrt builds its own kernel + rootfs (musl toolchain, so kmod vermagic matches by construction), while rk-forge still does the RK-specific packing; both NAND and SD paths are verified on board. Usage: `bash scripts/forge.sh all --rootfs=openwrt` (add `--sd` for the SD image). Tutorial: [OpenWrt port](document/tutorial/openwrt/00_openwrt.md) · Reference: [board/aes/openwrt/README.md](board/aes/openwrt/README.md). The buildroot profile remains the default and is untouched without the flag.

> **Build progress:** `forge build` shows live progress ([buildmeter](https://github.com/Awesome-Embedded-Learning-Studio/buildmeter)) — a bordered color Panel if `rich` is installed, a zero-dependency ANSI bar otherwise. `FORGE_PROGRESS=0` disables it.

> **zsh users:** always invoke as `bash scripts/forge.sh ...` — the lib scripts rely on `BASH_SOURCE`, which is empty under zsh.

Flashing and on-board boot are in [QUICK_START.md](QUICK_START.md) and [document/tutorial/boot/](document/tutorial/boot/).

---

## 📖 Learning path

The bring-up arc has five phases, read in order: get the board **booting**, make it **persistently log in**, light up **peripherals**, add the **SD card** as a second boot path, then tie it all together with the **forge orchestrator**.

| Phase | Topic | Contents | Status |
|-------|-------|----------|--------|
| 🚀 | [Boot](document/tutorial/boot/) | toolchain → U-Boot & rkbin → board device tree | ✅ |
| 📦 | [Rootfs](document/tutorial/rootfs/) | buildroot → init timing → UBIFS & loader-weak-write saga | ✅ |
| 🔌 | [Peripherals](document/tutorial/peripherals/) | Ethernet/SPI/MMC → USB → WiFi → I2C/UART → Audio | ✅ expanding |
| 💾 | [SD boot](document/tutorial/sd-boot/) | SD-1 manual boot → SD-2 autoboot | ✅ |
| 🛠️ | [forge orchestrator](document/tutorial/forge/) | one command for the whole build chain | ✅ |

Pitfalls are filed by failure domain in [document/pitfalls/](document/pitfalls/); the raw timeline lives in [document/notes/](document/notes/).

---

## 📦 Repository layout

```
scripts/
  forge.sh                     ★ single-entry orchestrator (setup/build/pack/assemble/all/clean/status)
  lib/{env,log,stage,toolchain,host,rkbin}.sh   shared libs; stage.sh = content-hash incremental skip
  apply-series.sh              ordered patch library (git am + true --check dry-run + atomic rollback)
  fit-pack.py · rkfw-pack.py   pure-Python packers, replacing vendor mkimage / afptool / rkImageMaker
  build-{linux,uboot,rootfs,openwrt}.sh · pack-{loader,fit,sd,ubifs}.sh · assemble-update.sh
  doctor.sh · env-setup.sh · fetch-deps.sh · flash-sd.sh
patches/{linux,uboot,openwrt}/series   ordered patch series ([mainline]/[uboot] prefix; openwrt is a Device/aes + config overlay)
board/                         aes/(build workspace: fit/rootfs/buildroot-external/openwrt) · rk3506-evb/(board config)
third_party/                   rkbin(pinned submodule) · buildroot · src/(linux·uboot trees, +openwrt optional profile, fetch-deps-managed)
reference/                     vendor-sdk(reference/extraction pool, NOT a build dependency)
config/                        forge.env · toolchain.conf (declarative config)
document/                      tutorial · pitfalls · notes · logs · sdk-diff
```

---

## 🎯 Supported boards

| Board | SoC | Status |
|-------|-----|--------|
| AES-RK3506B | Rockchip RK3506B (Cortex-A7×3, 32-bit armhf) | ✅ fully supported |

Board device trees for other RK3506 boards are welcome via PR.

---

## 🧭 Honest blob policy

rk-forge is mainline-first and blob-minimizing, but **not blob-purist**: where a closed blob is currently unavoidable (`rkbin`'s DDR/SPL/TEE), we use it, document it, and track the elimination path. Beyond the pre-U-Boot stages, **the Linux kernel, U-Boot proper, and the device tree are all open mainline**. The full inventory and elimination path are in [document/blobs.md](document/blobs.md).

---

## 🤝 Contributing

Patches, board DTs, tutorials, and issue reports are all welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.

- **Patches**: quilt-style ordered `patches/<component>/series`, one patch per commit, generated with `git format-patch` and carrying `Signed-off-by`; prefix `[mainline]` / `[uboot]`.
- **Bash leaves must stay Python-wrap-able**: clean stdin/stdout/exit, **no** interactive `/dev/tty` (that's why `doctor.sh` just prints the apt command — never auto-installs).
- **Incremental builds**: use `lib/stage.sh` content-hash skipping — don't rebuild a stage whose inputs haven't changed.
- 🐛 [Report a bug](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues) · 🔧 [Open a PR](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/pulls)

---

## 📄 License

MIT, see [LICENSE](LICENSE). Patches originating from GPL SDKs retain GPL-2.0 and are marked in the patch header. `rkbin` is Rockchip proprietary firmware, referenced as a pinned submodule only — **not copied into this repo**, not redistributed.

---

<div align="center">

**An imx-forge sibling for the Rockchip world — tackling the underserved RK3506, running the latest Linux and honestly reporting the gaps.**

[⭐ Star](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge) · [🍴 Fork](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/fork) · [📢 Issues](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues)

</div>
