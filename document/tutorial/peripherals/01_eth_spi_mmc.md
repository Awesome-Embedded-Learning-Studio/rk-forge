# Ch1 — Ethernet + SPI + MMC/SD：三个纯接线的外设（A1）

> 外设系列第一章。RK3506 这块板 bring-up 分了 A/B/C/D/E 五档，A1 是其中最干净的那一档：Ethernet、SPI、MMC/SD——三样的主线驱动一个不缺（dwmac-rk、spi-rockchip、dw_mmc-rockchip），config 也都 `=y`，预期就是把 vendor DT 的节点抄进我们的 `rk3506.dtsi` 和 `rk3506b-aes.dts`，build dtb、出 update.img、板验。Ethernet 双口通网是亮点，SPI 干净利落，MMC 中途 `-110` 绕了一大圈——真因出乎意料，教训比结论值钱。完整记录见 [notes/21](../../notes/21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md)，MMC 单独排查见 [notes/22](../../notes/22-2026-06-19-mmc-sd-error110-investigation.md)。

落在这三个 patch：[0004](../../../patches/linux/0004-ARM-dts-rockchip-rk3506b-aes-add-Ethernet-gmac1-RMII.patch) 把 gmac1 的 SoC 节点（`ethernet@ff4d0000`，`rockchip,rk3506-gmac + snps,dwmac-4.20a`）+ `mdio1` + `eth_rmii1` pinctrl（bank3，func2）写进 `rk3506.dtsi`，板级 override 写进 `rk3506b-aes.dts`；[0005](../../../patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch) 一口气把 MMC/SD（`mmc@ff480000`，rk3288-dw-mshc fallback）和 SPI0（`spi@ff120000`，rk3066-spi fallback）的 SoC 节点 + sdmmc pinctrl（bank3 PA0-PA5 func1）+ spi0 pinctrl（bank0 func2）+ 板级 override 都加上——两个外设的 hunk 在 DT 里交织，合成一个 patch；[0006](../../../patches/linux/0006-ARM-dts-rockchip-rk3506b-aes-enable-2nd-Ethernet-gmac0.patch) 是后面翻案时补的 gmac0。

## Ethernet：先栽在 carrier=0，双口才发现真相

Ethernet 这一段的主角是 gmac1。第一次板验 gmac1 probe 得很漂亮——`rk_gmac-dwmac ff4d0000` RMII、Synopsys ID 0x51、PHY 在 MDIO 上探到了（`stmmac-1:01`），eth0 在、`ifconfig up` 也成，但 `carrier=0`，udhcpc 没响应。我那会儿第一反应是往物理上怀疑——这反应是错的，后面翻案。

板级 override 长这样（[0004](../../../patches/linux/0004-ARM-dts-rockchip-rk3506b-aes-add-Ethernet-gmac1-RMII.patch)），typical 的 stmmac 板级接线：

```dts
&gmac1 {
    phy-mode = "rmii";
    clock_in_out = "output";
    snps,reset-gpio = <&gpio0 RK_PC4 GPIO_ACTIVE_LOW>;
    snps,reset-active-low;
    snps,reset-delays-us = <0 20000 100000>;
    pinctrl-names = "default";
    pinctrl-0 = <&eth_rmii1_miim_pins &eth_rmii1_tx_bus2_pins
                 &eth_rmii1_rx_bus2_pins &eth_rmii1_clk_pins>;
    phy-handle = <&rmii_phy1>;
    status = "okay";
};

&mdio1 {
    rmii_phy1: phy@1 {
        compatible = "ethernet-phy-ieee802.3-c22";
        reg = <0x1>;
    };
};
```

PHY 是 YT8512，但 DT 里不写 `ethernet-phy-ieee802.3-c22` 之外的私有 compatible——主线 generic C22 PHY 驱动就够了，别背 vendor 的私有 PHY 驱动包袱。reset 走 GPIO0_PC4，active-low，三段时序 `(0, 20000, 100000)` 是 stmmac 的惯例（deassert → 等 20ms → assert 100ms 稳住）。

翻案的钥匙是拿 vendor 镜像在同块板上对照。我烧了 vendor 的 SD 启动镜像抓 log（[boot-sdl-2026-06191732](../../logs/boot-sdl-2026-06191732.txt) + [vendor_sdk_ubifs](../../logs/vendor_sdk_ubifs.txt)），发现 vendor **同时 probe 了 gmac0（ff4c8000）和 gmac1（ff4d0000）两个口**，PHY 都是 YT8512，而且 vendor 的 eth0 = gmac0 link up 了 100M。也就是说这块 ATK 板有**两个 RJ45**，而我之前只照着 vendor DT 里 gmac1 那段开了 gmac1——**用户的网线插在 gmac0 那个口上**，forge 只开了 gmac1，eth0（=gmac1）自然 NO-CARRIER。

修就是 [0006](../../../patches/linux/0006-ARM-dts-rockchip-rk3506b-aes-enable-2nd-Ethernet-gmac0.patch) 把 gmac0 全补上：SoC 节点（`ethernet@ff4c8000`，对称于 gmac1，interrupts GIC_SPI 66/69）+ `mdio0` + `eth_rmii0` pinctrl + 板级 `&gmac0`（reset 改 GPIO0_PA0）+ `rmii_phy0` + `ethernet0` alias。这里有个细节容易翻车：gmac0 的 RMII 引脚在 **bank2**（func1），gmac1 在 **bank3**（func2），两组 pinctrl 的 bank/func 完全不一样，照抄 gmac1 改个数字会写到错的 pad 上。重烧 `update-a1-eth-dualgmac-mmc-spi.img`，[boot-sdl-2026-06191755](../../logs/boot-sdl-2026-06191755.txt) 就是结果：

```
rk_gmac-dwmac ff4c8000.ethernet eth0: PHY [stmmac-0:01] driver [Generic PHY]
rk_gmac-dwmac ff4c8000.ethernet eth0: Link is Up - 100Mbps/Full
udhcpc: lease of 192.168.60.132 obtained from 192.168.60.254
# ping -c3 192.168.60.2  →  3 packets received, 0% loss
```

Link Up + DHCP + ping 0% loss，Ethernet T3 全绿，板子也同时从上次的 rescue shell 恢复了（provisioning 走通、进 buildroot shell）。

## SPI：T1+T2 干净，T3 没条件

SPI0 这一段是这章最省心的。`rockchip-spi ff120000.spi` probe——PIO 模式，我故意删了 vendor 那套 5-cell DMA 编码（主线 pl330 那套 `dmas = <&dmac channel mux_reg mux_val ...>` 的 RK 风格编码主线不认，跟后面 Ch5 Audio 那边是同一个坑，这里干脆不挂 DMA，PIO 够用）。起手两条 `Failed to request optional TX/RX DMA channel -ENODEV` 是**良性的**——可选 DMA 没拿到，驱动继续走 PIO，别被吓到。`/dev/spidev0.0` 和 `0.1` 都在。

板级接线（[0005](../../../patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch)）：

```dts
&spi0 {
    status = "okay";
    pinctrl-names = "default";
    pinctrl-0 = <&spi0_csn0_pins &spi0_csn1_pins &spi0_clk_pins>;

    spidev@0 {
        compatible = "rohm,dh2228fv";
        spi-max-frequency = <50000000>;
        reg = <0>;
    };

    spidev@1 {
        compatible = "rohm,dh2228fv";
        spi-max-frequency = <50000000>;
        reg = <1>;
    };
};
```

这里有两个坑要记一下。一是 spidev 子节点的 `compatible` 必须用主线白名单里的值，比如 `rohm,dh2228fv`——主线 spidev 显式拒绝 `rockchip,spidev` 这种写法，它把 spidev 当成"用户空间调试用"，要求你挂在一个真实设备名下，`rohm,dh2228fv` 是主线白名单里最常被借用的 ADC 名字。二是 config：`CONFIG_SPI_ROCKCHIP` 必须 `=y`，multi_v7 defconfig 默认是 `=m`，我们那个最小 busybox rootfs 不 modprobe，必须内置，否则板上 SPI 根本不 probe——这条不补的话 dmesg 连 `rockchip-spi` 那行都不会有。

这板 SPI 没留对外接口，T3 loopback 做不了，T1（probe + `/sys/bus/spi/drivers/...`）+ T2（`/dev/spidev0.*`）到此即收。

## MMC/SD：-110 绕了一大圈，真因是卡没插紧

MMC/SD 这一段的 DT 节点移植本身没问题。SoC 节点（[0005](../../../patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch)）走 rk3288-dw-mshc fallback——主线 `dw_mmc-rockchip` 没给 rk3506 写专属条目，它就是靠 `rockchip,rk3288-dw-mshc` 这个 secondary compatible 命中 `rk3288_drv_data` 的 ops，vendor 也是这条路：

```dts
mmc: mmc@ff480000 {
    compatible = "rockchip,rk3506-dw-mshc", "rockchip,rk3288-dw-mshc";
    reg = <0xff480000 0x4000>;
    interrupts = <GIC_SPI 86 IRQ_TYPE_LEVEL_HIGH>;
    max-frequency = <150000000>;
    bus-width = <4>;
    clocks = <&cru HCLK_SDMMC>, <&cru CCLK_SRC_SDMMC>;
    clock-names = "biu", "ciu";
    fifo-depth = <0x100>;
    resets = <&cru SRST_H_SDMMC>;
    reset-names = "reset";
    status = "disabled";
};
```

板级 override 该有的都有：`cap-sd-highspeed`、`cd-gpios = <&gpio0 RK_PA2 GPIO_ACTIVE_LOW>`（卡检测）、`vmmc-supply` + `vqmmc-supply` 各挂一个 always-on 的 fixed regulator（forge 这板没 PMIC，全 fixed）。但前几次板验插卡全 `-110`：

```
mmc0: error -110 whilst initialising SD card
Card stuck being busy! __mmc_poll_for_busy
```

我绕了一大圈：先怀疑物理接触（错的，第一次误判），又怀疑主线 dw_mmc 驱动 6.1→7.1 回归，逐项排除了 DT/clk/pinctrl/ops 全等价于 vendor——抽 vendor DTB 反编译跟 forge 的 dtb 逐节 diff，把 mmc 节点本体、sdmmc pinctrl 引脚（bank3 PA0-PA5 func1 逐字相同）、`clk-rk3506.c` 里 `CCLK_SRC_SDMMC` 那段（`RK3506_CLKSEL_CON(49)` mux 13/2 divider 7/6）跟主线对，零差异——结果**真因是 SD 卡没插紧**。

带 RINTSTS debug 打印的镜像（[boot-sdl-202606191808](../../logs/boot-sdl-202606191808.txt)，临时在 `dw_mmc.c` 的 `DW_MCI_CMD_ERROR_FLAGS` 分支加一行 `dev_info` 抓 `pending` 寄存器）在板上把卡插紧，直接枚举：

```
mmc0: new high speed SDXC card
mmcblk0: mmc0:0001:0000 1 58.2 GiB
mmcblk0: p1 p2 p3 p4 p5 p6 p7 p8
```

那条 debug 打印抓到的 `pending=0x100` 是 RTO 位（Response Timeout），全落在 CMD5/CMD52——那是 mmc core 拿 SDIO 探测命令探一张 SD 内存卡，卡不认 SDIO 协议、超时，core 接着走 SD 内存初始化（CMD0/8/55/41）成功。**正常流程，不是错**。之前几次 `-110`（`Card stuck being busy`）就是卡数据线接触不良，插紧就好。

这章最值钱的教训不是怎么修 MMC，是前言那个方法论：判断硬件好不好，**别只看自己这棵树的 log，把 vendor 镜像跑在同板、同 SPI-NAND 上对照**。两个独立软件栈（vendor SPL/loader + mainline Linux）都读不出同一个东西才算物理坏；只一个读不出而另一个 OK，铁定是读不出的那侧的软件问题。我们一度把 MMC 的 `-110` 和 Ethernet 的 `carrier=0` 一起归给"物理问题"，是 vendor 那张 [vendor_sdcard_log](../../logs/vendor_sdcard_log.txt)——vendor 从 SD 启动，把同一张 64G 卡读得干干净净还从它启动——一眼把我们救回来的。硬件好的，是 forge 软件的事。**两次错的共同点**：没在动手深挖驱动/clk 之前，先排除"卡没插好、网线插错口"这种最便宜的物理变量（重插、换口、换卡各试一次）。顺序应该是先做最便宜的物理 triage，再进软件层 diff——我把它倒过来做，把一个 5 分钟能验的接触问题，绕成了一场几小时的驱动考古。

## 成功长这样

A1 三件套全绿，定型镜像 `update-a1-eth-dualgmac-mmc-spi.img`：

- **Ethernet** 双口（gmac0 + gmac1，YT8512 RMII），link up + DHCP 拿到 192.168.60.132 + ping 0% loss
- **SPI0** T1+T2（probe + `/dev/spidev0.0` + `0.1`），PIO 模式
- **MMC/SD** 枚举 + 8 分区（58.2 GiB SDXC）

到这里 forge 的设备树对 net/spi/mmc 已经自足，不再依赖 vendor DT——kill-vendor-sdk 那条线里 "DT 自足" 的第一刀。vendor 那两张 log 顺带还纠正了两个我之前的假设：屏是 **800×1280**（不是 720，vendor DRM 报 `800x1280@61.4, 67.0 MHz`），WiFi/BT 是 **USB dongle Realtek RTL8733BU**（不是板载 SDIO 模组，所以不抢那唯一的 dw_mmc 控制器）。这两条后面 Phase C/D 会再碰到。下一章我们点亮 USB——那要补一小块 USB2PHY 驱动，外加一个踩了才知道的 DT 坑。我们 Ch2 见。
