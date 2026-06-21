---
title: 外设
---

<PageHeader icon="🔌" title="外设" description="把板子从「能启动」变成「能用」——网口、USB、WiFi、I2C/UART、音频" />

boot + rootfs 走完，板子能持久 `login:` 了，但这只是"核心活"。一块板子要真正能用，还得把外设一个个点亮。好消息是：RK3506 这些外设的主线驱动**基本都在上游**（dwmac-rk、dw_mmc-rockchip、spi-rockchip、dwc2、pl330、ES8328……一个不缺），所以外设 bringup 的主体是"接线活"——把驱动用设备树接到引脚上、在 config 里打开、再上板验证。

我们分三层逐级坐实：**T1 驱动 probe**（dmesg / sysfs）→ **T2 设备就绪**（`/dev/*`、`/sys/class/net/*`）→ **T3 功能**（真 I/O）。有硬件就验 T3，没有就诚实标 `needs <gear>`，不装假通过。

<ChapterNav>
  <ChapterLink num="01" href="00_roadmap">路线图：把板子从"能启动"变成"能用"</ChapterLink>
  <ChapterLink num="02" href="01_eth_spi_mmc">Ethernet + SPI + MMC/SD：三个纯接线的外设</ChapterLink>
  <ChapterLink num="03" href="02_usb">USB：USB2PHY 的两套寄存器和那个父节点坑</ChapterLink>
  <ChapterLink num="04" href="03_wifi">WiFi（RTL8733BU）：把 out-of-tree 驱动搬进 7.1</ChapterLink>
  <ChapterLink num="05" href="04_i2c_uart_rmio">I2C/UART：RK3506 的 RMIO 交叉开关</ChapterLink>
  <ChapterLink num="06" href="05_audio">Audio（ES8388 + SAI1）：点亮数字音频链路</ChapterLink>
</ChapterNav>
