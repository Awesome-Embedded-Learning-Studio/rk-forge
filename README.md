<div align="center">

# rk-forge

每板全栈的 Rockchip 主线 Linux 教学 + 工程项目 · RK3506B / RK3568 / RK3588
主线优先 · 真板诚实 · 追全开源

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Kernel](https://img.shields.io/badge/Kernel-mainline%207.1-blue?style=flat-square)](#这是什么)
[![U-Boot](https://img.shields.io/badge/U--Boot-mainline%202026.07--rc4-blue?style=flat-square)](#这是什么)
[![Mainline](https://img.shields.io/badge/Mainline-first%20%E2%9C%93-brightgreen?style=flat-square)](#这是什么)
[![Boards](https://img.shields.io/badge/boards-RK3506B%20%C2%B7%20RK3568%20%C2%B7%20RK3588-brightgreen?style=flat-square)](#这是什么)
[![WSL2](https://img.shields.io/badge/WSL2-tested-brightgreen?style=flat-square)](QUICK_START.md)
[![Docs](https://img.shields.io/badge/docs-online%20%E2%86%92-blue?style=flat-square)](https://awesome-embedded-learning-studio.github.io/rk-forge/)
[![Deploy](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml/badge.svg)](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/actions/workflows/deploy.yml)

[English](README.en.md) · 中文

</div>

---

## 这是什么

rk-forge 把**主线** Linux 7.1 + U-Boot 2026.07 跑到三块 Rockchip 板上,围绕每块板搭一条从驱动 bring-up 到应用层的全栈车道。**不是**发行版镜像 / Armbian / Yocto / 厂商 BSP——交付的是可复现构建链 + 有序补丁库 + 教程,不是成品。

- **主线优先**:kernel / U-Boot 走上游,只集成不重造;`rkbin` 是唯一闭源依赖(当靶子、追踪消除)。
- **真板诚实**:每项能力挂真板证据,跑通说跑通、没通标没通,状态不刷绿。
- **追全开源**:逐层消灭闭源 blob,走向全开源(北极星)。

> 定位的完整论述与设计原则见 [蓝图与定位](document/blueprint.md);架构与构建见 [架构与构建](document/architecture.md)(这两份也在[文档站](https://awesome-embedded-learning-studio.github.io/rk-forge/)「项目」菜单里)。

## 🚀 快速开始

```bash
./scripts/doctor.sh            # 检查 host 依赖 + 交叉工具链(缺啥给 apt 命令)
source scripts/env-setup.sh    # 导出 ARCH / CROSS_COMPILE
bash scripts/forge.sh all      # setup → build → pack → assemble → board/aes/out/update.img
```

默认板 `aes`(RK3506B);构建其它板加 `--board=rk3568-atk` / `rk3588-topeet`(自动选工具链 / 存储 / rootfs profile);OpenWrt 加 `--rootfs=openwrt`。完整步骤、烧录上板、常见坑见 [QUICK_START.md](QUICK_START.md) 与 [document/tutorial/](document/tutorial/)。

## 去哪找什么

| 想找什么 | 去哪 |
|---|---|
| 怎么用 / 教程 | [document/tutorial/](document/tutorial/) |
| 每板规划与进度(ROADMAP) | [document/planning/](document/planning/) |
| 主线 vs vendor 差距、**验证了什么** | [document/sdk-diff.md](document/sdk-diff.md) |
| 闭源 blob 清单与消除路径 | [document/blobs.md](document/blobs.md) |
| 踩过的坑 | [document/pitfalls/](document/pitfalls/) |
| 真板日志 / 时间线 | [document/logs/](document/logs/) · [document/notes/](document/notes/) |
| 定位与设计原则 | [document/blueprint.md](document/blueprint.md) |
| 架构与构建 | [document/architecture.md](document/architecture.md) |
| 贡献指南 | [CONTRIBUTING.md](CONTRIBUTING.md) |

## 仓库结构

```
scripts/                      forge.sh(单一入口)+ lib/ + build-*/pack-* .sh + apply-series.sh + 纯 Python 打包器
patches/<board>/{linux,uboot}/series   按板隔离的有序补丁序列(git format-patch 的 [PATCH] 主题)
board/                        各板构建工作区 + 配置(aes · rk3568-atk · rk3588-topeet)
third_party/                  rkbin(pinned submodule)· buildroot · src/<board>/(主线源码树)
reference/                    各板 vendor SDK(参照/萃取池,非构建依赖)
config/                       forge.env · toolchain.conf(声明式配置)
document/                     tutorial · planning · sdk-diff · blobs · pitfalls · logs · notes
```

> 这是**当前**布局;正在就地重构为更清晰的形状(无 `config/` 目录、`board/→boards/` 自含 `board.yaml`+`patches/`、产物归到根 `out/`)。目标结构见 [document/architecture.md](document/architecture.md)。

## 📄 协议

MIT,详见 [LICENSE](LICENSE)。源自 GPL SDK 的补丁保留 GPL-2.0 并在补丁头标注。`rkbin` 为 Rockchip 专有固件,仅以 pinned 子模块引用,**不拷入本仓库**、不再分发。

---

<div align="center">

[⭐ Star](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge) · [🍴 Fork](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/fork) · [📢 Issues](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues)

</div>
