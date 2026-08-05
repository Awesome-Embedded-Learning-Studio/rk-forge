---
title: RK3588 教程
---

<PageHeader icon="🦾" title="RK3588 主线移植" description="iTOP-RK3588 / topeet 板：从 bootloop 第 0 关一路跑到 Ubuntu GNOME 桌面" />

RK3588 是这条阶梯里最重的一块板——八核 big.LITTLE、Mali-G610、NPU、VPU 全挤在一颗硅上。它的主线支持比 RK3506 成熟得多（Collabora 的旗舰），所以咱们在这块板上要对付的，不是"主线缺驱动"，而是"主线都有，可当你把 vendor 那整套拔掉、换上主线重新走一遍时，哪些接口和时机会让板子起不来"。这条路上最硬的四块骨头，就是本卷的四章：启动链那场看不见报错的 bootloop、LCD 那条拖了四个镜像才出图的 saga、GPU 固件的 early-probe 时机、还有把 Ubuntu 桌面塞进 eMMC 的 rootfs 打包。

> 前置课不重讲：主线 bring-up 是怎么回事、rkbin 这段闭源 blob 卡在哪、`forge` 编排器怎么用、buildroot / init 的时序坑——这些在 RK3506B 的 [教程](../boot/) 里已经建起来了。本卷默认你读过那条主线，或者会回头查，咱们只讲 RK3588 特有的增量。

> 诚实地说：RK3588 现在是 `partial`——真机已经 boot 到 Ubuntu GNOME 桌面、GPU / LCD / 触摸都板上点过；但 LCD 的 VOP2 hard-lock 修复当前还是候选镜像，连续冷热启动的稳定性没闭环，所以涉及显示的章节咱们会标清楚"出图，但不宣称稳定"。WiFi/BT、NPU、VPU、摄像头这些仍是 roadmap，本卷不碰，等真机数据齐了再补。

<ChapterNav>
  <ChapterLink num="00" href="00_roadmap">路线图：RK3588 在三板阶梯里的位置</ChapterLink>
  <ChapterLink num="01" href="01_boot">引导启动：bootloop 第 0 关 + 主线 SPL + autoboot</ChapterLink>
  <ChapterLink num="02" href="02_lcd">LCD 移植 saga：TC358775 桥 IC 与 9 条 gotcha</ChapterLink>
  <ChapterLink num="03" href="03_gpu">GPU 固件：Panthor early probe 与内建 raw 固件</ChapterLink>
  <ChapterLink num="04" href="04_rootfs">Ubuntu rootfs：从 ubuntu-base 到 GNOME 桌面</ChapterLink>
  <ChapterLink num="05" href="05_stability">稳定性调试：抓看不见的 hard-lock（方法论）</ChapterLink>
</ChapterNav>
