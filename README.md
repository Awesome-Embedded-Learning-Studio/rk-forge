<div align="center">

```
██████╗ ██╗  ██╗      ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██║ ██╔╝      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝█████╔╝ █████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
██╔══██╗██╔═██╗ ╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
██║  ██║██║  ██╗      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**面向 Rockchip 平台的开发者工作空间 ——**  
**脚本库 × 驱动参考实现 × 结构化补丁管理 × 任意发行版 Rootfs 部署配方。**

🌐 语言：**中文** | [English](assets/README_EN.md)

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Boards](https://img.shields.io/badge/Boards-RK3588_|_RK3568_|_RK3528_|_RK3506-red?style=flat-square)](#支持的开发板)
[![CI](https://img.shields.io/github/actions/workflow/status/yourname/rk-forge/ci-patch-validate.yml?label=Patch%20CI&style=flat-square)](https://github.com/yourname/rk-forge/actions)
[![Patches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/yourname/rk-forge/main/meta/stats.json&query=$.total_patches&label=Patches&style=flat-square&color=ff6600)](patches/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

</div>

---

## ⚒️ 什么是 RK-Forge？

RK-Forge 是一个面向 **Rockchip 平台嵌入式开发者** 的开源工作空间。它不发布烧录镜像，也不替代 Armbian 或厂商 SDK——它解决的是 **SDK 下游开发者** 每天真正遇到的问题：

- 拿到一块新板子，怎么最快地把私有 SDK 变成可自定义的系统？
- 厂商 SDK 和 upstream 到底差了什么？哪些补丁我必须带，哪些可以丢掉？
- 驱动在哪里写、怎么写、如何在没有硬件的时候先跑通？
- 换一个发行版 Rootfs，最少需要动哪些配置？

RK-Forge 把这些答案整理成 **可组合的脚本库 + 可查阅的知识配方**，让你从 `git clone` 到第一次成功 `flash` 的路径尽可能直。

### 这个项目不是什么

| 不是 | 是 |
|------|-----|
| 开箱即用的镜像发布站 | 可组合的脚本 + 配方库的开箱即用的镜像发布站（笑） |
| Armbian / Librecomputer 的替代品 | 专注私有 SDK 场景的下游工具层 |
| 通用 ARM 开发工具 | 只做 Rockchip，做深不做宽 |
| 需要 Makefile 背诵的构建系统 | 即支持现代的构建系统一步构建，又支持`./scripts/xxx.sh`，看文档，自己组合 |

---

## 🚀 快速开始

### 环境初始化

```bash
git clone https://github.com/yourname/rk-forge.git
cd rk-forge
source scripts/env-setup.sh       # 安装并配置交叉编译工具链
```

### 应用补丁 & 编译内核

```bash
# 指定目标板卡和内核版本
./scripts/apply-patches.sh --board rk3588-evb --kernel 5.10
./scripts/build-kernel.sh  --board rk3588-evb --kernel 5.10
```

### 构建并烧录 Rootfs

```bash
# 使用 standard profile 构建 Debian Rootfs
./scripts/build-rootfs.sh --distro debian --profile standard --board rk3588-evb
./scripts/flash.sh --board rk3588-evb
```

### 分析私有 SDK 与 upstream 差异

```bash
# 传入你的本地私有 SDK 路径，工具自动 clone 对应 upstream 版本对比
./scripts/sdk-diff.py --sdk-path /path/to/vendor-sdk --component kernel
```

### 在 PC 上跑 QEMU 冠烟测试（无需真实硬件）

```bash
./sim/run-qemu.sh --kernel output/Image --rootfs output/rootfs.ext4
```

---

## 🎯 支持的开发板

| 板卡 | SoC | Kernel 5.10 | Kernel 6.1 | 状态 |
|------|-----|:-----------:|:----------:|------|
| （待补充） | RK3588 | 🚧 | 📋 计划 | Phase 1 主力 |
| （待补充） | RK3568 | 🚧 | 📋 计划 | Phase 1 |
| （待补充） | RK3528 | 📋 计划 | 📋 计划 | Phase 2 |
| （待补充） | RK3506 | 📋 计划 | 📋 计划 | Phase 2 |

> 🚧 = 进行中，📋 = 已计划，✅ = 已验证

---

## 🔩 驱动参考实现

`drivers/` 目录下的每个模块都是独立的内核模块，附带完整的 `METADATA.yaml`，声明：

- 经过验证的内核版本与板卡兼容性
- 依赖的内核配置项
- 原始 License（MIT 或保留 GPL-2.0）
- CI 验证状态

覆盖方向：GPIO/UART/SPI/I2C 外设、Camera/ISP、GPU/RGA/NPU、USB/PCIe、电源管理/DVFS、网络（WiFi/LTE）。

---

## 🩹 补丁管理

补丁使用 `git format-patch` 生成，通过 `series` 文件管理应用顺序，兼容 quilt 工作流。

```
patches/kernel/5.10/
├── series                         # 应用顺序列表
├── 0001-rk3588-fix-pcie-phy.patch
├── 0002-add-custom-spi-driver.patch
└── 0003-buildroot-overlay-fix.patch
```

所有补丁在 PR 合并前均须通过 CI 的 `patch apply + kernel build` 双重校验。详见 [docs/patch-workflow.md](docs/patch-workflow.md)。

---

## 📦 Rootfs 部署

RK-Forge 不绑定任何发行版。部署框架基于 ext4 镜像拷贝烧录，支持：

- **Buildroot**（极简嵌入式场景）
- **Debian / Ubuntu**
- 任何能打包成 ext4 rootfs 的发行版（Alpine、OpenWrt 等）

通过 `profiles/` 三档配置（minimal / standard / full）+ `overlays/` 板卡覆盖层组合，实现跨发行版的统一部署接口。详见 [docs/rootfs-deploy.md](docs/rootfs-deploy.md)。

---

## 🖥️ PC 端模拟（无硬件开发）

`sim/` 目录提供两种本地验证路径：

- **QEMU ARM64**：交叉编译内核后直接在 x86 机器上跑 boot 冠烟测试
- **Docker 容器**：轻量级驱动逻辑单元测试，不依赖真实硬件环境

适合在拿到板子之前提前验证补丁和驱动的基本逻辑。

---

## ⚙️ CI 流水线

| 阶段 | 触发时机 | 内容 |
|------|---------|------|
| pre-commit（本地） | `git commit` | lint + patch 格式检查 |
| patch-validate（远程） | PR | 补丁可应用性校验 + 内核交叉编译 |
| rootfs-build（远程） | PR / 手动触发 | Rootfs 镜像构建验证 |
| qemu-smoke（远程） | 手动触发 | QEMU boot 冠烟测试 |

---

## 🤝 贡献方式

欢迎提交 PR 与 Issue。提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，特别注意：

- Patch 命名规范（`NNNN-scope-brief-description.patch`）
- 新增驱动必须附带完整的 `METADATA.yaml`
- 补丁须在本地通过 `pre-commit` 检查后再推送

---

## 📄 开源协议

MIT LICENSE —— 详见 [LICENSE](LICENSE)。

若补丁源自 GPL 授权的 SDK，则保留其原始 GPL-2.0 许可证，并在对应 `METADATA.yaml` 中明确标注，不影响主仓库 MIT 协议。

---

<div align="center">

**用 🔥 和无数串口终端堆出来的工程。**  
**希望每个 Rockchip 开发者都能少翻一次厂商 Wiki。**

</div>
