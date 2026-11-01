---
title: "卷五：构建自己的用户系统"
---

# 卷五：构建自己的用户系统

> RK3506B 线 · 卷五 · 第 11–12 章 · [返回线总览](index.md)

### 第 11 章：Buildroot 产品系统

一句话：Buildroot 能编 rootfs ≠ 你有产品 rootfs——从「最小 busybox」到「带业务、带构建身份、能维护」。

要点：

- 纪律：改动全走 `BR2_EXTERNAL`，Buildroot 主树不碰（升级只 rebase 自己这一层）
- 外部工具链与 U-Boot/Linux 共用同一份（board.yaml `toolchain:`）；sysroot 不一致是经典坑
- 三层定制各管一摊：overlay（铺成品文件）/ post-build（打包前脚本）/ 自定义 package（源码→编译→装进 rootfs）
- BusyBox init + mdev：inittab 三类条目、`rcS` 按 S* 顺序、mdev 热插拔建节点，NAND 资源紧张板的轻量方案
- **产品 rootfs 必须带可追溯构建身份**（版本/commit/时间/配对版本注入 `/etc/version`）——没有构建身份的 rootfs 不可维护

实践：
- 把一个业务程序写成自定义 package（`foo.mk` + `Config.in`）编进 rootfs
- 加 `S90foo` 启动脚本，板上验证启动顺序/异常恢复/日志轮转
- 注入构建身份，验证两份不同 commit 的 rootfs 板上可区分

### 第 12 章：OpenWrt 网络设备

一句话：要「opkg 装包、LuCI 配置、A/B 升级」的网络设备就切 OpenWrt profile——与 Buildroot 按产品定位二选一，不是谁替代谁。

要点：

- 三层组织 target/subtarget/device：加一块新板主要是写 device 的 DTS 与 profile，定制留主树外
- musl 工具链与 Buildroot 的 glibc **绝对不能混**（`version GLIBC_x.x not found`）；两镜像完全独立构建
- vermagic 是 OpenWrt 最硬的约束：kmod 与内核完全一致才能加载，升级内核 = 全部 kmod 重编 = 仓库同步；rk-forge 自建 kernel+rootfs 天然匹配绕开此坑
- 「网络设备」栈：opkg/uci/procd/netifd/firewall4/LuCI，把网络当一等公民——双网口板的用武之地
- 选型：自定义业务为主→Buildroot；网络为主功能、需动态装包与 A/B→OpenWrt

实践：
- 加一个自定义 opkg 包（守护进程 + uci 配置）并 `opkg install` 验证
- 写一个 procd 服务（崩溃自重启、等网络就绪）
- 配双网口 WAN/LAN + DHCP + NAT + 防火墙并验证；故意编不配套 kmod 看 `insmod` 报错
- `sysupgrade -b/-r` 配置备份恢复

阶段产出：Buildroot 产品镜像或 OpenWrt 网络镜像（任选），加一份选型报告。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rootfs/01（buildroot）、02（init）](../../tutorial/rootfs/) | 第 11 章初稿 |
| [pitfalls/02（busybox init 两道暗门）](../../pitfalls/02-busybox-init-devtmpfs.md) | init 排障骨架 |
| [notes/19](../../notes/19-2026-06-18-buildroot-minimal-rootfs-first-build.md)、[31](../../notes/31-2026-06-20-mk-rootfs-patch-maker-removal.md)、[34](../../notes/34-2026-07-11-openwrt-integration.md)、[35](../../notes/35-2026-07-12-openwrt-rootfs-flow.md) | 取证链 |
| [tutorial/openwrt/](../../tutorial/openwrt/) | 第 12 章初稿 |
| [boards/aes/](../../../boards/aes/) 的五套 kernel config 与 [README-evb-configs.md](../../../boards/aes/README-evb-configs.md) | 产品裁剪实证 |
