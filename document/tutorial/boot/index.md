---
title: 引导启动
---

<PageHeader icon="🚀" title="引导启动" description="主线 U-Boot 2026.07-rc4 + 主线 Linux 7.1，从 rkbin 把 DDR 点亮一路跑到 shell" />

这条启动链最关键的事实，藏在 rkbin 这一段闭源 blob 后面——rkbin 之前，我们借厂商 blob 把 DDR 点亮；rkbin 之后，从 U-Boot 到 init，每一行都能在主线仓库里翻到源码、能 `git bisect`、能打补丁。换句话说，闭源与开源的分界线就画在 rkbin 之后。这一章系列就是把分界线之后那段链路一条主线走到底：U-Boot 跑到 `=>` 提示符、内核认出我们手写的板级设备树。再往后接 rootfs、上 `rk3506 login:`，是后面几章的事。

> 诚实地说：所谓"纯主线 boot"目前还做不到，卡点就在 rkbin 这段 DDR init（自己写 SPL 替代——内部叫方案 A——还在趟）。所以我们的 U-Boot 和 kernel 是纯主线，但启动链最前段仍借了厂商 blob。差距有多大、还差什么，见 [差距对照](../../sdk-diff)。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：为什么是 RK3506，为什么 mainline-first</ChapterLink>
  <ChapterLink num="02" href="01_toolchain">工具链：arm-linux-gnueabihf</ChapterLink>
  <ChapterLink num="03" href="02_uboot_rkbin">U-Boot 与 rkbin：在闭源 blob 的咽喉上拔河</ChapterLink>
  <ChapterLink num="04" href="03_kernel">内核：补上那块属于我们的板级设备树</ChapterLink>
</ChapterNav>
