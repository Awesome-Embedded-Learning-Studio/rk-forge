---
title: 环境准备
---

<PageHeader icon="🧰" title="环境准备" description="WSL2 + usbipd：在任何一块板开工之前，先有一个干净的开发环境" />

这一卷与板无关，三块板（RK3506B / RK3568 / RK3588）共用：rk-forge 的整条构建链跑在 Windows 上的 WSL2 里，串口看启动日志、烧录前的设备直通也都从 host 这边过。开工之前先把它走一遍，后面所有章节的 host 环境就不再是变量。

两章的顺序就是做事的顺序：先把 WSL2 本身搭干净——装发行版、隔离 Windows PATH、配 Mirrored 网络共用 Windows 代理、VS Code 接入；再把 usbipd-win 配起来，让 WSL 摸得到插在 Windows 上的 USB 设备。仓库根部的 [QUICK_START](../../../QUICK_START.md) 列着 forge 的 host 构建依赖清单，环境装完可以从那里进。

<ChapterNav>
  <ChapterLink num="01" href="00_wsl2">想要真 Linux：WSL2 环境搭建</ChapterLink>
  <ChapterLink num="02" href="01_usbipd">usbipd-win：把 USB 设备直通进 WSL</ChapterLink>
</ChapterNav>
