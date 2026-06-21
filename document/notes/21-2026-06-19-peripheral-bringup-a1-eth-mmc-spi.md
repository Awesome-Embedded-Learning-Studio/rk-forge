# 21 — 外设 bring-up A1：Ethernet（双口）+ SPI + MMC/SD 全跑通（2026-06-19）

> **✅ 里程碑（A1 全绿）**：forge 从"只有 console + SFC/NAND"推进到 **Ethernet（双口）+ SPI + MMC/SD 全部板验跑通**——Ethernet 端到端 link up + DHCP + ping；SPI T1+T2；MMC/SD 热插枚举 + 8 分区。这条是 kill-vendor-sdk 弧线里 **Role 2（DT 自足）**的第一刀：把板子在用的外设从 vendor DT 搬进 forge 主线 DT 并板验。MMC 中途 `-110` 绕了一大圈（一度误判物理、又误判主线驱动回归，真因是卡接触不良），单独排查见 [22](22-2026-06-19-mmc-sd-error110-investigation.md)，最终板上插紧即通。

> **方法论要点（这条最值钱）**：判断"板子硬件好不好"，别只看 forge 自己的 log——**把 vendor 镜像跑在同一块板、同一个 SPI-NAND 上**（`boot-sdl-2026-06191732.txt` 是 vendor SD 启动、`vendor_sdk_ubifs.txt` 是 vendor NAND UBIFS），两边对照。vendor 能读的东西硬件就是好的，forge 读不出 = forge 软件问题，**别轻易往"物理/接触"上归因**（我一开始就犯了这错，见下）。

## 背景：A1 的活

按 [forge-remaining-work-roadmap](../../) 的分期，A1 是"纯 DT、零驱动 patch"的那一档外设：Ethernet、MMC/SD、SPI0。三样的主线驱动都齐（dwmac-rk 有完整 rk3506 RMII glue、dw_mmc-rockchip、spi-rockchip），config 也都 `=y`（`DWMAC_ROCKCHIP`/`MMC_DW_ROCKCHIP`/`SPI_ROCKCHIP`），所以预期就是把 vendor DT 的节点抄进 forge 的 `rk3506.dtsi`（SoC 节点 + pinctrl）和 `rk3506b-aes.dts`（板级 override + regulator），build dtb 验语法、出 update.img 板验。

落在三个 patch：`0004` Ethernet gmac1（RMII）、`0005` MMC/SD + SPI0（两外设编辑交织在同一批 hunk 里，合并成一个 patch）、`0006` 补 gmac0。外加 `kernel.config` 补 `CONFIG_SPI_ROCKCHIP=y`（multi_v7 默认是 `=m`，最小 busybox rootfs 不 modprobe，必须内置——这条不补的话 SPI 板上根本不 probe）。

## 板验三件套的 T1/T2/T3 分层

"确实在工作"不能只看 dmesg 蹦一行，分三层逐级坐实，每层有硬证据：**T1 驱动 probe**（dmesg 有 probe 行 + `/sys/bus/.../drivers/...` 绑了节点）、**T2 设备就绪**（总线枚举到：`/sys/class/net/eth0`、`/dev/mmcblk0`、`/dev/spidev0.*`）、**T3 功能**（真 I/O：Ethernet 的 carrier + DHCP + ping，MMC 插卡读 MBR + mount，SPI loopback）。T1+T2 不依赖任何外部硬件就能 100% 坐实"DT+驱动正确"；T3 要网线/卡/跳线，脚本自动探测有就跑、没有就标 `needs <gear>`，不装假通过。

## Ethernet：先栽在 carrier=0，双口才发现真相

第一次板验（`boot-sdl-202606191635.txt`）：gmac1 probe 漂亮（`rk_gmac-dwmac ff4d0000` RMII、Synopsys ID 0x51、PHY `stmmac-1:01` 探到 = MDIO 通），eth0 在、`ifconfig up` 也成，但 `carrier=0` + `udhcpc` 无响应。我那时把它跟 vendor SD 启动时 SPL 的 `mmc_init: -95` 联想，**误判成"MMC 和网都像物理问题"**——这是错的，后面翻案。

翻案的钥匙是 vendor 那两张 log。`boot-sdl-2026-06191732.txt`（vendor 从 SD 启动）里，**同一块板、同一个 dwmmc 控制器，把那张 64G 卡读得干干净净**（`mmc0: new high speed SDXC card`、`mmcblk0: ... 58.2 GiB`、8 分区 EXT4 mount 还从它启动）；`vendor_sdk_ubifs.txt`（vendor 跑在同一 SPI-NAND，`ubi.mtd=5 rootfs` 跟 forge **逐字一样**）里，**boot NAND 的同时还把那张 SD 卡读出来了**——正是 forge 的场景。所以 SD 槽+卡+控制器硬件 100% 好，SPL 那个 `-95` 只是"SD 上没 boot 镜像 → fall 到 NAND"的正常启动顺序，不是读卡失败。我道歉，判断错了。

Ethernet 的真因藏在这两张 log 里：vendor **同时 probe 了 gmac0(ff4c8000) + gmac1(ff4d0000) 两个口**，PHY 都是 YT8512，而且 **vendor 的 eth0=gmac0 link up 了 100M**。也就是说 ATK 这板有**两个 RJ45**，我之前只按 `rk3506b-alientek.dtsi` 里 gmac1 那段（alientek 只把 gmac1 写全，gmac0 只留了个 reset-gpio stub）开了 gmac1。**用户的网线插在 gmac0 那个口上**，forge 只开了 gmac1 → eth0(=gmac1) 自然 NO-CARRIER。

修就是 `0006`：把 gmac0 的 SoC 节点（`ethernet@ff4c8000`，MAC0 时钟/reset，对称于 gmac1）+ `mdio0` + `eth_rmii0` pinctrl（注意 gmac0 在 **bank2**，gmac1 在 bank3，不一样）+ 板级 `&gmac0`（reset=GPIO0_PA0、phy-handle=`rmii_phy0`、status okay）+ `&mdio0 { rmii_phy0: phy@1 }` + `ethernet0` alias 全补上。evb1 里 gmac0 的板级配置是现成的参考（reset 用 PC2，但 alientek/实际 DTB 是 PA0，按板上实际来）。

重烧 `update-a1-eth-dualgmac-mmc-spi.img`，`boot-sdl-2026-06191755.txt` 就是结果：

```
rk_gmac-dwmac ff4c8000.ethernet eth0: PHY [stmmac-0:01] driver [Generic PHY]
rk_gmac-dwmac ff4c8000.ethernet eth0: Link is Up - 100Mbps/Full
udhcpc: lease of 192.168.60.132 obtained from 192.168.60.254
# ping -c3 192.168.60.2  →  3 packets received, 0% loss
```

**Ethernet T3 全绿**，板子也同时从上次的 rescue shell 恢复了（provisioning 走通、进 buildroot shell）。这条算彻底过。

## SPI：T1+T2 干净

SPI0 没啥波折：`rockchip-spi ff120000.spi` probe（PIO 模式——我故意删了 vendor 的 5-cell DMA 编码，主线 pl330 不认），起手两条 `Failed to request optional TX/RX DMA channel -ENODEV` 是**良性的**（可选 DMA 没拿到，驱动继续走 PIO），别被吓到。`/dev/spidev0.0` + `0.1` 都在（子节点 `compatible` 必须用白名单里的 `rohm,dh2228fv`，主线 spidev 拒绝 `rockchip,spidev`）。这板子 SPI 没留对外接口，T3 loopback 做不了，T1+T2 到此即收。

## 顺带纠正的几个假设（影响后续 phase）

vendor 那两张 log 顺带把几个我之前的假设纠正了，记一下免得后面 phase 走错：

- **屏是 800×1280，不是 720**。vendor U-Boot DRM + Linux DRM + weston 都报 `800x1280@61.4, 67.0 MHz`（`dsi@ff640000: detailed mode clock 67000`），而且用户确认"没调就亮"——驱动 800×1280 能点亮就说明物理屏就是 800×1280。Phase D 用 `rk3506-alientek-mipi800x1280.dtsi` 那套（init 解锁 `FF 98 81 03`），不是 720。
- **WiFi/BT 是 USB dongle（Realtek RTL8733BU）**，不是板载 AP6256 SDIO。log 里 `rtk_btusb: chip type 0x76` + `rtl8733bu_config`，插在 USB2 口上。所以 WiFi 这条走主线 USB WiFi 驱动，**不抢那个唯一的 mmc 控制器**（RK3506 只有一个 dw_mmc，SD 卡和 SDIO-WiFi 是互斥的，USB dongle 正好绕开）。
- **Audio(ES8388+SAI)、USB(dwc2×2)、PL330 DMA(dmac0/dmac1)、rga2、gt9xx 触摸** 在 vendor 里全 probe 正常——验证了 Phase B（USB）/E（Audio）硬件可行，DMA 也能 port（Audio 要用的）。

## MMC：节点移植对了，-110 是卡接触（绕了一大圈）

MMC/SD 节点（`0005`）移植本身没问题：`mmc@ff480000`（rk3288-dw-mshc fallback）+ sdmmc pinctrl（bank3 PA0-PA5 func1）+ 板级（cd-gpios、vmmc/vqmmc regulator-fixed）+ `pcfg_pull_none_drv_level_3`（SPI 用的 pinconf，内联补进 pinctrl）。但前几次板验插卡都 `-110`（`mmc0: error -110 whilst initialising SD card` + `Card stuck being busy`），绕了一大圈排查（先误判物理、又误判主线 dw_mmc 驱动回归，逐项排除 DT/clk/pinctrl/ops 全等价于 vendor）——**真因是 SD 卡没插紧**。带 RINTSTS 打印的 `update-mmc-debug.img`（`boot-sdl-202606191808.txt`）板上插紧后直接枚举：`mmc0: new high speed SDXC card` + `mmcblk0: ... 58.2 GiB` + **8 分区全出来**。那条 debug 打印抓到的 `pending=0x100`（RTO）全在 CMD5/CMD52（SDIO 探测命令）上，是 SD 内存卡被 SDIO 命令探时的正常超时，不是真错。完整排查 + 两次误判的教训见 [22](22-2026-06-19-mmc-sd-error110-investigation.md)。dw_mmc 的 debug 打印已撤（一次性）。

## 现状一句话

**A1 全绿**：Ethernet（双口，link up + DHCP + ping）+ SPI（T1+T2）+ MMC/SD（枚举 + 8 分区）全部板验跑通，驱动全内置。删 vendor_sdk 的 Role 2 门槛，Ethernet/SPI/MMC 这块 DT 已自足——可以开 A2（RMIO 驱动 + I2C/UART2）了。
