---
title: 教程系列
---

<PageHeader icon="📚" title="教程系列" description="从空机器到 RK3506 主线启动到 UART 登录的完整可复现路径" />

## 学习路线图

rk-forge 的 bring-up 弧线分五个阶段，按下面的顺序读最顺。我们先把板子**启动**起来——主线 U-Boot 加一份板级设备树；再让它**持久登录**，rootfs 这条路把 buildroot、init 时序、UBIFS 与 loader 弱写 saga 一口气走完；接着把**外设**一个个点亮，Ethernet/SPI/MMC、USB、WiFi、I2C/UART、Audio 全上板；之后补 **SD 卡**这条第二条启动路，纯 SD 也能 boot；最后用 **forge 编排器**把整条构建链收成一个命令。

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

## 教程目录

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

::: tip 遇到问题？
RK3506 这条链踩了一路坑——rkbin SPL 的隐性契约、SPI-NAND 读写 saga、reserved-memory 那个把人骗过两次的 imprecise abort、USB2PHY 的两套寄存器、out-of-tree WiFi 搬进 7.1……全都老老实实记在 [踩坑日记](../pitfalls/) 的七篇里，每条挂着串口原文。提 [GitHub Issue](https://github.com/Awesome-Embedded-Learning-Studio/rk-forge/issues) 也欢迎。
:::
