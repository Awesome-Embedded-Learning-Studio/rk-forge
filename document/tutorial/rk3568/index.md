---
title: RK3568 教程
---

<PageHeader icon="🧩" title="RK3568 主线移植" description="ATK-DLRK3568：从 ARM32 进 AArch64，主线 kernel 7.1 板上 boot 到 login" />

RK3568 在阶梯里占的是中间级，咱们从 RK3506B 的 ARM32 与主线 bring-up 往上走，要进的是 AArch64、ATF 和标准 Linux 驱动框架。它的主线支持很成熟（Collabora 早就伺候明白），所以咱们在这块板上的活，和 RK3588 一样不是给主线补缺的驱动。咱们干的是把原厂 SDK 拔掉，换成主线的三件套：U-Boot、kernel 加 binman 自产的 loader，咱们把整条链重走一遍。顺带咱们把 AArch64 的家底也学了，像 EL0–EL3、ATF、PSCI、64 位地址这些。

> 诚实地说：RK3568 现在是 `partial` 的形态。00、01、02 三章咱们已经写成，都有板上的串口证据撑着。ROADMAP 里还规划了一整套 AArch64 驱动框架课（字符设备、platform driver、DT binding、IRQ、DMA、I²C/SPI、DRM……），那些咱们还没课程化。板级设备树的 8 个子系统（PMIC、双 GMAC、audio、触摸、LCD、GPU、CAN、RTC）移植做了、板验了，**但板级 DT 咱们还留在 working-tree delta 的状态，正式的 patch 化还没做进 `patches/rk3568-atk/`**。这笔工程债咱们记在 [sdk-diff-rk3568](../../sdk-diff-rk3568) 里，咱们还清它之后，别人 clone 下来的就是同一块板。本卷还是 MVP 的形态，三章咱们写定了，其余标了建设中。

<ChapterNav>
  <ChapterLink num="00" href="00_roadmap">路线图：RK3568 在三板阶梯里的位置</ChapterLink>
  <ChapterLink num="01" href="01_boot">引导启动：主线 7.1 板上首启到 login</ChapterLink>
  <ChapterLink num="02" href="02_peripherals">板级 DT 八子系统：从"能启动"到"能用"</ChapterLink>
</ChapterNav>

> 🚧 建设中：板级 DT 八子系统咱们已经写进 [02 章](02_peripherals)（双 GMAC / LCD / Panfrost / 触摸 / CAN / RTC / PMIC / audio），那一章对应的板 DT 仍是 working-tree delta，咱们等 patch 化（P4）落定后第二人才 clone 得出同一块板。rtl8852bs WiFi 的驱动已接线进构建、板上验证咱们还没做，buildroot Phase 2a 全栈（Qt6/Mesa/GStreamer/Weston）的素材也还在 [notes/40–42](../../notes/) 里躺着，素材齐了咱们再补成章节。
