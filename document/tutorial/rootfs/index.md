---
title: 根文件系统
---

<PageHeader icon="📦" title="根文件系统" description="buildroot 出正规最小 rootfs，从 switch_root 到 login，再到 UBIFS + loader 弱写 saga" />

板子能启动到 console 了，但还跑不进 shell——缺一份能持久化的根文件系统。这一卷做三件事：用 buildroot 出一份正规的最小 rootfs、理清从 `switch_root` 到 `login:` 的 init 时序暗门、最后啃下 bringup 最深的一关——SPI-NAND 上 UBIFS 与 loader 弱写 saga。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：从 panic 到 login，rootfs 这条最深的路</ChapterLink>
  <ChapterLink num="02" href="01_buildroot">buildroot：出一份正规的最小 rootfs</ChapterLink>
  <ChapterLink num="03" href="02_init">init 时序：switch_root 到 login 的两道暗门</ChapterLink>
  <ChapterLink num="04" href="03_ubifs_loader_weakwrite">UBIFS 与 loader 弱写 saga：bringup 最深的一关</ChapterLink>
</ChapterNav>
