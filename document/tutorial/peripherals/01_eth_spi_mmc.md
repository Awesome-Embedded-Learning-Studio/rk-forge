# Ch1 — Ethernet + SPI + MMC/SD：三个纯接线的外设（A1）

> 外设系列的第一章。RK3506 这块板 bring-up 分了 A/B/C/D/E 五档，A1 是其中最干净的那一档。Ethernet、SPI、MMC/SD 三样的主线驱动一个不缺（dwmac-rk、spi-rockchip、dw_mmc-rockchip），config 也都置了 `=y`，预期就是咱们把原厂 DT 的节点搬进咱们自己的 `rk3506.dtsi` 和 `rk3506b-aes.dts`，而后 build dtb、出 update.img、板验。Ethernet 双口通网是这一章的亮点，SPI 的段落干净利落，MMC 中途 `-110` 绕了一大圈，而真因出乎咱们的意料，教训的分量比修法还重。完整的记录见 [notes/21](../../notes/21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md)，MMC 的单独排查见 [notes/22](../../notes/22-2026-06-19-mmc-sd-error110-investigation.md)。

咱们把这一档的活落在三个 patch 上：[0004](../../../boards/aes/patches/linux/0004-ARM-dts-rockchip-rk3506b-aes-add-Ethernet-gmac1-RMII.patch) 把 gmac1 的 SoC 节点（`ethernet@ff4d0000`、`rockchip,rk3506-gmac + snps,dwmac-4.20a`）+ `mdio1` + `eth_rmii1` pinctrl（bank3、func2）写进了 `rk3506.dtsi`，板级的 override 写进 `rk3506b-aes.dts`。[0005](../../../boards/aes/patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch) 一口气把 MMC/SD（`mmc@ff480000`、rk3288-dw-mshc fallback）和 SPI0（`spi@ff120000`、rk3066-spi fallback）的 SoC 节点 + sdmmc pinctrl（bank3 PA0-PA5 func1）+ spi0 pinctrl（bank0 func2）+ 板级 override 都加上了，两个外设的 hunk 在 DT 里交织，咱们就把它合成了一个 patch。[0006](../../../boards/aes/patches/linux/0006-ARM-dts-rockchip-rk3506b-aes-enable-2nd-Ethernet-gmac0.patch) 是后面翻案时补的 gmac0。

## Ethernet：一上来就栽在 carrier=0，双口才发现真相

Ethernet 这一段的主角是 gmac1。咱们头一次板验，gmac1 的 probe 出得很漂亮，`rk_gmac-dwmac ff4d0000` 报的是 RMII、Synopsys ID 0x51，PHY 在 MDIO 上也探到了（`stmmac-1:01`），eth0 在、`ifconfig up` 也都起来了，但是链路那头 `carrier=0`，而 udhcpc 没响应。笔者那会儿的第一反应是往物理上怀疑，而这一怀疑是错的，后面咱们翻案。

咱们给 gmac1 写的板级 override 长这样（[0004](../../../boards/aes/patches/linux/0004-ARM-dts-rockchip-rk3506b-aes-add-Ethernet-gmac1-RMII.patch)），是 typical 的 stmmac 板级接线：

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

PHY 用的是 YT8512，但 DT 里咱们不写 `ethernet-phy-ieee802.3-c22` 之外的私有 compatible，主线 generic C22 PHY 驱动就够了，咱们别背原厂的私有 PHY 驱动包袱。reset 走的是 GPIO0_PC4、active-low，三段时序 `(0, 20000, 100000)` 是 stmmac 的惯例（`deassert → 等 20ms → assert 100ms 稳住`）。

翻案靠的是拿原厂镜像在同一块板上做对照。咱们烧了原厂的 SD 启动镜像抓 log（[boot-sdl-2026-06191732](../../logs/boot-sdl-2026-06191732.txt) + [vendor_sdk_ubifs](../../logs/vendor_sdk_ubifs.txt)），发现原厂**同时 probe 了 gmac0（ff4c8000）和 gmac1（ff4d0000）两个口**，PHY 用的都是 YT8512，而且原厂的 eth0 = gmac0 link up 了 100M。也就是说这块 ATK 板上装了**两个 RJ45**，而咱们之前只照着原厂 DT 里 gmac1 那段开了 gmac1，**用户的网线偏偏插在 gmac0 那个口上**，而 forge 只开了 gmac1，eth0（=gmac1）自然是 NO-CARRIER 了。

修复靠的是 [0006](../../../boards/aes/patches/linux/0006-ARM-dts-rockchip-rk3506b-aes-enable-2nd-Ethernet-gmac0.patch)，把 gmac0 完整地补上：SoC 节点（`ethernet@ff4c8000`、对称于 gmac1、interrupts GIC_SPI 66/69），补上 `mdio0` + `eth_rmii0` 的 pinctrl，再补板级的 `&gmac0`（reset 改 GPIO0_PA0），以及 `rmii_phy0` 和 `ethernet0` 的 alias。这里有个容易翻车的细节：gmac0 的 RMII 引脚在 **bank2**（func1），而 gmac1 的落在 **bank3**（func2），两组 pinctrl 的 bank/func 完全不一样，复制 gmac1 的写法改个数字，会写到错的 pad 上。咱们重烧 `update-a1-eth-dualgmac-mmc-spi.img`，结果都在 [boot-sdl-2026-06191755](../../logs/boot-sdl-2026-06191755.txt) 里：

```
rk_gmac-dwmac ff4c8000.ethernet eth0: PHY [stmmac-0:01] driver [Generic PHY]
rk_gmac-dwmac ff4c8000.ethernet eth0: Link is Up - 100Mbps/Full
udhcpc: lease of 192.168.60.132 obtained from 192.168.60.254
# ping -c3 192.168.60.2  →  3 packets received, 0% loss
```

咱们把 Link Up 加 DHCP 加 ping 0% loss 都验到了，Ethernet 的 T3 全过，板子也同时从上次的 rescue shell 里恢复了，provisioning 走通、进了 buildroot shell。

## SPI：T1+T2 干净，T3 没条件

SPI0 这一段是这章最省心的。`rockchip-spi ff120000.spi` probe 起来了，走的是 PIO 模式，咱们故意删了原厂那套 5-cell DMA 编码（主线 pl330 那套 `dmas = <&dmac channel mux_reg mux_val ...>` 的 RK 风格编码主线不认，跟后面 Ch5 Audio 那边踩的是同一颗雷，这里咱们干脆不挂 DMA，PIO 就够用了）。起手两条 `Failed to request optional TX/RX DMA channel -ENODEV` 是**良性的**，可选的 DMA 没拿到，驱动接着走的是 PIO，咱们别被吓到。`/dev/spidev0.0` 和 `0.1` 都在了。

咱们照 [0005](../../../boards/aes/patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch) 落的板级接线：

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

这里有两颗雷要咱们记下。一是 spidev 子节点的 `compatible` 必须用主线白名单里的值（比如 `rohm,dh2228fv`），主线 spidev 显式拒绝的正是 `rockchip,spidev` 这样的写法，它把 spidev 当成了“用户空间调试用”，要求你挂在一个真实设备名下，而 `rohm,dh2228fv` 是主线白名单里最常被借用的 ADC 名字。二是 config 的部分，`CONFIG_SPI_ROCKCHIP` 得是 `=y` 的：multi_v7 defconfig 默认给的是 `=m`，咱们那个最小 busybox rootfs 不 modprobe，所以必须内置，否则板上根本不会有 SPI 的 probe，漏掉它的代价是 dmesg 里连 `rockchip-spi` 那行都不会有。

这板的 SPI 没给咱们留对外接口，T3 的 loopback 做不了，所以验证到 T1（probe + `/sys/bus/spi/drivers/...`）加 T2（`/dev/spidev0.*`）就收。

## MMC/SD：-110 绕了一大圈，真因是卡没插紧

MMC/SD 这一段的 DT 节点，咱们移植过来本身没问题。SoC 节点（[0005](../../../boards/aes/patches/linux/0005-ARM-dts-rockchip-rk3506b-aes-add-MMC-SD-SPI0.patch)）走的是 rk3288-dw-mshc fallback，原因是主线 `dw_mmc-rockchip` 没给 rk3506 写过专属的条目，它就是靠 `rockchip,rk3288-dw-mshc` 这个 secondary compatible 命中 `rk3288_drv_data` 的 ops，而原厂走的也是同样的路：

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

板级 override 这边咱们该有的都配了：`cap-sd-highspeed`、`cd-gpios = <&gpio0 RK_PA2 GPIO_ACTIVE_LOW>`（卡检测），`vmmc-supply` 加 `vqmmc-supply` 各挂了一个 always-on 的 fixed regulator，而 forge 这板没 PMIC、全 fixed。但头几回板验插卡全吃了 `-110`：

```
mmc0: error -110 whilst initialising SD card
Card stuck being busy! __mmc_poll_for_busy
```

咱们绕了一大圈：起初怀疑的是物理接触，而这一怀疑是错的（头一次误判），又怀疑主线 dw_mmc 驱动从 6.1 到 7.1 的回归，逐项排查 DT、clk、pinctrl、ops 是不是全等价于原厂——咱们抽原厂 DTB，反编译后跟 forge 的 dtb 逐节 diff，把 mmc 的节点本体、sdmmc 的 pinctrl 引脚（bank3 PA0-PA5 func1 逐字相同）、`clk-rk3506.c` 里 `CCLK_SRC_SDMMC` 那段（`RK3506_CLKSEL_CON(49)` mux 13/2 divider 7/6）跟主线比，结果零差异——**最后真因落在了 SD 卡没插紧上**。

咱们拿带 RINTSTS debug 打印的镜像（[boot-sdl-202606191808](../../logs/boot-sdl-202606191808.txt)，临时在 `dw_mmc.c` 的 `DW_MCI_CMD_ERROR_FLAGS` 分支加一行 `dev_info` 抓 `pending` 寄存器）到板上把卡插紧，卡就直接枚举出来了：

```
mmc0: new high speed SDXC card
mmcblk0: mmc0:0001:0000 1 58.2 GiB
mmcblk0: p1 p2 p3 p4 p5 p6 p7 p8
```

那行 debug 打印抓到的 `pending=0x100` 是 RTO 位（Response Timeout），全落在 CMD5/CMD52——那是 mmc core 拿 SDIO 探测命令探一张 SD 内存卡的流程，而卡不认 SDIO 协议、超时，core 接着走的 SD 内存初始化（CMD0/8/55/41）成功了。**它其实是正常流程，咱们别当成错**。此前几回 `-110`（`Card stuck being busy`）就是卡的数据线接触不良，插紧了就好。

这章最值钱的教训落在了前言那个方法论上：判断硬件好不好的办法，**就是别只看自己这棵树的 log，把原厂镜像跑在同板的同一个 SPI-NAND 上对照**。两个独立的软件栈（原厂 SPL/loader 加 mainline Linux）都读不出同一个东西，咱们才能断定它物理坏了。只一个读不出而另一个 OK，铁定是读不出的那一侧的软件问题。咱们一度把 MMC 的 `-110` 和 Ethernet 的 `carrier=0` 一起归给“物理问题”，是原厂的 [vendor_sdcard_log](../../logs/vendor_sdcard_log.txt) 把咱们一眼救了回来——原厂从 SD 启动，把同一张 64G 卡读得干干净净还从它启动了。硬件是好的，出事的是 forge 的软件。**两次错的共同点**，是咱们没在动手深挖驱动和 clk 的时候，把卡没插好、网线插错口这类最便宜的物理变量排掉，重插、换口、换卡各试了一次。正确的顺序是从最便宜的物理 triage 做起，再进软件层 diff——咱们当时把它倒过来做了，把一个 5 分钟就能验的接触问题，绕成了一场几小时的驱动考古。

## 成功长这样

A1 的三件套咱们全验过了，定型镜像用的是 `update-a1-eth-dualgmac-mmc-spi.img`：

- **Ethernet** 双口（gmac0 + gmac1，YT8512 RMII），link up + DHCP 拿到 192.168.60.132 + ping 0% loss
- **SPI0** T1+T2（probe + `/dev/spidev0.0` + `0.1`），PIO 模式
- **MMC/SD** 枚举 + 8 分区（58.2 GiB SDXC）

到这里 forge 的设备树对 net/spi/mmc 已经自足，不再依赖原厂的 DT。这是 kill-vendor-sdk 那一路里 DT 自足的第一刀。原厂的两张 log 顺带还纠正了咱们此前的两个假设：屏的规格是 **800×1280**（不是 720，原厂 DRM 报的是 `800x1280@61.4, 67.0 MHz`），WiFi/BT 的真身是 **USB dongle Realtek RTL8733BU**（不是板载 SDIO 模组，所以不抢那唯一的 dw_mmc 控制器）。这两点咱们后面 Phase C/D 会再碰到。下一章咱们点亮 USB——那要补一小块 USB2PHY 驱动，外加一颗踩了才知道的 DT 雷。咱们 Ch2 见。
