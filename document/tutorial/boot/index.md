---
title: 引导启动
---

<PageHeader icon="🚀" title="引导启动" description="主线 U-Boot 2026.07-rc4 + 主线 Linux 7.1，从 rkbin 把 DDR 点亮一路跑到 shell" />

整条启动链最关键的事实，藏在 rkbin 那段闭源 blob 的前后分界上。rkbin 之前的那些环节，咱们借原厂 blob 把 DDR 点亮。rkbin 之后的环节（从 U-Boot 到 init），每一行的源码都能在主线仓库里翻到、能 `git bisect`、能打补丁。开源与闭源的分界线就画在 rkbin 之后。本卷要做的，就是把分界线之后的那段链路一条主线走到底：U-Boot 跑到 `=>` 提示符，内核认出咱们手写的板级设备树。再往后接 rootfs、跑到 `rk3506 login:` 的那一段，就归后面的几卷了。

> 诚实地讲：所谓“纯主线 boot”咱们目前还做不到，卡点就在 rkbin 的这段 DDR init，咱们自己写 SPL 去替代它的尝试（内部叫方案 A）还在趟。所以咱们的 U-Boot 和 kernel 是纯主线，但启动链最前段仍借了原厂 blob。差距的量化清单见 [差距对照](../../sdk-diff.md)。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：为什么是 RK3506，为什么 mainline-first</ChapterLink>
  <ChapterLink num="02" href="01_toolchain">工具链：arm-linux-gnueabihf</ChapterLink>
  <ChapterLink num="03" href="02_uboot_rkbin">U-Boot 与 rkbin：在闭源 blob 的咽喉上拔河</ChapterLink>
  <ChapterLink num="04" href="03_kernel">内核：补上那块属于咱们的板级设备树</ChapterLink>
</ChapterNav>
