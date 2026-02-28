---

<div align="center">

```
██████╗ ██╗  ██╗      ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██║ ██╔╝      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝█████╔╝ █████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
██╔══██╗██╔═██╗ ╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
██║  ██║██║  ██╗      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**The open-source forge for Rockchip boards — drivers, patches, rootfs configs & SDK scripts, ready to strike.**

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Boards](https://img.shields.io/badge/Boards-RK3588_|_RK3568_|_RK3528_|_RK3506-red?style=flat-square)](#supported-boards)
[![CI](https://img.shields.io/github/actions/workflow/status/yourname/rk-forge/ci-patch-validate.yml?label=Patch%20CI&style=flat-square)](https://github.com/yourname/rk-forge/actions)
[![Patches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/yourname/rk-forge/main/meta/stats.json&query=$.total_patches&label=Patches&style=flat-square&color=ff6600)](patches/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

</div>

---

## ⚒️ What is RK-Forge?

RK-Forge is a **personal, open-source workspace** for rapidly bootstrapping Rockchip-based boards into working embedded systems. It centralizes everything that is normally scattered across vendor SDKs, forum threads, and late-night shell history:

- 🔩 **Self-made drivers** — standalone kernel modules with per-board compatibility metadata
- 🩹 **SDK & U-Boot patches** — organized as `series`-managed `format-patch` files, source-aware and CI-validated
- 📦 **Rootfs configs** — a three-layer `packages.config` model for Buildroot targets, including package-level patches
- 🛠️ **SDK toolkit scripts** — unified wrappers for build, flash, menuconfig and environment setup
- 🖥️ **Applications** — Qt demos, NPU samples, RGA tools and third-party submodules

> No more hunting through vendor wikis. Clone, source, build, flash. That's the contract.

---

## 🎯 Supported Boards

| SoC | Series | Linux | Android | Buildroot | Bare-metal / RTOS | CI |
|-----|--------|:-----:|:-------:|:---------:|:-----------------:|:--:|
| RK3588 / RK3588S | Cortex-A76+A55, 6 TOPS NPU | - | - | - | — | - |
| RK3566 / RK3568 | Cortex-A55 | - | - | - | — | - |
| RK3506 | Cortex-A7 MCU-class | — | — | — | - | - |

> ✅ Verified · 🚧 In Progress · — Not Applicable

## Currently Focusing
- [ ] Some Common Scripts
- [ ] Some Common Tutorials
- [ ] Apply Buildroot Patches into RK-SDK
- [ ] Making A Tools That can auto pick up diffs among private-sdk and open-sources to make fast apply
- [ ] Enable Third Party Conviniences Auto Patches And Discriptions
- [ ] Some Common Libraries With Only the C/C++ To Minimize the Dependencies

---

## 🤝 Contributing

PRs and issues are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first — especially the patch naming convention and the requirement for a filled `METADATA.yaml` on any new driver.

---

## 📄 License

MIT LICENSE — see [LICENSE](LICENSE).  
Patches that originate from GPL-licensed SDKs retain their original GPL-2.0 license and are marked accordingly in their `METADATA.yaml`.

---

<div align="center">

**Built with 🔥 on too much coffee and too many serial consoles.**

</div>