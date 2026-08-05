---
title: 教程系列
---

<PageHeader icon="📚" title="教程系列" description="三块 Rockchip 板的主线移植教程——RK3506B / RK3568 / RK3588，一条递进的阶梯" />

## 三块板，一条阶梯

rk-forge 围绕三块 Rockchip 开发板组织教程，它们是一条递进的阶梯，不是三门平行的课：

- 🟢 **[RK3506B 系列](#rk3506b-系列-完整教程)** —— 主线 bring-up 主课，也是教程最完整的一块：工具链 → rootfs → 外设 → SD 启动 → forge 编排器，五阶段全兑现。
- 🟡 **[RK3568 系列](rk3568/)** —— 从 ARM32 进 AArch64、学标准 Linux 驱动框架。当前 MVP：启动首启章已写真板验证，其余课程建设中。
- 🟡 **[RK3588 系列](rk3588/)** —— 异构、媒体、桌面产品级。启动 / LCD 移植 / GPU 固件 / Ubuntu rootfs 四章已写真板验证。

新手从 RK3506B 进；做过 BSP 想系统学 AArch64 驱动框架的从 RK3568 进；做异构 / 媒体 / 桌面产品的从 RK3588 进。三块板的完整教学目标、课程顺序和当前状态，见 [三板教学路线](../planning/)。

## RK3506B 系列（完整教程）

rk-forge 的 bring-up 弧线分五个阶段，按下面的顺序读最顺。我们先把板子**启动**起来——主线 U-Boot 加一份板级设备树；再让它**持久登录**，rootfs 这条路把 buildroot、init 时序、UBIFS 与 loader 弱写 saga 一口气走完；接着把**外设**一个个点亮，Ethernet/SPI/MMC、USB、WiFi、I2C/UART、Audio 全上板；之后补 **SD 卡**这条第二条启动路，纯 SD 也能 boot；最后用 **forge 编排器**把整条构建链收成一个命令。这五阶段是主弧线；跑通之后若还想要一套真能 `opkg` / LuCI 的发行版，再岔到 [OpenWrt 支线](openwrt/)——它和 buildroot 并列，是 rootfs 的进阶选择。

<RoadMap>
  <RoadMapPhase icon="🚀" title="引导启动" subtitle="Boot" time="主线 U-Boot + Kernel" :difficulty="3" :num="1">
    <ChapterLink num="00" href="boot/00_roadmap" variant="sub">路线图：为什么是 RK3506，为什么 mainline-first</ChapterLink>
    <ChapterLink num="01" href="boot/01_toolchain" variant="sub">工具链：arm-linux-gnueabihf</ChapterLink>
    <ChapterLink num="02" href="boot/02_uboot_rkbin" variant="sub">U-Boot 与 rkbin：在闭源 blob 的咽喉上拔河</ChapterLink>
    <ChapterLink num="03" href="boot/03_kernel" variant="sub">内核：补上那块属于我们的板级设备树</ChapterLink>
  </RoadMapPhase>

  <RoadMapPhase icon="📦" title="根文件系统" subtitle="RootFS" time="从 panic 到 login" :difficulty="3" :num="2">
    <ChapterLink num="00" href="rootfs/00_roadmap" variant="sub">路线图：rootfs 这条最深的路</ChapterLink>
    <ChapterLink num="01" href="rootfs/01_buildroot" variant="sub">buildroot：出一份正规的最小 rootfs</ChapterLink>
    <ChapterLink num="02" href="rootfs/02_init" variant="sub">init 时序：switch_root 到 login 的两道暗门</ChapterLink>
    <ChapterLink num="03" href="rootfs/03_ubifs_loader_weakwrite" variant="sub">UBIFS 与 loader 弱写 saga：bringup 最深的一关</ChapterLink>
  </RoadMapPhase>

  <RoadMapPhase icon="🔌" title="外设" subtitle="Peripherals" time="从能启动到能用" :difficulty="3" :num="3">
    <ChapterLink num="00" href="peripherals/00_roadmap" variant="sub">路线图：把板子从"能启动"变成"能用"</ChapterLink>
    <ChapterLink num="01" href="peripherals/01_eth_spi_mmc" variant="sub">Ethernet + SPI + MMC/SD：三个纯接线的外设</ChapterLink>
    <ChapterLink num="02" href="peripherals/02_usb" variant="sub">USB：USB2PHY 的两套寄存器和那个父节点坑</ChapterLink>
    <ChapterLink num="03" href="peripherals/03_wifi" variant="sub">WiFi（RTL8733BU）：把 out-of-tree 驱动搬进 7.1</ChapterLink>
    <ChapterLink num="04" href="peripherals/04_i2c_uart_rmio" variant="sub">I2C/UART：RK3506 的 RMIO 交叉开关</ChapterLink>
    <ChapterLink num="05" href="peripherals/05_audio" variant="sub">Audio（ES8388 + SAI1）：点亮数字音频链路</ChapterLink>
  </RoadMapPhase>

  <RoadMapPhase icon="💾" title="SD 卡启动" subtitle="SD Boot" time="第二条启动路" :difficulty="2" :num="4">
    <ChapterLink num="00" href="sd-boot/00_roadmap" variant="sub">路线图：SD 卡，第二条启动路</ChapterLink>
    <ChapterLink num="01" href="sd-boot/01_sd1_manual" variant="sub">SD-1：手动引导 SD 卡到 shell</ChapterLink>
    <ChapterLink num="02" href="sd-boot/02_sd2_autoboot" variant="sub">SD-2：autoboot，上电零输入到 shell</ChapterLink>
  </RoadMapPhase>

  <RoadMapPhase icon="🛠️" title="forge 编排器" subtitle="Orchestrator" time="把命令收成一个" :difficulty="2" :num="5">
    <ChapterLink num="00" href="forge/00_forge" variant="sub">forge：把一长串命令收成一个编排器</ChapterLink>
  </RoadMapPhase>
</RoadMap>

## RK3506B 教程目录

### 引导启动

<ChapterNav>
  <ChapterLink num="01" href="boot/00_roadmap">路线图：为什么 mainline-first</ChapterLink>
  <ChapterLink num="02" href="boot/01_toolchain">工具链：arm-linux-gnueabihf</ChapterLink>
  <ChapterLink num="03" href="boot/02_uboot_rkbin">U-Boot 与 rkbin</ChapterLink>
  <ChapterLink num="04" href="boot/03_kernel">内核：板级设备树</ChapterLink>
</ChapterNav>

### 根文件系统

<ChapterNav>
  <ChapterLink num="01" href="rootfs/00_roadmap">路线图：rootfs 最深的路</ChapterLink>
  <ChapterLink num="02" href="rootfs/01_buildroot">buildroot 最小 rootfs</ChapterLink>
  <ChapterLink num="03" href="rootfs/02_init">init 时序</ChapterLink>
  <ChapterLink num="04" href="rootfs/03_ubifs_loader_weakwrite">UBIFS 与 loader 弱写 saga</ChapterLink>
</ChapterNav>

### 外设

<ChapterNav>
  <ChapterLink num="01" href="peripherals/00_roadmap">路线图：从启动到能用</ChapterLink>
  <ChapterLink num="02" href="peripherals/01_eth_spi_mmc">Ethernet + SPI + MMC/SD</ChapterLink>
  <ChapterLink num="03" href="peripherals/02_usb">USB（USB2PHY + DWC2）</ChapterLink>
  <ChapterLink num="04" href="peripherals/03_wifi">WiFi（RTL8733BU）</ChapterLink>
  <ChapterLink num="05" href="peripherals/04_i2c_uart_rmio">I2C/UART（RMIO 交叉开关）</ChapterLink>
  <ChapterLink num="06" href="peripherals/05_audio">Audio（ES8388 + SAI1）</ChapterLink>
</ChapterNav>

### SD 卡启动

<ChapterNav>
  <ChapterLink num="01" href="sd-boot/00_roadmap">路线图：第二条启动路</ChapterLink>
  <ChapterLink num="02" href="sd-boot/01_sd1_manual">SD-1：手动引导</ChapterLink>
  <ChapterLink num="03" href="sd-boot/02_sd2_autoboot">SD-2：autoboot</ChapterLink>
</ChapterNav>

### forge 编排器

<ChapterNav>
  <ChapterLink num="01" href="forge/00_forge">forge：收成一个编排器</ChapterLink>
</ChapterNav>

### OpenWrt（可选支线）

<ChapterNav>
  <ChapterLink num="01" href="openwrt/00_openwrt">OpenWrt：给 RK3506 装一套真能 opkg 的发行版</ChapterLink>
</ChapterNav>

## RK3568 系列（MVP · 建设中）

RK3568 是 AArch64 + 标准驱动框架的中间级。主线 7.1 + binman 自产 loader 已真机 boot 到 login。

<ChapterNav>
  <ChapterLink num="00" href="rk3568/00_roadmap">路线图：RK3568 在阶梯里的位置</ChapterLink>
  <ChapterLink num="01" href="rk3568/01_boot">引导启动：主线 7.1 真机首启到 login</ChapterLink>
  <ChapterLink num="02" href="rk3568/02_peripherals">板级 DT 八子系统：从"能启动"到"能用"</ChapterLink>
</ChapterNav>

> 🚧 板级 DT 八子系统（PMIC / 双 GMAC / audio / 触摸 / LCD / GPU / CAN / RTC）、rtl8852bs WiFi、buildroot Phase 2a 全栈——在 [notes/40–42](../notes/) 有真机记录，但等板 DT patch 化（P4）落定后再课程化成章节。完整课程目标见 [RK3568 路线](../planning/RK3568_ROADMAP)。

## RK3588 系列

RK3588 是异构 / 媒体 / 桌面产品级的顶级。主线 boot 到 Ubuntu GNOME 桌面，LCD / GPU / 触摸板上点亮。

<ChapterNav>
  <ChapterLink num="00" href="rk3588/00_roadmap">路线图：RK3588 在阶梯里的位置</ChapterLink>
  <ChapterLink num="01" href="rk3588/01_boot">引导启动：bootloop 第 0 关 + 主线 SPL + autoboot</ChapterLink>
  <ChapterLink num="02" href="rk3588/02_lcd">LCD 移植 saga：TC358775 桥 IC 与 9 条 gotcha</ChapterLink>
  <ChapterLink num="03" href="rk3588/03_gpu">GPU 固件：Panthor early probe 与内建 raw 固件</ChapterLink>
  <ChapterLink num="04" href="rk3588/04_rootfs">Ubuntu rootfs：从 ubuntu-base 到 GNOME 桌面</ChapterLink>
  <ChapterLink num="05" href="rk3588/05_stability">稳定性调试：抓看不见的 hard-lock（方法论）</ChapterLink>
</ChapterNav>

> 🚧 V4L2/ISP 摄像头、MPP 视频编解码、NPU/AI、Android 产品化方向课——主线驱动还在 roadmap、硬件未接齐，等真机数据补齐后补。LCD 的 VOP2 hard-lock 修复当前是候选镜像，连续稳定性板验未完。完整课程目标见 [RK3588 路线](../planning/RK3588_ROADMAP)。

::: tip 遇到问题？
三块板这条链踩了一路坑——rkbin SPL 的隐性契约、SPI-NAND 读写 saga、reserved-memory 那个把人骗过两次的 imprecise abort、RK3588 那场看不见报错的 bootloop、TC358775 桥 IC 的 `.prepare` 生命周期、GPU 固件的 early-probe 时机……全记在 [踩坑日记](../pitfalls/) 和各章的"坑"小节里，每条挂着串口原文。提 [GitHub Issue](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues) 也欢迎。
:::
