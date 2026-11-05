---
title: 外设
---

<PageHeader icon="🔌" title="外设" description="把板子从「能启动」变成「能用」——网口、USB、WiFi、I2C/UART、音频" />

咱们把 boot 和 rootfs 走完，板子能持久地跑进 `login:` 了，但这部分只是核心的活。一块板子要真正地能用，咱们还得把外设一个个点亮。RK3506 这些外设的主线驱动基本都在上游：`dwmac-rk`、`dw_mmc-rockchip`、`spi-rockchip`、`dwc2`、`pl330`、`ES8328` 一个都不缺，所以外设 bringup 的主体是接线活，咱们把驱动用设备树接到引脚上、在 config 里打开、再拿到板上验证。驱动咱们基本不用从头写，写的多是 DT 和那几处 RK3506 缺的 of_match，最大的一发驱动活是 pinctrl 的 RMIO 交叉开关（04 章）。

验证咱们就一层层落实：咱们在 dmesg、sysfs 里看 probe 起没起，`/dev/*`、`/sys/class/net/*` 这些设备节点出来了没，最后跑真的 I/O。有硬件咱们就验到功能层，没有的咱们就诚实标 `needs <gear>`，咱们绝不装假通过。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：把板子从"能启动"变成"能用"</ChapterLink>
  <ChapterLink num="02" href="01_eth_spi_mmc">Ethernet + SPI + MMC/SD：三个纯接线的外设</ChapterLink>
  <ChapterLink num="03" href="02_usb">USB：USB2PHY 的两套寄存器和那个父节点雷</ChapterLink>
  <ChapterLink num="04" href="03_wifi">WiFi（RTL8733BU）：把 out-of-tree 驱动搬进 7.1</ChapterLink>
  <ChapterLink num="05" href="04_i2c_uart_rmio">I2C/UART：RK3506 的 RMIO 交叉开关</ChapterLink>
  <ChapterLink num="06" href="05_audio">Audio（ES8388 + SAI1）：点亮数字音频链路</ChapterLink>
</ChapterNav>
