---
title: 三板教学路线
---

# 三板教学路线

> rk-forge 围绕三块 Rockchip 开发板组织教学——从 ARM32 主线 bring-up，到 AArch64 Linux 驱动框架，再到异构计算与产品工程。三块板不是平行的三门课，是一条递进的阶梯；每块板各有一份 ROADMAP，定义要教什么、什么顺序、怎么验收、当前进展到哪。

## 三块板，一条阶梯

| 板子 | SoC / 架构 | 你会学到 | ROADMAP | 进展 |
|---|---|---|---|---|
| **RK3506B** | RK3506B / ARMv7-A · Cortex-A7×3（32-bit armhf） | 主线 bring-up、SPI-NAND/UBIFS 可靠性、SD 启动、Buildroot/OpenWrt、工业接口 | [RK3506B 路线](RK3506B_ROADMAP) | 🟢 `partial` — 真板已验证，教程已在 [tutorial/](../tutorial/) 兑现 |
| **RK3568** | RK3568 / AArch64 · Cortex-A55×4 | Linux 设备模型、IRQ/clock/regulator、I²C/SPI/UART、DMA、USB/PCIe、网络、DRM | [RK3568 路线](RK3568_ROADMAP) | 🟡 `partial` — ATK 真机 boot 已验证（多外设板验），课程化待建 |
| **RK3588** | RK3588 / AArch64 · A76+A55 big.LITTLE | 异构、内存/SMMU/dma-buf、DRM/V4L2/MPP/RGA、AI(NPU)/媒体/Android/GPU | [RK3588 路线](RK3588_ROADMAP) | 🟡 `partial` — iTOP 真机 boot 到 GNOME 桌面已验证，课程化待建 |

## 从哪块板开始

- **嵌入式新手，或想吃透主线 bring-up** — 从 [RK3506B](RK3506B_ROADMAP) 进。它是三块板里教程最完整、验证最透的一块：主线 U-Boot 2026.07 + Linux 7.1 启动链、SPI-NAND 可靠性、Buildroot 与 OpenWrt 都有完整的 [tutorial/](../tutorial/) 教程和 [真板日志](../logs/) 取证。学完你能独立维护一块 ARM32 板的板级支持。
- **做过 Linux BSP，想系统学驱动框架** — 从 [RK3568](RK3568_ROADMAP) 进。它假设你懂交叉编译和基础启动链，把精力集中在 AArch64 下的 platform driver、设备树绑定、中断与 DMA、USB/PCIe、DRM 这套标准驱动框架上。
- **做异构 / 媒体 / AI / Android 产品** — 从 [RK3588](RK3588_ROADMAP) 进。它不收零基础，要求先过它 §3 的六条自测（EL1/EL3、地址类型、设备树、probe 失败分析、perf、AArch64 产物隔离），然后从公共媒体地基进入 NPU / 媒体 / Android 三个方向之一。

> RK3506B 的主线启动链、设备树、有序补丁库、`forge` 编排器是三块板共用的前置课——已在它的 [tutorial/](../tutorial/) 建立起来，RK3568/RK3588 的 ROADMAP 不再重述，默认你已具备或会回头查。

## 状态怎么读

每份 ROADMAP 的每一章都标了四档状态，你可以据此判断"这节内容现在能不能学到东西"：

| 状态 | 含义 |
|---|---|
| 🟢 `verified` | 仓库已有真板证据（日志 + 产物 + 配置齐备），可由第二人在板上复现 |
| 🟡 `partial` | 工程基线已板上验证，课程化（章节、实践、证据挂接）仍在进行 |
| ⚪ `planned` | 教学目标与课程顺序已定义，但 rk-forge 尚未建立真板 target |
| 🔴 `blocked` | 明确卡在某项硬依赖（如某闭源 blob、某驱动未上游） |

一句话："跑通过一次" ≠ `verified`，"厂商 SDK 能跑" ≠ rk-forge `verified`。每项能力的状态，都和仓库里对应的 [真板日志](../logs/) 与 [教程](../tutorial/) 一一对应——查不到证据的，就只能停在 `planned`。

## 路线之间的边界

这三条让三份 ROADMAP 各有清晰职责、不重复、不模糊：

1. RK3506B 的 **SPI-NAND/UBIFS 可靠性**主课不复制到 RK3568——后者走 eMMC/SD，存储课题完全不同；
2. RK3568 **不写成缩小版 RK3588**——NPU、复杂 ISP/VPU、Android 属于 RK3588 的方向课；
3. 三块板可以借鉴方法，但**不默认共享**任何固件、U-Boot、ATF、设备树、内核配置、模块或镜像——SoC 不同，每一块板都要独立建立证据。

---

rk-forge 走 mainline-first：主线 Linux + 主线 U-Boot + 主线设备树 + 最小化的 `rkbin` blob。想看启动链里哪里闭源、哪里开源，进 [诚实 blob 政策](../blobs.md)；想看 vendor BSP 和主线移植的逐项差距，进 [差距对照](../sdk-diff.md)。
