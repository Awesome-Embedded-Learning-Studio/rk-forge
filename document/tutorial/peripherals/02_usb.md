# Ch2 — USB：USB2PHY 的两套寄存器和那个父节点坑

> Ch1 三个外设是纯接线，这章 USB 是第一个要动驱动代码的——主线 USB2PHY 驱动缺一个 rk3506 的 of_match，PHY 不 probe，DWC2 就拿不到 phy。不过别紧张，逐行读了 vendor 驱动之后我们发现，host 枚举需要的那部分主线几乎现成就能用。真正的坑反而藏在 DT 的一个 `status` 上。完整记录见 [notes/28](../../notes/28-2026-06-20-usb-bringup-usb2phy-dwc2.md)。

## 前言：三个 gap，只有一个是驱动

USB bringup 有三个缺口：驱动（USB2PHY 缺 rk3506 of_match）、DT（没 usb2phy/dwc2 节点）、config（`PHY_ROCKCHIP_INNO_USB2` 关了、`USB_SUPPORT` 还被 trim 砍了）。三个里只有第一个要动驱动代码，其余是接线 + config。

## 先 de-risk：RK3506 USB2PHY 的两套寄存器

动驱动之前，我们先逐行读了 vendor 6.1 的 USB2PHY 驱动，发现一个关键的架构事实——RK3506 的 USB2PHY 用**两套寄存器空间**：

- **检测/电源/充电**（`phy_sus`、`bvalid/idfall`、`utmi_*`、`chg_det`）全走 **`rphy->grf`**（DT 里 `rockchip,usbgrf=<&grf>`，GRF@ff288000）。**主线的 grf-regmap 路径零改动就覆盖了这些。**
- **模拟调谐 + 480M clkout 门控**（`clkout_ctl`、眼高、预加重）走 **`rphy->phy_base`**（PHY 自己的寄存器窗 @ff2b0000）。主线那个 struct **没有 phy_base、没有 ioremap**。

最关键的一句：**host 枚举不需要 phy_base 那套硬骨头**。因为 `phy_sus`（真正的电源开关）在 GRF 里、主线能动它，PHY 就能上电；而 DWC2 消费的是 CRU 时钟（不是 PHY 的 480M），所以 clkout 门控无关紧要；模拟调谐只影响信号质量、不影响枚举。也就是说，只要给主线驱动补一个 phy_base 字段、补 rk3506 的 of_match、把 vendor 的几行 tuning 搬进来，host 枚举就能通，不用复刻 vendor 那套发散模型。

## patch 0014 + 0015

[0014](../../../patches/linux/0014-phy-rockchip-inno-usb2-add-RK3506-support.patch) 给主线 inno-usb2 加 RK3506 支持：struct 加一个 `void __iomem *phy_base`，probe 里 `devm_platform_ioremap_resource` 拿 phy_base（IS_ERR 就置 NULL——经典 GRF-only 的 PHY 不受影响，只有 RK3506 节点有 MEM 资源），`rk3506_usb2phy_tuning()` 搬 vendor 的几行 phy_base 写入，of_match 加 `rockchip,rk3506-usb2phy`。OTG 的 iddig-force、充电检测那些主线 struct 没字段的，全砍掉（host 用不到），所以**零 struct 字段新增**。

[0015](../../../patches/linux/0015-ARM-dts-rockchip-rk3506b-aes-add-USB2PHY-DWC2.patch) 是 DT：`usb2phy@ff2b0000`（rk3506-usb2phy，usbgrf）+ `u2phy_otg0/1`（两个 PHY 端口）+ `usb@ff740000`、`usb@ff780000`（DWC2，用 `snps,dwc2` fallback——**不用动 dwc2 驱动**，它认这个 fallback 就 bind）。

config 要点：`PHY_ROCKCHIP_INNO_USB2=y` + `USB_DWC2_HOST=y`。这里有个 trim 的坑——我们的 `kernel-trim.config` 里有一行 `# CONFIG_USB_SUPPORT is not set`，它是**在 kernel.config 之后应用的**，会把所有 USB 砍光。第一次构建出来 DWC2/PHY 全没，就栽在这；删了那行才好。

## 坑：USB2PHY 父节点 disabled，DWC2 拿不到 phy

驱动、DT、config 都弄好，第一次上板（[boot-sdl-202606200858](../../logs/boot-sdl-202606200858.txt)）USB 是死的——DWC2 报 `error getting phy`，deferred probe 挂着；更关键的是 dmesg 里**根本没有 `rockchip-usb2phy ff2b0000` 的 probe 行**，PHY 提供者压根没起来。

根因是个 DT bug，不是驱动问题：SoC 那个 `usb2phy` **父节点**是 `status="disabled"`，我只 enable 了子端口（`&u2phy_otg0/1`）。可 inno-usb2 是绑**父节点**的（带 `rk3506-usb2phy` compatible 的那个），子端口是它 probe 之后才发布的 phy。父节点 disabled，OF core 都不给它建 platform device，驱动自然不 probe，DWC2 就永远拿不到 phy。

修就一行：板级 dts 加 `&usb2phy { status = "okay"; };`（照 vendor evb 的写法，它也是连父带子一起 enable）。驱动 patch 和 DWC2 都没问题。

## 成功长这样

父节点 enable 重烧，[boot-sdl-202606200858](../../logs/boot-sdl-202606200858.txt) 这次 USB 全通——T1+T2+T3：

```
dwc2 ff740000.usb: DWC OTG Controller / new USB bus registered, bus number 1
dwc2 ff780000.usb: DWC OTG Controller / new USB bus registered, bus number 2
usb 2-1: new high-speed USB device number 2 using dwc2          ← 枚举
usb 2-1.3: new high-speed USB device number 3 using dwc2         ← hub 后面挂的
usb-storage 2-1.1:1.0: USB Mass Storage device detected
sd 0:0:0:0: [sda] Attached SCSI removable disk                   ← /dev/sda
```

两个 DWC2 都注册成 host，一个 USB hub 加 U 盘枚举成功、挂成 `/dev/sda`。`supply vusb_d/vusb_a not found → dummy regulator` 是 vbus 的非问题，无害。USB 这章，closed。

板载那颗 WiFi dongle，此刻就枚举在 USB 总线上——只是还没驱动认它。下一章我们就给这颗 RTL8733BU 搬驱动，让它从"枚举出来的设备"变成"能联网的 wlan0"。我们 Ch3 见。
