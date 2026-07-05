---
title: SD 卡启动
---

<PageHeader icon="💾" title="SD 卡启动" description="SPI-NAND 之外的第二条启动路：RKFW 格式 + 手动引导到 autoboot" />

SPI-NAND 之外的第二条启动路。RK3506 这块板的 SD 卡启动有个硬前提要先讲清楚：裸 `dd` 出的镜像 ROM 不认，**必须打成 RKFW 格式**（和 NAND 那个 `update.img` 同一种容器，RK 工具只认这个）。本卷分两步走。先在 SD-1 里靠 U-Boot 提示符下手动 `mmc read` 把 kernel 拉起来、挂上 ext4 rootfs，跑通到 shell；再把那几行手动引导烤进一个独立的 SD defconfig，做成 SD-2 的 autoboot，上电零输入直接到 shell。板上三轮验证全过，kernel 和 rootfs 都是从 SD ext4 上来的，没走 NAND、也没 panic。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：SD 卡，第二条启动路</ChapterLink>
  <ChapterLink num="02" href="01_sd1_manual">SD-1：手动引导 SD 卡到 shell</ChapterLink>
  <ChapterLink num="03" href="02_sd2_autoboot">SD-2：autoboot，上电零输入到 shell</ChapterLink>
</ChapterNav>
