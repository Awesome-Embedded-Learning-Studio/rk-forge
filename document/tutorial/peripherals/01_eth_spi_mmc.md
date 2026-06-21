# Ch1 — Ethernet + SPI + MMC/SD：三个纯接线的外设（A1）

> 外设系列第一章，先把三个"纯 DT、零驱动 patch"的外设点亮：Ethernet、SPI、MMC/SD。它们的主线驱动一个不缺（dwmac-rk、spi-rockchip、dw_mmc-rockchip），所以这一章基本就是接线 + 板验。Ethernet 双口通网是亮点，MMC 中途 -110 绕了一大圈（真因出乎意料），SPI 干净利落。完整记录见 [notes/21](../../notes/21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md)。

## 前言：A1 这批为什么是"纯接线"

按外设 bringup 的难易分档，Ethernet / SPI / MMC/SD 属于最干净的那一档——主线驱动全在、config 也都 `=y`，预期就是把 vendor DT 的节点抄进我们的 `rk3506.dtsi` 和 `rk3506b-aes.dts`，build dtb、出镜像、板验。落在三个 patch：[0004](../../../patches/linux/0004-ARM-dts-rockchip-rk3506b-aes-add-Ethernet-gmac1-RMII.patch) Ethernet gmac1（RMII）、[0005](../../../patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch) MMC/SD + SPI0、[0006](../../../patches/linux/0006-ARM-dts-rockchip-rk3506b-aes-enable-2nd-Ethernet-gmac0.patch) 补 gmac0。

## Ethernet：先栽在 carrier=0，双口才发现真相

Ethernet 第一次板验，gmac1 probe 得很漂亮——`rk_gmac-dwmac ff4d0000` RMII、Synopsys ID 0x51、PHY 探到（MDIO 通），eth0 在、`ifconfig up` 也成。但 `carrier=0`，udhcpc 没响应。我当时第一反应是往物理上怀疑——错了。

翻案的钥匙是拿 vendor 镜像在同块板上对照。vendor 的 log 里同时 probe 了 **gmac0（ff4c8000）和 gmac1（ff4d0000）两个口**，PHY 都是 YT8512，而且 vendor 的 eth0=gmac0 link up 了 100M。也就是说这块 ATK 板有**两个 RJ45**，而我之前只照着 vendor DT 里 gmac1 那段开了 gmac1——**用户的网线插在 gmac0 那个口上**，forge 只开了 gmac1，eth0（=gmac1）自然 NO-CARRIER。

修就是 `0006` 把 gmac0 补全：SoC 节点（`ethernet@ff4c8000`，对称于 gmac1）+ `mdio0` + `eth_rmii0` pinctrl（注意 gmac0 在 **bank2**，gmac1 在 bank3，不一样）+ 板级 `&gmac0`（reset-gpio、phy-handle、status okay）+ `rmii_phy0`。重烧上去，[boot-sdl-2026-06191755](../../logs/boot-sdl-2026-06191755.txt) 就是结果：

```
rk_gmac-dwmac ff4c8000.ethernet eth0: PHY [stmmac-0:01] driver [Generic PHY]
rk_gmac-dwmac ff4c8000.ethernet eth0: Link is Up - 100Mbps/Full
udhcpc: lease of 192.168.60.132 obtained from 192.168.60.254
# ping -c3 192.168.60.2  →  3 packets received, 0% loss
```

Link Up + DHCP + ping 0% loss，Ethernet T3 全绿。

## SPI：T1+T2 干净，T3 没条件

SPI0 没啥波折。`rockchip-spi ff120000.spi` probe（PIO 模式——我故意删了 vendor 那套 5-cell DMA 编码，主线 pl330 不认），起手两条 `Failed to request optional TX/RX DMA channel -ENODEV` 是**良性的**——可选 DMA 没拿到，驱动继续走 PIO，别被吓到。`/dev/spidev0.0` 和 `0.1` 都在。

这里有两个坑要记一下。一是 spidev 子节点的 `compatible` 必须用主线白名单里的值，比如 `rohm,dh2228fv`——主线 spidev 显式拒绝 `rockchip,spidev` 这种写法。二是 config：`CONFIG_SPI_ROCKCHIP` 要 `=y`，multi_v7 默认是 `=m`，我们那个最小 busybox rootfs 不 modprobe，必须内置，否则板上 SPI 根本不 probe。这板 SPI 没留对外接口，T3 loopback 做不了，T1+T2 到此即收。

## MMC/SD：-110 绕了一大圈，真因是卡没插紧

MMC/SD 的 DT 节点（`0005`）移植本身没问题。但前几次板验插卡全 `-110`（`mmc0: error -110 whilst initialising SD card` + `Card stuck being busy`），我绕了一大圈：先怀疑物理接触，又怀疑主线 dw_mmc 驱动回归，逐项排除了 DT/clk/pinctrl/ops 全等价于 vendor——结果**真因是 SD 卡没插紧**。

带 debug 打印的镜像（[boot-sdl-202606191808](../../logs/boot-sdl-202606191808.txt)）在板上把卡插紧，直接枚举：`mmc0: new high speed SDXC card` + `mmcblk0: ... 58.2 GiB` + **8 分区全出来**。那条 debug 打印抓到的 `pending=0x100`（RTO 超时）全落在 CMD5/CMD52——那是 SDIO 探测命令探一张 SD 内存卡时的正常超时，不是真错。

这章最值钱的教训就是前言那个方法论：判断硬件好不好，拿 vendor 同板对照。我们一度把 MMC 的 -110 和 Ethernet 的 carrier=0 一起归给"物理问题"，是 vendor 那张 [vendor_sdcard_log](../../logs/vendor_sdcard_log.txt)（vendor 从 SD 启动，把同一张 64G 卡读得干干净净还从它启动）一眼把我们救回来的——硬件好的，是 forge 软件的事。

## 成功长这样

A1 三件套全绿：Ethernet（双口，link up + DHCP + ping）、SPI（T1+T2）、MMC/SD（枚举 + 8 分区）。到这里 forge 的设备树对 net/spi/mmc 已经自足，不再依赖 vendor DT。下一章我们点亮 USB——那要补一小块 USB2PHY 驱动，外加一个踩了才知道的 DT 坑。我们 Ch2 见。
