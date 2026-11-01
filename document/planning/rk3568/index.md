---
title: "RK3568 教学路线：AArch64 Linux 驱动与接口工程"
---

# RK3568 教学路线：AArch64 Linux 驱动与接口工程

> 状态：**partial**。RK3568（正点原子 ATK-DLRK3568 EVB1 DDR4 v1.0）已真机 boot 到 login：主线 kernel 7.1 + 主线 U-Boot + binman 自产 loader（零 vendor 工具），双 GMAC、eMMC、LCD ILI9881C、Panfrost Mali-G52、CAN、RTC、Goodix 触摸多外设板验；rootfs 走 buildroot Phase 2a 全功能栈（Qt6/Mesa/GStreamer/Weston）。课程化（章节、实践、证据挂接）仍在进行，板级 DT 正整理进有序补丁库（[boards/rk3568-atk/patches/](../../../boards/rk3568-atk/patches/)，内部代号 P4 工程债），WiFi 驱动（rtl8852bs）已接线集成、真机验证待做，VPU/NPU、PCIe/SATA 仍属 roadmap。

## 1. 路线承诺

RK3568 路线不重复 RK3506B 的 NAND bring-up，也不把 RK3588 的高级能力缩小一遍。它承担两项清晰任务：

1. 帮助学习者从 ARM32/Linux BSP 进入 AArch64、ATF 和 64 位用户系统；
2. 以真实外设为载体，系统学习 Linux 设备模型、标准驱动框架、DMA 和通用高速接口。

完成本路线后，学习者应能拿到原理图、datasheet、BSP 参考和一块新板，独立完成常见外设的 Linux 接入、调试、测试和交付。

## 2. 平台角色与边界

| 项目 | 本路线定义 |
|---|---|
| 目标 SoC | Rockchip RK3568，ARMv8-A / AArch64 |
| 具体开发板 | 正点原子 ATK-DLRK3568 EVB1 DDR4 v1.0 |
| 主角色 | 64 位通用 Linux 和驱动课程主平台 |
| 架构重点 | LP64、EL0–EL3、ATF、PSCI、64 位地址与 ABI |
| 驱动重点 | 设备模型、DT binding、IRQ、clock/reset/regulator、I²C/SPI、DMA、USB、PCIe、网络、基础 DRM |
| 用户系统 | Buildroot 教学系统；其他发行版只能在形成独立证据后增加 |
| 不承担 | RK3506B NAND 可靠性主课；RK3588 NPU、复杂 ISP/VPU、Android 产品主课 |

RK3568 与 RK3588 同为 AArch64，不代表二者能够共用 U-Boot、ATF、设备树、内核配置、模块、镜像或真板结论。

## 3. 适合谁学习

### 从 RK3506B 或其他 ARM32 BSP 进入

需要补：

- AArch64 工具链和 LP64；
- EL0–EL3 与 ATF；
- 64 位地址和 DMA 地址；
- cache 一致性；
- RK3568 具体启动存储和板级差异。

可以跳过：

- 交叉编译基本概念；
- U-Boot/Linux/rootfs 的通用定义；
- Git、补丁和基础日志阅读。

### 已经做过 Linux 驱动

通过自测后可以从 DMA、高速接口或 DRM 卷开始，但仍需完成：

- RK3568 基线证据；
- AArch64/ATF 对照；
- 板级资源与设备树审计。

### 直接进入

应具备：

- C 语言和基本数据结构；
- Linux 用户态编程；
- 进程、线程、文件、内存和并发基础；
- 能阅读简单原理图和芯片 datasheet。

本路线会补 Linux 驱动所需的最小内核基础，但不复制完整 Linux 基础教程。

## 4. 能力成长地图

| 阶段 | 学习者要解决的问题 | 阶段成果 |
|---|---|---|
| 理解平台 | ARM64 启动和 ARM32 有什么实质差异 | AArch64/ATF 启动图 |
| 掌握设备模型 | 怎样让内核发现并管理一个真实设备 | 规范的 platform driver |
| 掌握资源 | 怎样管理 GPIO、IRQ、clock、reset、regulator | 可正确上下电和响应中断的设备 |
| 掌握总线 | 怎样接入 I²C、SPI、UART 设备 | 使用标准子系统接口的驱动 |
| 掌握数据通路 | 怎样处理 DMA、USB、PCIe、网络 | 有性能数据的高速接口实验 |
| 掌握显示 | 怎样理解 DRM/KMS 显示对象 | 可解释的显示管线 |
| 掌握质量 | 怎样定位并证明驱动缺陷已经修复 | 驱动、测试、日志和文档交付 |

## 5. 课程编排

七个卷，二十章，外加三个候选毕业项目。第 19、20 章实为质量交付内容，按能力成长地图的「掌握质量」阶段单独成卷七，不随显示选修裁掉：

| 卷 | 章 | 主题 | 状态 |
|---|---|---|---|
| [卷一：AArch64 与系统基线](01-aarch64-baseline.md) | 第 1–4 章 | 平台全景、工具链/LP64、EL0–EL3 与 ATF/PSCI、U-Boot 与开发 rootfs | 🟡 partial — 真机 boot 已验 |
| [卷二：Linux 驱动地基](02-driver-foundations.md) | 第 5–7 章 | 字符设备、设备模型与 platform driver、设备树绑定 | ⚪ planned |
| [卷三：GPIO、中断、电源与时钟](03-gpio-irq-power-clock.md) | 第 8–10 章 | pinctrl/GPIO/input、GIC 与中断、clock/reset/regulator 与 runtime PM | 🟡 partial — 触摸/CAN/RTC 已板验 |
| [卷四：标准总线与真实设备](04-buses-real-devices.md) | 第 11–13 章 | I²C 与 regmap、SPI、UART/RS-485 与协议边界 | 🟡 partial — I²C（触摸）已板验 |
| [卷五：DMA 与高速接口](05-dma-highspeed.md) | 第 14–17 章 | DMAengine 与 cache 一致性、USB、PCIe/NVMe、GMAC/PHY/网络性能 | 🟡 partial — 双 GMAC 已板验；USB 待确认门、PCIe 未验、WiFi 待板验 |
| [卷六：显示与 HMI 选修](06-display-hmi.md) | 第 18 章 | DRM/KMS 入门 | 🟡 partial — LCD 与触摸已板验 |
| [卷七：驱动质量与交付](07-quality-delivery.md) | 第 19–20 章 | 驱动调试工具、把驱动做成可维护交付物 | ⚪ planned |
| [毕业项目](capstone-projects.md) | — | 驱动验证平台、轻量工业 HMI、PCIe/USB/网络综合设备 | ⚪ planned |

> 状态按全仓四档口径标注（见[三板教学路线](../index.md)）。真板已验的外设（双 GMAC、eMMC、LCD、触摸、CAN、RTC）是工程基线，对应卷的课程化（章节、实践、证据挂接）仍在进行。

## 6. 候选毕业项目

每位学习者选择一个主项目，不要求覆盖所有接口，三个候选见[毕业项目](capstone-projects.md)。

## 7. 结课标准

学习者必须能够：

1. 解释 AArch64、ATF、PSCI 与 Linux 的交接；
2. 严格区分 ARM32/ARM64 工具链、sysroot、rootfs 和模块；
3. 编写一个规范的 platform/I²C/SPI 等真实驱动；
4. 正确管理 IRQ、GPIO、clock、reset 和 regulator；
5. 使用标准子系统接口而不是只暴露私有字符设备；
6. 完成 DMA 或一个高速接口实验；
7. 使用 ftrace/perf/dynamic debug 定位问题；
8. 交付驱动、设备树、测试、日志和已知限制；
9. 完成一个毕业项目最小版本。

## 8. 硬件确认门

以下事项中，开发板型号（ATK-DLRK3568 EVB1 DDR4 v1.0）、DRAM、eMMC、调试串口、以太网、显示（LCD ILI9881C）和触摸已在真板确认；其余仍待确认的，相应章节保持 `planned`：

- 具体开发板型号和 PCB 版本；
- DRAM 容量；
- eMMC/SD/SPI Flash 等启动存储；
- 调试串口和烧录入口；
- 可长期使用的以太网、USB、PCIe、显示接口；
- 配套屏幕、触摸和扩展设备；
- 厂商 BSP/SDK、U-Boot、ATF 和 Linux 基线版本；
- 真板数量和自动化验证条件。

## 9. 明确不讲或推迟

- 不把 RK3568 写成稳定/完整支持——当前是 `partial`（真机 boot + 多外设板验），但板级 DT 仍在整理进补丁库（P4 工程债）、WiFi 驱动真机验证未做、VPU/NPU 未接，连续稳定性验证未完；
- 板卡型号已确认（ATK-DLRK3568），pinout/分区/镜像布局见 [boards/rk3568-atk/](../../../boards/rk3568-atk/)，但未板上验证的接口不写结论；
- 不复制 RK3506B 的 SPI-NAND saga；
- 不从头复制完整 Linux/C 基础课；
- 不把字符设备 demo 当成驱动课程终点；
- 不一次覆盖所有内核子系统；
- 不把 RK3568 变成缩小版 RK3588；
- 不把 NPU、复杂 ISP/VPU、Android 放进本路线主干；
- 不默认与 RK3588 共用二进制产物；
- eMMC 烧录与量产链（RKDevTool/upgrade_tool）不单独成课——工具操作按仓库 QUICK_START，深度量产课题暂缓；5G 拨号待硬件确认门。
