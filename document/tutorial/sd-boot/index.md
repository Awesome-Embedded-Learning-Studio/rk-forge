---
title: SD 卡启动
---

<PageHeader icon="💾" title="SD 卡启动" description="SPI-NAND 之外的第二条启动路：RKFW 格式 + 手动引导到 autoboot" />

SPI-NAND 之外的第二条启动路。RK3506 这块板的 SD 卡启动有个硬前提咱们得讲在前面：裸 `dd` 出的镜像 ROM 不认，**必须打成 RKFW 格式**（它和 NAND 的 `update.img` 是同一种容器，RK 工具认的就是这个）。本卷咱们分两步走。头一步咱们在 SD-1 里靠 U-Boot 提示符下的手动 `mmc read` 把 kernel 拉起来、挂上 ext4 rootfs，一路跑到了 shell。接着把那几行手动引导烤进一个独立的 SD defconfig，做成 SD-2 的 autoboot，上电零输入就直接到了 shell。板上三轮验证咱们全跑过了，kernel 和 rootfs 都是从 SD 的 ext4 上来的，咱们没走 NAND、也没碰上 panic。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：SD 卡，第二条启动路</ChapterLink>
  <ChapterLink num="02" href="01_sd1_manual">SD-1：手动引导 SD 卡到 shell</ChapterLink>
  <ChapterLink num="03" href="02_sd2_autoboot">SD-2：autoboot，上电零输入到 shell</ChapterLink>
</ChapterNav>
