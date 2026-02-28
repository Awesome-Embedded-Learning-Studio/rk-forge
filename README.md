<div align="center">

```
██████╗ ██╗  ██╗      ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██║ ██╔╝      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝█████╔╝ █████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
██╔══██╗██╔═██╗ ╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
██║  ██║██║  ██╗      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**面向 Rockchip 开发板的开源锻造工坊 —— 驱动、补丁、Rootfs 配置与 SDK 脚本，一次集结，随时开打。**

🌐 Language: **中文** | [English](assets/README_EN.md)

[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](LICENSE)
[![Boards](https://img.shields.io/badge/Boards-RK3588_|_RK3568_|_RK3528_|_RK3506-red?style=flat-square)](#支持的开发板)
[![CI](https://img.shields.io/github/actions/workflow/status/yourname/rk-forge/ci-patch-validate.yml?label=Patch%20CI\&style=flat-square)](https://github.com/yourname/rk-forge/actions)
[![Patches](https://img.shields.io/badge/dynamic/json?url=https://raw.githubusercontent.com/yourname/rk-forge/main/meta/stats.json\&query=$.total_patches\&label=Patches\&style=flat-square\&color=ff6600)](patches/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)

</div>

---

## ⚒️ 什么是 RK-Forge？

RK-Forge 是一个**个人维护的开源工作空间**，用于快速将 Rockchip 平台开发板引导成可运行的嵌入式系统。

它把那些通常散落在厂商 SDK、论坛帖子、Wiki 页面和深夜 shell 历史记录里的内容统一整理起来：

* 🔩 **自研驱动** —— 独立内核模块，附带每块板卡的兼容性元数据
* 🩹 **SDK 与 U-Boot 补丁** —— 基于 `format-patch` + `series` 管理，具备源码感知能力并通过 CI 校验
* 📦 **Rootfs 配置** —— 三层 `packages.config` 模型，支持 Buildroot 目标及包级补丁
* 🛠️ **SDK 工具脚本** —— 统一封装 build、flash、menuconfig 与环境初始化流程
* 🖥️ **应用示例** —— Qt 示例、NPU Demo、RGA 工具及第三方子模块

> 不再翻找厂商 Wiki。Clone → source → build → flash —— 这是约定。

---

## 🎯 支持的开发板

> 先这样写，目前都在开发
| SoC              | 系列                          | Linux | Android | Buildroot | 裸机 / RTOS |  CI |
| ---------------- | --------------------------- | :---: | :-----: | :-------: | :-------: | :-: |
| RK3588 / RK3588S | Cortex-A76 + A55，6 TOPS NPU |   -   |    -    |     -     |     —     |  -  |
| RK3566 / RK3568  | Cortex-A55                  |   -   |    -    |     -     |     —     |  -  |
| RK3506           | Cortex-A7 MCU 级             |   —   |    —    |     —     |     -     |  -  |

> ✅ 已验证 · 🚧 开发中 · — 不适用

---

## 🚧 当前重点方向

* [ ] 常用脚本整理
* [ ] 常用教程整理
* [ ] 将 Buildroot 补丁自动适配进 RK-SDK
* [ ] 开发一个工具，自动对比 private SDK 与开源仓库差异并生成快速应用补丁
* [ ] 第三方组件自动补丁与说明生成机制
* [ ] 纯 C/C++ 公共库（最小化C/C++验证依赖）

---

## 🤝 贡献方式

欢迎提交 PR 与 Issue。
在提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，特别注意：

* Patch 命名规范
* 新增驱动必须附带完整的 `METADATA.yaml`

---

## 📄 开源协议

MIT LICENSE —— 详见 [LICENSE](LICENSE)。

若补丁源自 GPL 授权的 SDK，则保留其原始 GPL-2.0 许可证，并在对应 `METADATA.yaml` 中明确标注。

---

<div align="center">

**用 🔥 和无数串口终端堆出来的工程。希望我们可以更方便的自定义自己的打包~**

</div>