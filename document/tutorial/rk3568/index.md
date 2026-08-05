---
title: RK3568 教程
---

<PageHeader icon="🧩" title="RK3568 主线移植" description="ATK-DLRK3568：从 ARM32 进 AArch64，主线 kernel 7.1 真机 boot 到 login" />

RK3568 是这条阶梯的中间级——从 RK3506B 的 ARM32 / 主线 bring-up，往上走到 AArch64、ATF 和标准 Linux 驱动框架。它的主线支持很成熟（Collabora 早就伺候明白），所以咱们在这块板上的活，和 RK3588 一样不是"补主线缺的驱动"，而是"把 vendor SDK 拔掉、主线 U-Boot + 主线 kernel + binman 自产 loader 重新走一遍"，顺带学 AArch64 那一套（EL0–EL3、ATF、PSCI、64 位地址）。

> 诚实地说：RK3568 现在是 `partial`，而且比 RK3588 更靠前——教程目前**只有启动首启这一章是真机验证过的**。ROADMAP 里规划的那套完整的 AArch64 驱动框架课（字符设备、platform driver、DT binding、IRQ、DMA、I²C/SPI、DRM……）还没课程化；板级设备树的 8 个子系统（PMIC/eth/audio/touch/LCD/WiFi）移植虽然做了，**但目前是 working-tree delta，没正式 patch 化进 `patches/rk3568-atk/`**——这块板要能被第二人 clone 复现，得先把这个 patch 化的工程债还上（见 [sdk-diff-rk3568](../../sdk-diff-rk3568)）。所以本卷是 MVP：启动章能读，其余标"建设中"。

<ChapterNav>
  <ChapterLink num="00" href="00_roadmap">路线图：RK3568 在三板阶梯里的位置</ChapterLink>
  <ChapterLink num="01" href="01_boot">引导启动：主线 7.1 真机首启到 login</ChapterLink>
  <ChapterLink num="02" href="02_peripherals">板级 DT 八子系统：从"能启动"到"能用"</ChapterLink>
</ChapterNav>

> 🚧 建设中：板级 DT 八子系统已经写进 [02 章](02_peripherals)（双 GMAC / LCD / Panfrost / 触摸 / CAN / RTC / PMIC / audio），但那一章对应的板 DT 仍是 working-tree delta，待 patch 化（P4）才能 clone 复现；rtl8852bs WiFi 移植、buildroot Phase 2a 全栈（Qt6/Mesa/GStreamer/Weston）也还在 [notes/40–42](../../notes/) 里，等真机数据补齐后补成章节。
