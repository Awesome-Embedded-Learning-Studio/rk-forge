---
title: SD 卡启动
---

<PageHeader icon="💾" title="SD 卡启动" description="RKFW 格式的第二条启动路——从手动引导到上电零输入 autoboot" />

SPI-NAND 之外的第二条启动路。RK3506 这块板的 SD 卡启动有个硬前提：裸 `dd` 出的镜像 ROM 不认，**必须打成 RKFW 格式**。这一卷先手动把 SD 卡一步步引导到 shell（SD-1），再做成上电零输入的 autoboot（SD-2），板上三轮验证全过——kernel + rootfs 都从 SD ext4 起。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：SD 卡，第二条启动路</ChapterLink>
  <ChapterLink num="02" href="01_sd1_manual">SD-1：手动引导 SD 卡到 shell</ChapterLink>
  <ChapterLink num="03" href="02_sd2_autoboot">SD-2：autoboot，上电零输入到 shell</ChapterLink>
</ChapterNav>
