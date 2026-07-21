---
title: OpenWrt
---

<PageHeader icon="🌐" title="OpenWrt" description="--rootfs=openwrt：给 RK3506 装一套真能 opkg 的发行版" />

rootfs 那一卷把 buildroot 这条路走到头了——rootfs 落进 SPI-NAND、跨冷重启持久、loader 弱写 saga 也收口。但 buildroot 给得了"一个 rootfs"，给不了"一套发行版"：朋友要的是板子上能 `opkg install` 现场装包、能开 LuCI、能像路由器一样随时加 kmod，这套只有 OpenWrt 有。这一卷就把 OpenWrt 作为 `--rootfs=openwrt` profile 移植进 rk-forge，和 buildroot 并排——不借 kernel（vermagic 不让）、OpenWrt 自建 musl kernel+rootfs，rk-forge 复用已验过的主线 U-Boot + 纯 Python 打包链，NAND 走 from-source 置备、SD 走 ext4，两条路都板上跑到 `root@OpenWrt:~#`。

<ChapterNav>
  <ChapterLink num="01" href="00_openwrt">OpenWrt：给 RK3506 装一套真能 opkg 的发行版</ChapterLink>
</ChapterNav>
