---
title: 踩坑日记
---

<PageHeader icon="🕳️" title="踩坑日记" description="RK3506 这条链踩的一路坑——按故障域分篇，还原时间线 + 弯路 + 被推翻的结论 + 板上证据" />

RK3506 这条 bring-up 链不是一路顺风的。rkbin SPL 背后藏着三个不可违背的隐性契约；SPI-NAND 的读写加上 loader 弱写 rootfs，演成了一整部 saga；有一阵子板子一写就 external abort，翻了半天才发现是 reserved-memory 没给 OP-TEE 留对；USB 要调 PHY，WiFi 要移植 out-of-tree 驱动……

这些坑全都老老实实记在这里，按**故障域**分篇（非一坑一文件），每篇内部按时间线还原该域的坑 + 走过的弯路 + **被推翻的结论** + 每步板上证据（log 行）。踩坑不是失败，是路标——你在教程里看到的每一段"我们为什么这么改"，背后多半挂着一个曾经把我们按在地上摩擦的坑。

> 与其他层分工：[工程笔记](../notes/) = raw 按天流水（取证源）；本目录 = 回溯提炼的完整叙事 + canonical 结论；[教程](../tutorial/) = 面向读者的成功路径。完整的篇-坑号对照表见 [pitfalls/README](./README)。

<ChapterNav>
  <ChapterLink num="01" href="01-rkbin-spl-contracts">跟 rkbin SPL 死磕：三个隐性契约</ChapterLink>
  <ChapterLink num="02" href="02-busybox-init-devtmpfs">busybox init 的两道暗门</ChapterLink>
  <ChapterLink num="03" href="03-build-verification">构建侧的两个方法论坑</ChapterLink>
  <ChapterLink num="04" href="04-sfc-nand-saga">SPI-NAND 写崩 saga（最重一篇）</ChapterLink>
  <ChapterLink num="05" href="05-secure-mem-reservation-imprecise-abort">reserved-memory 漏 → external abort</ChapterLink>
  <ChapterLink num="06" href="06-usb-bringup-usb2phy-dwc2">USB2PHY + DWC2 bring-up</ChapterLink>
  <ChapterLink num="07" href="07-wifi-out-of-tree-port">WiFi out-of-tree 移植（RTL8733BU）</ChapterLink>
</ChapterNav>
