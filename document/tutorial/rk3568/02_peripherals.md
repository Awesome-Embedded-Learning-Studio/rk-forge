# Ch2 — 板级 DT 八子系统：从"能启动"到"能用"

> 上一章把 RK3568 跑到了 login，可那会儿用的是主线自带的 `rk3568-evb1-v10.dtb`（Rockchip EVB1 的 DT）——它能让你 boot，但 ATK 板上那些 EVB1 没有的东西（双网口的 PHY 时序、LCD 屏、触摸、CAN、RTC、PMIC 的 io-domain）一概不认。这一章咱们写一块 ATK 专用的板级 DT（`rk3568-atk-evb1-ddr4-v10.dts`，脱离复用 evb1-v10），把八个子系统一次移植过去。完整方案见 [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)（DT 移植方案），板验状态见 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)。

> ⚠️ 先把工程债说在前头：这一章对应的板级 DT 和 panel descriptor，目前是 `third_party/src/rk3568-atk/linux/` 里的 working-tree delta，还没正式 quilt 化进 `patches/rk3568-atk/linux/series`（那个 series 现在只带 WiFi 接线）。也就是说，本章教的是移植方法 + 真机证据，但第二人 `forge setup` clone 下来，复现不了这些外设——把这块板 DT patch 化（P4）是它进版本控制、能被别人复现的前置。在 P4 落定前，你把这一章当「咱们当时怎么移植的」来读。

## 为什么要写专用 ATK DT

RK3568 的主线支持很完整——`rk3568.dtsi` 里 SoC 级的控制器（GMAC、USB、eMMC、I2C、SPI、VOP、DSI……）全有。可板级的东西不在 SoC dtsi 里：ATK 板用的 PHY 是 RTL8211F（要 RGMII delay）、屏是 10.1" MIPI、触摸是 GT911、PMIC 是 RK809、还要 io-domain 配置——这些得在板级 `.dts` 里声明。复用主线 evb1-v10 的 DT，等于让板子戴着别人的帽子跑，SoC 能起、外设不认。

所以咱们另起一个 `rk3568-atk-evb1-ddr4-v10.dts`，phandle 对齐 `rk3568.dtsi`，把 ATK 板的八个子系统接进去。这八个里大半是「主线驱动直接能用、只要在 DT 里接线」（内部叫 A 类），LCD 是「主线有驱动骨架、要补一块数据 descriptor」（C 类，极小），WiFi 是「主线没驱动、得搬 vendor」（C 类，硬阻塞，单独一章不在这卷）。

## 机制铺垫：kernel.config 的"框架总开关"

正式点亮之前，先说一个贯穿所有外设的坑：显示/网络/音频这一栈的框架总开关，漏一个就整栈降级成 `=m`。RK3568 这条线上踩了三次。

第一次是 `STMMAC_ETH`、`DWMAC_ROCKCHIP` 编成模块——buildroot busybox 的 rootfs 没有 modprobe，模块永远不加载，dmesg 一行 eth 都没有，`/sys/class/net` 只有 lo。第二次是 `DRM` 框架总开关漏——漏了它，整条显示栈（`DRM_ROCKCHIP` / `VOP2` / `DW_MIPI_DSI` / panel / PHY / backlight）全跟着降成 `=m`，DRM 不 probe。第三次是 `SOUND` 框架漏——`SND` / `SND_SOC` / `RK817` 整栈 `=m`，声卡不 probe。

[board/rk3568-atk/kernel.config](../../../board/rk3568-atk/kernel.config) 里那一大段 `=y`，就是把这些框架总开关和具体驱动符号一个个显式钉成 built-in。规矩就一条：这一栈的符号逐个 `grep .config` 确认 `=y`，别信「会自动 select」。

## 子系统逐个点亮

这八个子系统按移植难度分三档：接线就能亮的（A 类）、补一块数据 descriptor 的（LCD）、搬 vendor 驱动的（WiFi，不在这卷）。咱们按「先顺的、再卡住的、最后要写代码的」这个顺序走。

大半是 A 类——主线驱动直接能用，咱们要做的只是把 ATK 板的具体硬件（PHY 型号、屏参、GPIO）在 DT 里接上线。双网口走两个 RTL8211F，给 gmac0/gmac1 配上 RGMII 的 phy-mode 和收发 delay，eth0/eth1 就亮；PMIC 是 RK809，给全板供电，顺带把 io-domain 按板上的 1.8V / 3.3V 配好（这步配错外设会不稳，是 A 类里唯一要动脑子的地方）；触摸 GT911（板上是 GT928），主线 goodix 驱动会 runtime 读 chip_id 自己适配，配上 falling-edge 的 IRQ 就有 `/dev/input/event0`；GPU 也在这档，主线 Panfrost 直接驱动 Mali-G52，板验看到 card1（card0 留给显示）。剩下 CAN1（rockchip_canfd）、RTC（pcf8563）、PWM 风扇（这里有个小坑要记一下：fan-supply 是 `dc_12v` 不是 5V，照惯例抄 5V 会带不动）、HDMI、eMMC HS200、TF 卡槽——全是接线即亮，没故事。这一档走完，板子已经「能用」一大半了。

音频本来也该是 A 类，结果卡住了。这板没有 ES8388，模拟音频走 RK809 内置的 codec（主线 `rk817_codec.c`），machine driver 用 `simple-audio-card`——主线都有。可板验时 rk809-sound 声卡没 probe，dmesg 报：

```
gpio1-4 already requested by fe410000.i2s; cannot claim for rk809-sound
```

hp-det 那根 GPIO（gpio1 PA4）抢了 i2s1 的 mclk。这是 DT 接线冲突，不是驱动缺——换根 hp-det GPIO、或让 i2s1 mclk 的 pinctrl 避开 gpio1-4 就能解。当时没改完，只剩 BT SCO（card0）顶在那里。

LCD 是八个里唯一要补代码的，而且它的 IC 身份还有争议——单独开一节说。

## LCD 的身份矛盾：HX8394 还是 ILI9881C？

LCD 是八个里唯一需要补代码的（C 类，极小），可它的 IC 身份在咱们的笔记里自相矛盾，这里如实摆出来。

[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 的 workflow 分析（8 个 agent、567k tokens 那一轮）从 vendor 给的 init sequence 首命令认出来的：序列起于 `B9 FF 83 99`，这是 Himax 的 SETEXTC 命令——所以 IC 是 HX8394，不是最初以为的 ILI9881C。好消息是主线 `drivers/gpu/drm/panel/panel-himax-hx8394.c` 已经存在，移植不是搬 vendor 驱动，而是给它加一块 ~250 行的纯数据 descriptor（`atk_10p1_init_sequence` + `atk_10p1_desc` + of_match 项 `atk,rk3568-evb1-hx8394-10p1`），把 vendor init sequence 翻译进去。

可 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 交接时，板验状态表写的是「ILI9881C driver + ATK DT 点亮」——和 41 的 HX8394 结论对不上。这两篇笔记不一致，真机实际是哪颗 IC，得在板上读芯片 ID、或核对 init sequence 首命令才能定。

> 咱们这里采纳 [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 的 HX8394 结论——因为它有 workflow 的推理依据（从 SETEXC 命令认出来的，不是猜的），而且「主线已有 `panel-himax-hx8394.c`、只补 descriptor」这条路更干净。但你真机核对时如果确认是 ILI9881C，那就走主线 `panel-ilitek-ili9881c.c` 加 descriptor（和 RK3588 那块屏的套路一样）。这个矛盾教程里不替你拍板，标出来等你定。

不管 IC 是哪颗，移植套路是一样的：主线 `drm_panel` 驱动已有骨架，咱们补一块 vendor init sequence 的纯数据 descriptor，配上 `lanes=4`、vendor 的 timing、`VIDEO_BURST` mode flag。这块 descriptor 当时加了之后屏亮了（`card0-DSI-1 connected`，fb0 写入）。

> LCD 还有两条 critique（[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)）：一是电源——草案把 `vcc/iovcc` 都指 3.3V，但 IOVCC 物理常是 1.8V，`panel-himax-hx8394.c` 用 `devm_regulator_get`（非可选），缺就 `-EPROBE_DEFER`，二烧前要查 ATK 原理图确认 IOVCC 实际 LDO + 控制 GPIO；二是 `&sata2` 别误 disable（synthesis 曾误判 pcie3x2/sata2 抢 combphy2，实际 pcie3x2 用专用 pcie30phy，sata2 用 combphy2，不冲突）。

## canonical：板级 DT 与 kernel fragment 的形状

板级 DT 的结构定型为：phandle 对齐 `rk3568.dtsi`，`&gmac0/&gmac1`（RTL8211F RGMII + delay）、`&i2c*`（RK809 / GT911 / pcf8563）、`&dsi1`（panel 节点 + panel descriptor）、`&can1`、`&sata2{status=okay}`、backlight（default-brightness 255，不是草案的 100）、fan-supply（`dc_12v`）。Makefile 加 `dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3568-atk-evb1-ddr4-v10.dtb`。

kernel fragment 把整栈钉 `=y`（节选）：

```
# Ethernet（曾 =m 无 eth）
CONFIG_STMMAC_ETH=y
CONFIG_DWMAC_ROCKCHIP=y
CONFIG_REALTEK_PHY=y
# DRM（曾漏框架总开关整栈 =m）
CONFIG_DRM=y
CONFIG_DRM_ROCKCHIP=y
CONFIG_ROCKCHIP_VOP2=y
CONFIG_ROCKCHIP_DW_MIPI_DSI=y
CONFIG_DRM_PANEL_HIMAX_HX8394=y     # 或 ILI9881C，看真机核对
CONFIG_PHY_ROCKCHIP_INNO_DSIDPHY=y  # 漏了 dsi1 defer 屏不亮
CONFIG_BACKLIGHT_PWM=y
# Audio（曾漏 SOUND 整栈 =m）
CONFIG_SOUND=y
CONFIG_SND_SOC=y
CONFIG_SND_SOC_RK817=y
CONFIG_SND_SIMPLE_CARD=y
# 触摸 / CAN / RTC / GPU
CONFIG_TOUCHSCREEN_GOODIX=y
CONFIG_CAN_ROCKCHIP_CANFD=y
CONFIG_RTC_DRV_PCF8563=y
CONFIG_DRM_PANTHOR=y
```

## 成功长这样

一轮大重 build 之后（kernel dtbs/Image + u-boot + 重 pack），板验（[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)）：

```
...（主线 7.1 boot）
eth0: ... RTL8211F ...                # 双 GMAC 通
eth1: ... RTL8211F ...
rockchip-pmics ... rk809 ...          # PMIC
[drm] Initialized rockchip ...        # DRM 起
card0-DSI-1: connected, fb0           # LCD 点亮
panthor mali-g52 id 0x7402, card1     # GPU
Goodix GT928, /dev/input/event0       # 触摸
rockchip_canfd can0                   # CAN
pcf8563                               # RTC
rk3568 login:
```

到这一步，RK3568 从「只启动」变成「能用」——八个子系统里除了音频（gpio 冲突）和 WiFi（待搬 vendor 驱动），其余都板上验证通过。

> 老实把没收尾的列这：音频 RK809（hp-det 抢 i2s1 mclk，声卡没 probe）；WiFi rtl8852bs（SDIO 总线通、主线 rtw89 无 SDIO，待搬 vendor 851 文件驱动）；USB3 / PCIe / VPU / NPU（deferred 或 roadmap）。这些是后续。
