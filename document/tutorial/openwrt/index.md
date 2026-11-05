---
title: OpenWrt
---

<PageHeader icon="🌐" title="OpenWrt" description="--rootfs=openwrt：给 RK3506 装一套真能 opkg 的发行版" />

rootfs 那一卷把 buildroot 走到了头，rootfs 落进了 SPI-NAND、跨冷重启也持久了，loader 弱写的拉锯也画上了句号。不过 buildroot 给得了“一个 rootfs”，给不了“一套发行版”，朋友要的是板子上能 `opkg install` 现场装包、能开 LuCI、能像路由器一样随时加 kmod，这样的东西只有 OpenWrt 有。这一卷咱们就把 OpenWrt 作为 `--rootfs=openwrt` profile 移植进 rk-forge，和 buildroot 并排放着：不借它的 kernel（vermagic 不让），OpenWrt 自建 musl 的 kernel+rootfs，rk-forge 那边复用已验过的主线 U-Boot，加上纯 Python 的打包链。NAND 走 from-source 的置备，SD 走的是 ext4，两条路咱们都在板子上跑到了 `root@OpenWrt:~#`。

<ChapterNav>
  <ChapterLink num="01" href="00_openwrt">OpenWrt：给 RK3506 装一套真能 opkg 的发行版</ChapterLink>
</ChapterNav>
