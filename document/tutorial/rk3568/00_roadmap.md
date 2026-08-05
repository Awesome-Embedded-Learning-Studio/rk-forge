# Ch0 — RK3568：阶梯的中间级

> 这一章不敲命令，先把 RK3568 在咱们这条 bring-up 阶梯里的位置、和上下两级的关系、以及本卷当前的诚实状态（只有启动章）交代清楚。

## RK3568 是块什么板，在阶梯里的位置

RK3568 是四核 Cortex-A55 的 AArch64 SoC，主打中端。它在咱们这条阶梯里占的是中间级：从 RK3506B 的 ARM32 / 主线 bring-up 地基往上，第一次进 AArch64、第一次碰 ATF（ARM Trusted Firmware）和 PSCI、第一次系统学 Linux 的标准驱动框架（设备模型、platform driver、DT binding、IRQ、DMA、I2C/SPI/UART）。再往上 RK3588 那级，才是异构、GPU/媒体/AI 这些产品级课题。

RK3568 的主线支持比 RK3506 成熟太多——pinctrl/clk/GIC/USB/PCIe/GMAC/GPU（Panfrost）/VPU（Hantro+rkvdec2）主线都有。所以这块板的移植，性质是「主线都有，把 vendor 那套拔掉、主线重新走一遍，再把板级 DT 写出来」。和 RK3588 比它的启动链简单一截：vendor 的 `rk356x_spl` 没有 RK3588 那个基址迁移的坑，用 vendor SPL + 主线 U-Boot 就能起，不需要切主线 SPL。

## 和上下两级的关系：不重复，只增量

三板阶梯的纪律是一条：每块板独立建立证据链，不默认共享任何固件、U-Boot、ATF、设备树、内核配置或镜像。所以本卷不重讲 RK3506B 已建的东西——主线 bring-up、rkbin 卡点、`forge` 编排器、buildroot/init 时序——这些在 [RK3506B 教程](../boot/) 里。RK3568 的增量是 AArch64 那一层：第一次有 ATF（BL31），第一次走 binman 自产 loader（零 vendor 打包工具），eMMC 而不是 SPI-NAND 做启动存储。

反向边界也有一条：RK3568 不写成缩小版 RK3588。NPU、复杂 ISP/VPU、Android 这些产品级课题归 RK3588 那级，RK3568 的主线是「AArch64 + 标准驱动框架」，不背产品化的锅。

## 本卷当前的诚实状态：MVP，只有启动章

这里必须说清楚，免得你读下去以为 RK3568 教程已经齐了。RK3568 的 [ROADMAP](../../planning/RK3568_ROADMAP) 规划了一条完整的课（A0–A5，从 AArch64 启动到 DRM 显示、驱动调试、可维护交付，20 章），但课程化目前只走到了启动首启这一章。其余的——GPIO/IRQ/clock、I2C/SPI/UART、DMA、USB/PCIe、双 GMAC、DRM 显示、驱动调试——ROADMAP 定义了教学目标和顺序，但还没写成 tutorial 章节。

更硬的一条约束：RK3568 的板级设备树（PMIC、双 GMAC、RK809 audio、Goodix 触摸、LCD、CAN、RTC 等八个子系统）虽然在真机上移植并验证了，但目前是 `third_party/src/rk3568-atk/` 里的 working-tree delta，没有正式 quilt 化进 `patches/rk3568-atk/linux/series`（那个 series 现在只带 rtl8852bs WiFi 的接线）。也就是说，第二人 `forge setup` clone 下来，复现不了这些外设——这是 RK3568 落后 RK3588（已完整 patch 化）一个工程化阶段的地方。把这个债还上（内部叫 P4）是 RK3568 教程继续往下写的前置。

还有几个真机上没收尾的尾巴：WiFi（rtl8852bs）只有 SDIO 总线枚举、驱动没移植；RK809 audio 的 hp-det GPIO 和 i2s1 mclk 冲突、声卡没 probe；LCD 的 panel IC 在两篇笔记里说法不一致（一篇写 HX8394、一篇写 ILI9881C），写真板教程前得在真机上核对清楚。

## 本卷带你走到哪

| 章 | 主题 | 状态 |
|---|---|---|
| [01 引导启动](01_boot) | 主线 7.1 + binman 自产 loader，真机首启到 login | ✅ 真机验证 |
| [02 板级 DT 八子系统](02_peripherals) | PMIC/双 GMAC/audio/touch/LCD/GPU/CAN/RTC | 🟡 板验，DT 待 P4 patch 化 |
| （后续）WiFi rtl8852bs | vendor 851 文件驱动移植到 7.1 | 🚧 待移植 |
| （后续）buildroot 全栈 | Qt6/Mesa/GStreamer/Weston | 🚧 待真机验证 |

所以本卷现在重点是启动首启那一章。咱们从 BootROM 跑到 busybox `login:` 那条链开始。
