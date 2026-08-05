# Ch0 — RK3588：阶梯最上面那级

> 这条 bring-up 阶梯，RK3506B 是地基，RK3568 是 AArch64 驱动框架的练兵场，RK3588 是顶上那级——异构、媒体、AI、桌面产品级。这一章不敲命令，先把 RK3588 这块板在咱们整个项目里的位置、和下面两级的关系、以及本卷四章要带你走到哪，交代清楚。

## RK3588 是块什么板，为什么轮到它

RK3588 是 Rockchip 当家旗舰：四个 Cortex-A76 加四个 Cortex-A55 的 big.LITTLE，外加 Mali-G610 GPU、NPU、VPU（Hantro + rkvdec2）、RGA、ISP——一颗硅上挤了五个加速器。它的主线 Linux 支持是 Rockchip 全系里最成熟的，Collabora 把它当旗舰伺候，从 big.LITTLE 调度到 GPU 的 Panthor 开源驱动、再到 NPU 的主线 Rocket 驱动，主线树里都能翻到。

所以 RK3588 的主线移植，性质和 RK3506B 完全不一样。RK3506B 是「主线几乎一片空白，咱们补那块板级 DT」；RK3588 是「主线什么都有，可当你把 vendor 那整套 SDK 拔掉、换上主线 U-Boot + 主线 kernel + 一块自己写的板级 DT 重新走一遍时，会有一堆接口和时机的坑把你按在地上」。这条路上咱们踩过、值得写下来的，是四块硬骨头——bootloop、LCD、GPU 固件、Ubuntu rootfs。

## 和下面两级的关系：不重复，只增量

三板阶梯有一条贯穿的纪律：每块板独立建立证据链，不默认共享任何固件、U-Boot、ATF、设备树、内核配置或镜像。RK3568 和 RK3588 虽然同为 AArch64，也绝不共用二进制产物。所以本卷不重讲 RK3506B 已经建起来的东西——主线 bring-up 是怎么回事、rkbin 这段闭源 blob 卡在 DDR init、`forge` 编排器的 DAG 和增量跳过、buildroot 出 rootfs、init 时序那两道暗门——这些你在 [RK3506B 的教程](../boot/) 里读过一遍就行。本卷只讲 RK3588 特有的增量。

增量主要在三处。一是启动链的前段比 RK3506 多一级 ATF（ARM Trusted Firmware），而且 vendor 的 SPL 跟 BL31 之间有个基址错配的坑，会让你卡在一个看不见报错的 bootloop 里——这是 RK3588 的第 0 关，没过这关后面什么都谈不上。二是显示：RK3506 为了 NAND 体积把 DRM 砍了，RK3588 的 LCD 却是重头戏，可 topeet 这块屏走的是 DSI 转 LVDS 的桥接 IC，主线没驱动，得自己写一条 OOT panel 驱动，还拌着 9 条 gotcha 和一个 VOP handoff 的硬锁。三是 rootfs 上到了 Ubuntu 桌面：不再是 buildroot busybox，是 systemd + GNOME，固件时机、用户账户、ext4 ownership 都是新课题。

## 本卷四章带你走到哪

| 章 | 主题 | 解决什么 | 状态 |
|---|---|---|---|
| [01 引导启动](01_boot) | bootloop + 主线 SPL + autoboot | 把板子从 BootROM 一路跑到 systemd | ✅ 真机验证 |
| [02 LCD 移植 saga](02_lcd) | OOT panel 驱动 + TC358775 桥 IC + VOP handoff | 把那块 1024×600 屏点亮出图 | 🟡 出图，VOP2 稳定性未闭环 |
| [03 GPU 固件](03_gpu) | Panthor early probe + 内建 raw 固件 | renderD128 起来 + GNOME 桌面 | ✅ 真机验证 |
| [04 Ubuntu rootfs](04_rootfs) | ubuntu-base + fakeroot + GDM | 桌面账户 + ext4 ownership 修复 | ✅ 真机验证 |

> 诚实的边界：四章覆盖的是「已经板上跑通」的部分。RK3588 ROADMAP 里那个更宏大的课——V4L2/ISP 摄像头、MPP 视频编解码、NPU/AI、Android 产品化——主线驱动要么还在 roadmap、要么硬件咱们没接，本卷不碰，等真机数据齐了再补。完整的教学目标见 [RK3588 路线](../../planning/RK3588_ROADMAP)。

## 读这卷之前，确认你手里有这些

一块 iTOP-RK3588（topeet）开发板、一根串口线、一把 aarch64 交叉工具链（Arm GNU 15.3，前缀 `aarch64-none-linux-gnu-`，不是 RK3506 那把 armhf）、一台装了 WSL2 的机器。工具链怎么装、`forge` 怎么选板（`--board=rk3588-topeet`），都在 [RK3506B 的工具链章](../boot/01_toolchain) 讲过，这里不重复。

咱们从第 0 关开始——那场看不见报错的 bootloop。
