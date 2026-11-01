---
title: "RK3506B 教学路线：从主线 BSP 到可靠工业设备"
---

# RK3506B 教学路线：从主线 BSP 到可靠工业设备

> 状态：**partial（课程规划）**。仓库已经拥有 AES-RK3506B 的主线 U-Boot、Linux、SPI-NAND/UBIFS、SD、Buildroot、OpenWrt、外设和真板日志基线；本文件规划如何把这些工程成果组织成课程。单章是否完成仍须以对应配置、构建产物和真板证据为准。

## 1. 路线承诺

RK3506B 路线不以“烧录一个 rootfs”作为终点，而是训练学习者把一块资料不完整、带有厂商启动约束的开发板，做成一个：

- 能解释启动链；
- 能从源码重复构建；
- 能定位 bootloader、内核、设备树、rootfs 和存储故障；
- 能可靠烧录、冷重启和恢复；
- 能接入网络与工业接口；
- 能长期维护补丁和证据；
- 最终可以承载工业网关、OpenWrt 路由或数据采集业务的嵌入式系统。

完成本路线后，学习者的角色应从“Linux 系统使用者”提升为“能够独立维护 ARM32 板级支持的 BSP 工程师”。

## 2. 平台角色与边界

| 项目 | 本路线定义 |
|---|---|
| 目标 SoC | Rockchip RK3506B，ARMv7-A / 32 位 |
| 当前课程载体 | AES-RK3506B |
| 系统重点 | 主线优先 bring-up、SPI-NAND/UBIFS、SD、Buildroot、OpenWrt、工业接口 |
| 架构重点 | armhf ABI、ARMv7-A 异常模型、Cortex-A7 SMP |
| 工程重点 | 版本 pin、补丁序列、BSP/Mainline 差距、可复现构建、真板取证 |
| 闭源边界 | DDR、SPL/TPL、TEE 等 rkbin 产物；必须明确记录来源和配对约束 |
| 不承担 | AArch64 EL0–EL3、PCIe 高速驱动、复杂媒体/NPU/Android 主课程 |

课程只能把 AES-RK3506B 的真板结论用于该板卡。其他 RK3506/RK3506B 板卡即使 SoC 相同，也必须重新确认设备树、存储、接口和启动配置。

## 3. 适合谁学习

### 直接进入者

应具备：

- Linux 命令行和 Git 基础；
- C 语言、指针、结构体和基本 Makefile 能力；
- 能阅读简单原理图和芯片 datasheet；
- 理解进程、文件系统、设备文件和网络接口的基本概念。

不要求提前会：

- U-Boot；
- Linux 内核移植；
- NAND、UBI、UBIFS；
- Rockchip 打包格式；
- OpenWrt 平台移植。

### 已学过其他 Linux BSP 的学习者

可以跳过通用的 Linux、C 和交叉编译入门，从以下内容开始：

1. Rockchip 启动链与 rkbin；
2. RK3506B 的 ARM32 与板级设备树；
3. SPI-NAND/UBI/UBIFS 可靠性；
4. Buildroot/OpenWrt 双系统路线；
5. 工业接口与毕业项目。

## 4. 能力成长地图

| 阶段 | 学习者要解决的问题 | 阶段成果 |
|---|---|---|
| 读懂基线 | 板子实际经过哪些启动阶段 | 启动链图和证据索引 |
| 掌控启动 | 如何替换并验证 U-Boot、内核、DTB | 可复现的主线启动链 |
| 掌控内核与设备树 | 如何把 SoC 支持落成一块具体板 | 板级设备树与有序补丁库 |
| 掌控存储 | 为什么 NAND 能读却未必可靠写 | 可恢复、可压力验证的 UBIFS 系统 |
| 掌控系统 | 如何形成自己的产品 rootfs | Buildroot 产品系统或 OpenWrt 网络系统 |
| 掌控硬件 | 如何接通网络和工业接口 | 可持续运行的接口服务 |
| 掌控交付 | 如何让第二个人复现并验收 | 版本、补丁、日志和测试闭环 |

## 5. 课程编排

七个卷，十七章，外加三个候选毕业项目：

| 卷 | 章 | 主题 | 状态 |
|---|---|---|---|
| [卷一：读取真板，而不是背诵命令](01-read-the-board.md) | 第 1–2 章 | 板上家当、两条启动路线、启动链总图、ARMv7-A 与 armhf | 🟡 partial |
| [卷二：掌控 Rockchip 启动链](02-boot-chain.md) | 第 3–4 章 | rkbin 闭源边界、U-Boot、FIT 与启动策略 | 🟡 partial |
| [卷三：主线内核、设备树与补丁](03-mainline-kernel-dt.md) | 第 5–6 章 | 从 SoC 支持到板级设备树、有序补丁与主线差距 | 🟡 partial |
| [卷四：SPI-NAND 与可靠存储](04-spinand-storage.md) | 第 7–10 章 | MTD/UBI/UBIFS、首启置备、断电与长跑可靠性 | 🟡 partial |
| [卷五：构建自己的用户系统](05-userland.md) | 第 11–12 章 | Buildroot 产品系统、OpenWrt 网络设备 | 🟡 partial |
| [卷六：工业接口与网络](06-industrial-io.md) | 第 13–15 章 | 双网口 GMAC/PHY、I²C/SPI/UART 与 RMIO、USB/Wi-Fi/音频选修 | 🟡 partial |
| [卷七：工程交付与真板取证](07-delivery-evidence.md) | 第 16–17 章 | 可复现构建与回归、怎样证明一项能力已经完成 | 🟡 partial |
| [毕业项目](capstone-projects.md) | — | 工业双网口协议网关、OpenWrt 边缘路由、数据采集终端 | ⚪ planned |

> 各卷状态按全仓四档口径标注（`verified` / `partial` / `planned` / `blocked`，见[三板教学路线](../index.md)的状态说明）。RK3506B 整线工程基线已板上验证、课程化在进行，故各卷标 `partial`；升 `verified` 以每章真板证据补齐为准。

## 6. 候选毕业项目

每位学习者只需完成一个主项目，三个候选见[毕业项目](capstone-projects.md)。

## 7. 结课标准

完成路线不以“所有命令都执行过”为标准。学习者必须能够：

1. 独立说明 RK3506B 启动链及 rkbin 边界；
2. 从干净源码重复构建 U-Boot、Linux、DTB 和所选 rootfs；
3. 根据日志把故障定位到正确阶段；
4. 解释 SPI-NAND、UBI 和 UBIFS 的分层；
5. 完成多轮冷重启和存储恢复验证；
6. 接入至少一种工业接口和一种网络能力；
7. 交付一个毕业项目最小版本；
8. 保存版本、产物、日志、测试和已知限制。

## 8. 明确不讲或推迟

- 不把其他 RK3506 板卡写成已经兼容；
- 不用 RK3506B 课程代替完整 Linux/C 基础课；
- 不把闭源 rkbin 描述成开源；
- 不承诺无 blob 的纯主线启动；
- 不把显示、CAN、蓝牙、蜂窝网络等未形成稳定证据的能力列为必修；
- AMP（A7+M0 多核异构）：主线 U-Boot/DT 对其支持未成熟，**诚实暂缓**——卷一第 2 章只留概念一条，不假装主线已支持（vendor 实现判断留档内部备忘）；
- 快启 HMI（3 秒启动 + LVGL）：暂缓——先测量后裁剪的思路留在卷五产品系统里，独立快启课题未立；
- 不在本路线展开 AArch64、RK3588 媒体、NPU、GPU 或 Android；
- 不为了多平台抽象破坏现有 AES-RK3506B 基线。
