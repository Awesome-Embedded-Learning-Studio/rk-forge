# ATK-DLRK3568 主线 DT 移植方案 (2026-07-26)

为 ATK 板建主线专用 `rk3568-atk-evb1-ddr4-v10.dts`(脱离复用 evb1-v10),把 ATK 主要驱动一次移植。workflow 8 agents / 567k tokens / 子系统分析 + synthesis + critique。

## 核心结论

| 子系统 | 分类 | 首烧通否 |
|---|---|---|
| PMIC/电源/io-domain (RK809) | A 主线直接 | ✅ |
| 以太网 (2× RTL8211F rgmii+delay) | A | ✅ |
| 音频 (**RK809 PMIC codec, 板上无 ES8388**) | A | ✅ |
| 触摸 (GT911) + adc-keys | A | ✅ |
| HDMI/USB/eMMC/TF/CAN1/RTC/fan | A | ✅ |
| **LCD** (10.1寸 800x1280 MIPI, IC=**Himax HX8394**) | C(极小) | 加 panel descriptor 后通 |
| **WiFi** rtl8852bs SDIO | C(硬阻塞) | 搬 vendor rtw89 SDIO |

**LCD 关键修正**:原以为 IC=ILI9881C,实际 init 起于 `B9 FF 83 99`=Himax SETEXTC → IC=**HX8394**。主线 `drivers/gpu/drm/panel/panel-himax-hx8394.c` 驱动**已存在**,移植=加 ~250 行纯数据 descriptor(`atk_10p1_init_sequence` + `atk_10p1_desc` + of_match 项 `atk,rk3568-evb1-hx8394-10p1`)。**不搬 vendor panel driver**。

**音频关键修正**:板上**无 ES8388**,模拟音频走 RK809 PMIC 内置 codec(`rk817_codec.c`),主线 `CONFIG_SND_SOC_RK817`。machine driver 用 `simple-audio-card`(vendor `rockchip,multicodecs-card` 非主线)。

## critique 必改(2 major)

1. **sata2 不要 disable**:synthesis 误判 pcie3x2/sata2 抢 combphy2。实际 pcie3x2 用 `pcie30phy`(专用),sata2 用 `combphy2`,不冲突。`&sata2 { status="okay"; }`。真正抢 combphy2 的是 pcie2x1(ATK 没用)。
2. **LCD 电源待原理图**:草案 `vcc/iovcc` 都指 `vcc3v3_lcd1_n`(3.3V),但 IOVCC 物理常 1.8V。`panel-himax-hx8394.c` 用 `devm_regulator_get`(非可选),缺则 -EPROBE_DEFER。**二烧前查 ATK 原理图**:面板 VDD/IOVCC 实际 LDO + 控制 GPIO + IOVCC 电压(1.8V 则 iovcc-supply 改 `&vcca_1v8`)。另:`himax,hx8394` fallback 在主线 of_match 不存在(descriptor 没加前 panel -ENODEV,不阻塞 boot 但 dmesg noise)。

## critique minor(真机再调)

- goodix compatible = `goodix,gt911`(推断自 tp-size=911,主线驱动 runtime 读 chip_id 适配,能 bind)
- 触摸供电(AVDD28/VDDIO)抄 vendor `vcc5v0_sys`,待原理图
- backlight default-brightness 草案 100,vendor 255
- **fan-supply 应 `dc_12v`**(vendor,12V 风扇),草案误写 vcc5v0_sys
- GT911 reset/irq 极性已按主线 goodix 转换(EDGE_FALLING),真机看中断

## 落地清单

1. **主线 DT**: `arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dts`(workflow §2 草案 625 行,phandle 对齐 rk3568.dtsi)+ Makefile 加 `dtb-$(CONFIG_ARCH_ROCKCHIP) += rk3568-atk-evb1-ddr4-v10.dtb`
2. **LCD panel descriptor**: `drivers/gpu/drm/panel/panel-himax-hx8394.c` 加 `atk_10p1`(翻 vendor init seq,~250 行数据)
3. **kernel defconfig**: 网络(STMMAC/DWMAC_ROCKCHIP =y)、音频(SND_SOC_RK817/simple-card)、触摸(GOODIX/ADC)、LCD(HIMAX_HX8394/BACKLIGHT_PWM)、CAN/RTC/fan 等 =y
4. **u-boot**: BOOTCOMMAND 改直接 mmc boot(绕 bootflow)+ BAUDRATE 115200
5. **boot.scr 0x08000000**(已改)+ ATK DT stdout 115200
6. 重 build(kernel dtbs/Image + u-boot)+ 重 pack

## 期望(一次移植通过)

- **首烧**:serial2 console + eMMC/TF + **eth0/1(DHCP)** + USB + **RK809 音频 aplay -l 见 "Analog RK809"** + CAN1/RTC/fan + HDMI
- **二烧**(加 panel descriptor + 原理图确认电源):**DSI1 屏点亮 + GT911 触摸 + 背光**
- **WiFi/BT**(独立任务):搬 vendor rtl8852bs SDIO 驱动 + 固件

rtl8852bs 是唯一硬阻塞(主线 rtw89 无 SDIO),首烧 WiFi 不通是预期。

---
完整 DT 草案 + defconfig + 风险表见 workflow report(workflow wnjx5whwc, /tmp/dt-port-report.md)。参见 [notes/40](40-2026-07-26-rk3568-first-boot-and-next-push.md)(首次 boot 成功)。
