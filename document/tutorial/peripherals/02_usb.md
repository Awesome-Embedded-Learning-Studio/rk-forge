# Ch2 — USB：USB2PHY 的两套寄存器和那个父节点坑

> Ch1 三个外设是纯接线，这章 USB 是第一个要动驱动代码的——主线 USB2PHY 驱动里压根没有 rk3506 的 of_match，PHY 不 probe，DWC2 自然拿不到 phy。但动之前我们先逐行扒了 vendor 6.1 的驱动，扒完反而踏实：host 枚举需要的那部分主线几乎现成，真正的弯绕其实藏在 DT 的一个 `status` 上。完整记录见 [notes/28](../../notes/28-2026-06-20-usb-bringup-usb2phy-dwc2.md)。

## 三个 gap，只有一个是驱动

USB bringup 一共三个缺口。主线 `drivers/phy/rockchip/phy-rockchip-inno-usb2.c` 没 `rk3506-usb2phy` of_match，PHY 永远不 probe，这是驱动侧唯一的活儿；DT 这边 forge 那份最小化的 `rk3506.dtsi` 没有 usb2phy、没有 dwc2 节点，得从 vendor 的 `rk3502.dtsi` 搬；config 这边 `PHY_ROCKCHIP_INNO_USB2` 默认关着，更阴的是 `USB_SUPPORT` 整个被我们的 `kernel-trim.config` 砍了（这个坑待会儿单独说）。三个里只有第一个动驱动代码，其余是接线 + config。

## 先 de-risk：RK3506 USB2PHY 的两套寄存器

动驱动之前，我们把 vendor 6.1 的 `phy-rockchip-inno-usb2.c` 逐行读了一遍，扒出一个决定整段移植走向的架构事实——RK3506 的 USB2PHY 寄存器**分两套空间**，不能照搬主线那个"PHY 配置全在 GRF 里"的模型。

第一套是检测 / 电源 / 充电相关，`phy_sus`@0x0060、`bvalid/idfall/idrise/ls_det`@0x0150、`utmi_*`@0x0118、`chg_det`，这些全走 `rphy->grf`，DT 里就是 `rockchip,usbgrf=<&grf>` 那一行（GRF@ff288000）。主线这套 grf-regmap 路径零改动就覆盖了它们——主线驱动早就在用这套机制处理其他 SoC。

第二套是模拟调谐 + 480M clkout 门控，`clkout_ctl`@0x041c、眼高、预加重、差分接收，这些走 `rphy->phy_base`，是 PHY 自己那个 0x8000 大小的寄存器窗 @ff2b0000——主线那个 struct 里压根没有 `phy_base` 字段、probe 里也没有 `ioremap`。

扒完两套空间，最关键的一句结论就出来了：**host 枚举不需要 phy_base 那套硬骨头**。因为 `phy_sus`——真正掌管 PHY 电源开关的那个寄存器——在 GRF 里，主线能动它就能给 PHY 上电；而 DWC2 消费的是 CRU 时钟（`HCLK_USBOTGx` / `_PMU` / `_ADP`），不是 PHY 输出的 480M，所以那个 clkout 门控跟我们这趟无关；剩下的模拟调谐只影响信号质量，不影响能不能枚举。也就是说，只要给主线驱动补一个可选的 `phy_base` 字段、补 rk3506 的 of_match、把 vendor 那几行 tuning 搬进来，host 枚举就能通，不用复刻 vendor 那套发散的 OTG/充电检测模型。

## patch 0014：驱动侧怎么补

[0014](../../../patches/linux/0014-phy-rockchip-inno-usb2-add-RK3506-support.patch) 给主线 inno-usb2 加 RK3506 支持，落点很克制。struct `rockchip_usb2phy` 加一个 `void __iomem *phy_base`，probe 里 `devm_platform_ioremap_resource(pdev, 0)` 拿窗，IS_ERR 就置 NULL——这样经典 GRF-only 的 PHY（节点不带 MEM 资源）完全不受影响，只有 RK3506 这个节点有 MEM 资源、才会真映射。

```c
rphy->phy_base = devm_platform_ioremap_resource(pdev, 0);
if (IS_ERR(rphy->phy_base))
    rphy->phy_base = NULL;
```

`tuning` 钩子 `rk3506_usb2phy_tuning()` 把 vendor 那几行 phy_base 写入搬过来，把它的 `phy_clear_bits` / `phy_update_bits` helper 开成 `readl`/`writel` 的 RMW：otg0/otg1 各自关掉 suspend 下的差分接收（`base+0x030`/`0x430` 的 bit2），把 HS 眼高从默认 450mV 调到 425mV（`GENMASK(6,4)` 写 0x05），再选 TX fs/ls 的 linestate 源（`base+0x094`/`0x494`）。`phy_base` 为 NULL 时这个函数直接 return 0，所以非 RK3506 的 SoC 跑过来是空操作。

of_match 表加 `rockchip,rk3506-usb2phy`，data 指向 `rk3506_phy_cfgs[]`：两个端口（OTG0 / HOST），`phy_sus` 和那一坨 `bvalid/idfall/idrise/ls_det` 检测寄存器全在 GRF 侧（OTG 走 0x0060/0x0150/0x0118、HOST 走 0x0070/0x0170/0x0118），`utmi_iddig` 在主线里叫 `utmi_id`、做个映射。vendor 那套 OTG 的 iddig-force 字段（`bvalid_grf_sel/con`、`iddig_output/en`、`vbus_det_en`、`port_ls_filter_con`）和 `chg_det` 全砍掉——主线 struct 里压根没这些字段、host 也用不到，所以**零 struct 字段新增**。`clkout_ctl` 也不模型化：DT 不带 `#clock-cells`，`clk480m_register()` 自然不会被调用。

## patch 0015：DT 侧搬节点

[0015](../../../patches/linux/0015-ARM-dts-rockchip-rk3506b-aes-add-USB2PHY-DWC2.patch) 在 SoC 级 `rk3506.dtsi` 加 PHY 和两个 DWC2 控制器，板级 `rk3506b-aes.dts` 把它们 enable 起来。SoC 级 PHY 节点长这样：

```dts
usb2phy: usb2-phy@ff2b0000 {
    compatible = "rockchip,rk3506-usb2phy";
    reg = <0xff2b0000 0x8000>;                  /* 同是 cfg-match key 和 phy_base 窗 */
    clocks = <&cru CLK_REF_USBPHY_TOP>, <&cru PCLK_USBPHY>;
    clock-names = "phyclk", "apb_pclk";
    rockchip,usbgrf = <&grf>;                   /* 检测/电源走 GRF */
    status = "disabled";                         /* 板级再 enable */

    u2phy_otg0: otg-port {                       /* IRQ 75/76/77 */
        #phy-cells = <0>;
        interrupts = <GIC_SPI 75 IRQ_TYPE_LEVEL_HIGH>,
                     <GIC_SPI 76 IRQ_TYPE_LEVEL_HIGH>,
                     <GIC_SPI 77 IRQ_TYPE_LEVEL_HIGH>;
        interrupt-names = "otg-bvalid", "otg-id", "linestate";
        status = "disabled";
    };
    u2phy_otg1: host-port { /* IRQ 80/81/82, 同结构 */ };
};
```

注意 `reg` 的第一个 cell `0xff2b0000` 同时干两件事：它是 `rk3506_phy_cfgs[].reg` 的 cfg-match key（驱动用 of_match 数据按这个找到对应 cfg），它又是 `phy_base` 那个 ioremap 窗的物理基址。一份 reg 两份用途，正好把两套寄存器空间串起来。

DWC2 这边更省心。两个控制器 `usb@ff740000` / `usb@ff780000` 用 `compatible = "rockchip,rk3066-usb", "snps,dwc2"`，dwc2 主线驱动认 `snps,dwc2` 这个 fallback 就 bind，所以**完全不用动 dwc2 驱动**。phys 引 `&u2phy_otg0` / `&u2phy_otg1`，时钟是 CRU 那三路（`otg` / `pmu` / `adp`），印证了前面那句"DWC2 不消费 PHY 480M"。板级 dts 把两个端口和两个控制器都改成 `dr_mode="host"` enable 起来——板上 USB-A 哪个口落外设都 enum 得到，OTG/gadget 留后续。

## 坑之一：kernel-trim 把 USB 整个砍了

config 这边有个能闪一板的东西。`PHY_ROCKCHIP_INNO_USB2=y` 和 `USB_DWC2_HOST=y` 在 `kernel.config` 里加得好好的，可第一次构建出来 `.config` 一看——USB 整个没了，`CONFIG_USB_SUPPORT is not set`，DWC2 / `PHY_ROCKCHIP_INNO_USB2` / `USB_STORAGE` 连个 `# ... is not set` 都不算，是直接消失。

根因在合并顺序。`build-linux.sh` 是按 `multi_v7 → kernel.config → kernel-trim → kernel-compress` 串起来跑 olddefconfig 的，trim 跑在 kernel.config **之后**、能盖掉它。我们那份 `board/rk3506-evb/kernel-trim.config` 里有一行 `# CONFIG_USB_SUPPORT is not set`（早期列"暂时不需要的子系统"时塞进去的），而 `USB_SUPPORT` 是顶层 menuconfig——它一关，下面所有 USB 符号被 olddefconfig 全清。同样的坑之前 SOUND 也踩过一次。修法很朴素：trim 里把那行删掉。**养成一个习惯**：加完 config 不仅要看 fragment，要去 grep 实际构建出的 `.config`——合并顺序藏着的覆盖，fragment 看不出来。

## 坑之二：USB2PHY 父节点 disabled，DWC2 永远拿不到 phy

驱动、DT、config 三件齐了，第一次上板（[boot-sdl-202606200858](../../logs/boot-sdl-202606200858.txt)）USB 是死的。DWC2 报 `error getting phy`、deferred probe 挂着不奇怪，奇怪的是 dmesg 里**根本没有 `rockchip-usb2phy ff2b0000` 的 probe 行**——也就是说 PHY 这个 provider 压根没起来，DWC2 defer 是对的。

```
[   12.010085] platform ff740000.usb: deferred probe pending: dwc2: error getting phy
[   12.010816] platform ff780000.usb: deferred probe pending: dwc2: error getting phy
```

根因是个 DT bug，跟驱动无关。SoC 那个 `usb2phy` **父节点**出厂是 `status="disabled"`，我第一次只 enable 了子端口（`&u2phy_otg0/1`）。可 `phy-rockchip-inno-usb2` 是绑**父节点**的——带 `rk3506-usb2phy` compatible 的就是它，子端口是驱动 probe 完之后才发布的 phy。父节点 disabled，OF core 连它的 platform device 都不建，驱动自然不 probe，DWC2 就永远等不到 phy。换句话说，子节点 enable 是没用的——它爹还没起来，它压根没被生出来。

修就一行，照 vendor evb 的写法（`rk3506-evb2-v10.dtsi` 就是连父带子一起 enable）：

```dts
&usb2phy { status = "okay"; };
&u2phy_otg0 { status = "okay"; };
&u2phy_otg1 { status = "okay"; };
&usb20_otg0 { dr_mode = "host"; status = "okay"; };
&usb20_otg1 { dr_mode = "host"; status = "okay"; };
```

这条坑其实有个普适规则值得记住：**provider/consumer 这一对里，驱动真正 of_match 的那个节点（带 compatible 的那个）必须 enable**，光 enable 它创建出来的子节点不够。我们这趟父节点是 provider、子节点是它发布的 phy，所以父节点一定要开。

## 成功长这样

父节点 enable 重烧，[boot-sdl-202606200858](../../logs/boot-sdl-202606200858.txt) 这次 USB 全通——两个 DWC2 都注册成 host、一个 USB hub 加 U 盘枚举成功、挂成 `/dev/sda`：

```
dwc2 ff740000.usb: DWC OTG Controller / new USB bus registered, bus number 1
dwc2 ff780000.usb: DWC OTG Controller / new USB bus registered, bus number 2
usb 2-1: new high-speed USB device number 2 using dwc2          ← 枚举
usb 2-1.3: new high-speed USB device number 3 using dwc2         ← hub 后面挂的
usb-storage 2-1.1:1.0: USB Mass Storage device detected
sd 0:0:0:0: [sda] Attached SCSI removable disk                   ← /dev/sda
```

`supply vusb_d/vusb_a not found → dummy regulator` 那行是 vbus 的非问题——板上 USB-A 的 5V 是常供电、没建模成 regulator，无害。USB 这章 closed。

板载那颗 WiFi dongle，此刻就枚举在 USB 总线上——只是还没驱动认它。下一章我们就给这颗 RTL8733BU 搬驱动，让它从"枚举出来的设备"变成"能联网的 wlan0"。我们 Ch3 见。
