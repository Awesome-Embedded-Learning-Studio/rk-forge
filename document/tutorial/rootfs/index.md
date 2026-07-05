---
title: 根文件系统
---

<PageHeader icon="📦" title="根文件系统" description="buildroot 出正规最小 rootfs，从 switch_root 到 login，再到 UBIFS + loader 弱写 saga" />

板子能启动到 console 了，但还跑不进 shell，缺一份能持久化的根文件系统。boot 系列 Ch3 结尾那行 `panic: Unable to mount root fs` 还杵在那儿，这个 rootfs 系列就是来消掉它的。一路下来我们先用 buildroot 出一份正规的、可维护的最小 rootfs，再理清从 `switch_root` 到 `login:` 这段 init 时序里的两道暗门，最后落在 SPI-NAND 上把 UBIFS 跑起来、把 loader 写我们小 rootfs 时那道位置无关的弱写治住。说句心里话，这一程比 boot 难得多，难不在"挂个文件系统"，难在挂上、持久、还写不崩。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：从 panic 到 login，rootfs 这条最深的路</ChapterLink>
  <ChapterLink num="02" href="01_buildroot">buildroot：出一份正规的最小 rootfs</ChapterLink>
  <ChapterLink num="03" href="02_init">init 时序：switch_root 到 login 的两道暗门</ChapterLink>
  <ChapterLink num="04" href="03_ubifs_loader_weakwrite">UBIFS 与 loader 弱写 saga：bringup 最深的一关</ChapterLink>
</ChapterNav>
