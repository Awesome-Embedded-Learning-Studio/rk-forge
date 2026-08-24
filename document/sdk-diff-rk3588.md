# sdk-diff — RK3588 topeet: vendor BSP vs 主线移植(诚实差距报告)

> rk-forge 的"诚实证明器"。逐子系统对比 topeet vendor BSP(`reference/rk3588/`,kernel 5.10.198
> + vendor U-Boot 2017.09 + rkbin)与我们主线移植(linux 7.1 + U-Boot 2026.07-rc4 + Ubuntu 26.04)
> 的差距。**不美化、不隐藏**:说清 BSP 有什么、主线有没有、差什么、还能不能 boot。本文随 bringup
> 推进持续更新。
>
> **状态(活文档)**:主线 7.1 + 主线 U-Boot(主线 SPL + rkbin DDR/BL31 blob)从 eMMC 启动到 Ubuntu
> 26.04 GNOME 桌面;8 核(A76×4+A55×4)/16GB LPDDR4X/eMMC HS400/PMIC rk806/CPU 调压 rk8602/rk8603/
> GMAC0 RGMII/USB2 host×2/GPU Panthor Mali-G610/10.1" 1024×600 DSI→LVDS 屏 + GT911 触摸坐标链路
> 全部点亮。**VOP2 dclk handoff 修复(patch 0009)是候选镜像,连续冷/热启动稳定性未闭环,不写成
> 稳定支持。** 最新里程碑见 [notes/48(GPU/GNOME)](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)、
> [notes/50(首启 systemd)](notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md)、
> [notes/54(VOP2 dclk 候选)](notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)、
> [notes/55(GT911 轴)](notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)、
> [notes/56(Ubuntu 用户/ownership)](notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md)。

## 一句话结论

**主线 Linux 7.1 + 主线 U-Boot 2026.07 在 iTOP-RK3588(topeet)从 eMMC 启动到 Ubuntu 26.04 GNOME 桌面
——8 核 big.LITTLE + eMMC HS400 + GMAC0 + USB2 host×2 + PMIC rk806 + rk8602/rk8603 调压 + GPU Panthor
Mali-G610(renderD128)+ 10.1" 1024×600 DSI→LVDS 屏 + GT911 触摸坐标链路 全主线打通。** 启动链前段仍
**借闭源 rkbin blob**(DDR init + BL31/ATF;SPL 已切主线——vendor `rk3588_spl` v1.13 与 BL31 v1.54 基址
错配会 bootloop,见 [notes/49](notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md))。WiFi/BT、NPU、
VPU/MPP、RGA、摄像头、PCIe/NVMe、USB3/Type-C、SD 卡、gmac1、RTC、音频 均为 roadmap,主线 DT 未接。

## "RK-SDK residue" 残留度量

PLAN 论点:**"取代 RK-SDK 的 build.sh,不是取代整个 RK-SDK"**。诚实量一下主线 boot 还残留多少 vendor 东西:

| 残留项 | 性质 | 状态 |
|---|---|---|
| DDR init blob(`rk3588_ddr_lp4_2112_lp5_2400`) | 闭源 blob(rkbin) | 用作 binman TPL(BootROM→DDR init)。来源为公开 rockchip-linux/rkbin submodule |
| BL31 / ATF(`rk3588_bl31_v*.elf`) | 闭源 blob(rkbin) | binman 嵌入 `u-boot.itb`,PSCI/SMC 由它提供(v1.54,基址 0x60000) |
| ~~vendor `rk3588_spl` v1.13/1.14~~ | ~~闭源 blob~~ | **已排除**:旧 SPL 早于 BL31 v1.54 → 跳错基址 → bootloop([notes/49](notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md))。改用 build-uboot 主线 SPL |
| ~~vendor U-Boot 2017.09~~ | ~~整套 vendor loader~~ | **已替换**:主线 U-Boot 2026.07-rc4(`evb-rk3588_defconfig` + binman),只借 rkbin DDR + BL31 |
| ~~vendor mkimage 2017.09 / afptool / rkImageMaker~~ | ~~打包税~~ | **已消除**:forge 纯 Python([scripts/fit-pack.py](../scripts/fit-pack.py) / [scripts/rkfw-pack.py](../scripts/rkfw-pack.py)),同 RK3506B |
| GPU 固件 `mali_csffw.bin` | 闭源固件(Arm,linux-firmware) | **内建进 kernel**(`CONFIG_EXTRA_FIRMWARE`),非 blob 残留;Panthor early-probe 在 rootfs 挂前要([notes/48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)) |
| board DT(`rk3588-topeet.dts`) | **我们写的**,非残留 | 从 vendor `topeet-rk3588-linux.dts` 移植;上游化目标 |

→ 残留 = **DDR init + BL31/ATF blob**(均闭源 rkbin;来源为公开仓 submodule)。比 RK3506B 多一项进步:
**主线 SPL 在 RK3588 上 work**(RK3506B 方案 A 未成);但 DDR + BL31 这两层是 RK 平台的硬现实,改不了。
vendor U-Boot 整套已替换、打包链纯 Python 化。论点**成立**:build 全换主线(U-Boot + kernel 全主线源码 +
patch),启动前段(DDR/secure)仍离不开闭源 rkbin blob。

## 子系统逐项对比

图例:✅ 工作并验证 · ⚠️ 驱动在主线但未接进我们 DT / 部分验证 · ❌ 主线缺 / 未做 · 🟡 借闭源 blob

vendor 侧信息来自 `reference/rk3588/` 实地读取:vendor kernel DT(`topeet-rk3588-linux.dts` +
`topeet-rk3588-linux.dtsi` + `topeet-screen-lcds.dts` + `rk3588-rk806-single.dtsi`)、vendor defconfig
(`rockchip_linux_defconfig` + `rk3588_linux.config` 片段)、vendor U-Boot(`configs/rk3588_defconfig`,
2017.09)、rkbin(`bin/rk35/` + `RKBOOT/RK3588MINIALL.ini`)。

| 子系统 | vendor BSP(5.10.198) | 主线移植(7.1) | 差距 / 闭合路径 |
|---|---|---|---|
| **CPU SMP(A76×4+A55×4 big.LITTLE)** | ✅ SMP 8 核,`ROCKCHIP_CPUFREQ` + schedutil | ✅ **8 核起来**(log `Brought up 1 node, 8 CPUs`;VIPT 0-3=A55、PIPT 4-7=A76) | 无 |
| **clk / reset** | ✅ vendor cru | ✅ 主线 clk-rk3588 / rst-rk3588 | 无 |
| **pinctrl / GPIO** | ✅ | ✅ bank probe | 无 |
| **UART console(ttyFIQ0 @ UART2)** | ✅ vendor FIQ debugger(serial-id=2、baudrate=115200、irq-mode-enable=1、SPI 423) | ✅ **vendor FIQ debugger 完整移植到 7.1**(patch 0003),ttyFIQ0 @115200;`&uart2` 禁用、serial8250 不绑([notes/51](notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)) | 已闭合 |
| **PSCI / ATF(BL31)** | 🟡 vendor rkbin BL31 v1.51(`rk3588_bl31_v1.51.elf`) | 🟡 公开 rkbin BL31 v1.54(binman 嵌 `u-boot.itb`);**SPL 切主线** | blob 残留(DDR+BL31);SPL 已闭合([notes/49](notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)) |
| **GIC / timer** | ✅ GICv3(`ARM_GIC_V3` + ITS) | ✅ GICv3(log `GICv3: GICD_CTLR.DS=0, SCR_EL3.FIQ=1`) | 无 |
| **eMMC(HS400,sdhci)** | ✅ `sdhci-of-dwcmshc`,HS400 ES,200MHz | ✅ **mmcblk0 HS400 Enhanced strobe**(log `new HS400 Enhanced strobe MMC card`、`p1 p2 p3`、METORA 116GiB) | 已闭合 |
| **Ethernet GMAC0(RGMII,RTL8211F)** | ✅ stmmac / `DWMAC_ROCKCHIP`,`rgmii-rxid`,tx_delay=0x44 | ✅ DT 已接(patch 0002),log `Active PHY interface: RGMII` | 已闭合 |
| **Ethernet GMAC1** | ✅ 第二口(gmac1 + rgmii_phy1) | ❌ DT 未接(topeet 单 eth 够用) | roadmap(非 bringup 必需) |
| **USB2 host ×2** | ✅ u2phy2/3 + `usb_host0/1_ehci/ohci` | ✅ DT 已接(patch 0002 双 host) | 已闭合 |
| **USB3 / Type-C(dwc3 + usbdp + fusb302)** | ✅ `usbdrd3_0/1` + `dwc3` + `usbdp_phy0/1` + `fusb302@22`(i2c6,altmode) | ❌ DT 未接 | roadmap |
| **PCIe / NVMe(pcie3x4)** | ✅ `pcie3x4` + `pcie30phy`(NANBNB) | ❌ `CONFIG_PCIE_ROCKCHIP_HOST=y` 已开,但 topeet DT 未接 | roadmap(Phase 2) |
| **PMIC rk806(single,spi2)** | ✅ vendor `MFD_RK806_SPI` + `REGULATOR_RK806` | ✅ DT 已接(patch 0002 完整 regulator 树,照 `rk3588-fet3588-c.dtsi`) | 已闭合 |
| **CPU/NPU 稳压器 rk8602/rk8603** | ✅ vendor `REGULATOR_RK860X` 驱动(i2c0 big0/big1、i2c1 npu) | ✅ **vendor rk860x 驱动移植到 7.1**(patch 0004),关掉 fan53555 误认;DVFS `-110` 消失([notes/51](notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)) | 已闭合 |
| **I2C(rk3x-i2c)** | ✅ i2c0/1/2/3/4/6/7 | ✅ i2c0/1/2 接 DT;**vendor 超时恢复 + SLV_HDSCL 检测 + 双 reset domain 移植**(patch 0004) | 已闭合(所用总线);i2c3/4/6/7 待外设 |
| **SD 卡(sdmmc / dw_mmc)** | ✅ `MMC_DW_ROCKCHIP`,UHS-SDR104 | ❌ DT 未接(topeet eMMC-primary) | roadmap(可选) |
| **GPU Mali-G610** | ✅ vendor **私有 Arm mali_kbase Bifrost/CSF DDK**(`drivers/gpu/arm/bifrost/`,`MALI_BIFROST`+`MALI_CSF_SUPPORT`;DT `arm,mali-bifrost`) | ✅ **主线 Panthor**(`CONFIG_DRM_PANTHOR`),`mali_csffw.bin` 内建;log `Mali-G610 id 0xa867`、renderD128 出、GNOME 桌面([notes/48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)) | 已闭合;固件内建是 trade-off;**非同一驱动**,vendor CSF DDK 的特性/调优未必对齐 |
| **显示(DRM 1024×600 DSI→LVDS)** | ✅ VOP2 + `DW_MIPI_DSI`(旧 `_DSI` 符号)+ `simple-panel-dsi` 重放 init-seq;**但 vendor 默认屏实为 MIPI1 / FT5x06 800×1280,1024×600/GT911 分支编译关闭**(`topeet-screen-lcds.dts` 仅 `#define LCD_TYPE_MIPI1`) | ✅ VOP2 vp2→dsi0(`mipi-dsi2`)→ OOT `panel-topeet-dsi` 重放 vendor init-seq(patch 0001/0002);boot logo + GNOME 桌面亮([notes/44](notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)–[47](notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md)) | 已闭合;**VOP2 dclk handoff(patch 0009)= 候选,稳定性未闭环**([notes/54](notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)) |
| **触摸 GT911(i2c2)** | ⚠️ vendor `goodix,gt9xx` 节点在 1024×600 分支里,**但 `TOUCHSCREEN_GT9XX` / `TOUCHSCREEN_GOODIX` 均未编进 defconfig**,且该屏分支编译关闭;vendor 实际点亮的是 FT5x06 | ⚠️ 主线 `goodix,gt911`(`CONFIG_TOUCHSCREEN_GOODIX`);IRQ 路径修(pinctrl `pcfg_pull_up` + `IRQ_TYPE_EDGE_FALLING`)、轴原生范围 600×1024 不交换(patch 0010);**坐标事件已取证,GNOME 触摸 UX + 稳定性待续**([notes/52](notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)、[55](notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)) | 部分闭合;与 hardlock 调查交叉 |
| **watchdog + ramoops** | ✅ `DW_WATCHDOG`(defconfig;topeet DTS 未重声明,用 SoC 默认) | ✅ `ramoops@110000` + DW watchdog + soft/buddy hardlock detector + systemd `RuntimeWatchdogSec=30`(patch DT + kernel.config) | 已闭合(取证用,非产品稳态,[notes/53](notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)) |
| **WiFi / BT(RTL8723DU,USB)** | ✅ Realtek standalone 驱动 `CONFIG_RTL8723DU=m`(`RK_WIFIBT_CHIP="RTL8723DU"`);**DT 无 WiFi/BT 节点——USB combo 免 DT**,WiFi/BT 共用一组 USB2.0(迅为手册) | ✅ **主线 `rtw88_8723DU` 已板验通(2026-08-15):关联 + DHCP routable**([notes/58](notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md));`FW_LOADER_COMPRESS_ZSTD` 必须(Ubuntu 固件全 .zst);rtl8xxxu 从不认 8723DU(曾误开);BT 半边配置/固件已全,待板验 | WiFi 已闭合;BT 板验待做 |
| **NPU** | ✅ vendor rknpu2(`drivers/rknpu/`,`ROCKCHIP_RKNPU`) | ❌ 主线 Rocket 驱动(RK3588-only)在,CONFIG 未开(kernel.config Phase 6 TODO) | roadmap |
| **VPU / MPP(Hantro + rkvdec2/rkvenc2)** | ✅ vendor MPP(`RKVDEC2`/`RKVENC2`/`VDPU`/`VEPU`,`drivers/video/rockchip/mpp/`) | ⚠️ 主线 Hantro + rkvdec2 驱动在,DT 未接;无 vendor MPP 用户态 | roadmap |
| **RGA(2D)** | ✅ vendor RGA3(`ROCKCHIP_MULTI_RGA`)+ RGA2 | ❌ 主线无 RGA 驱动 | roadmap / 上游缺 |
| **摄像头(RKCIF / rkisp1)** | ✅ vendor `rkcif`/`rkisp`/`ISP`/`ISPP` + ov5695/ov13850(i2c4) | ⚠️ 主线 rkisp1 在,DT 未接;topeet 摄像头 pipeline 未做 | roadmap(Phase 3) |
| **音频(ES8388)** | ✅ `es8388@11`(i2c7)+ `es8388-sound` multicodecs-card | ❌ DT 未接 | roadmap(Phase 2) |
| **RTC(hym8563)** | ✅ `hym8563@51`(i2c6) | ❌ DT 未接 | roadmap(Phase 2) |
| **CAN / SATA / HDMI-RX / pwm-fan / buzzer / adc-keys** | ✅ vendor 接(`can1`、`sata0`、`hdmirx_ctrler`、`pwm12` fan、`pwm15` buzzer) | ❌ DT 未接 | roadmap / 产品特性 |

## 能否 boot?——分能力回答

- **主线启动到 UART / userspace handoff**:✅ **能**。BootROM → 主线 SPL → BL31 v1.54 → 主线 U-Boot →
  主线 kernel 7.1,systemd 259.5(Ubuntu 26.04)起,hostname `rk3588-topeet`,graphical.target 排队
  (log [202608012117.txt](logs/rk3588/202608012117.txt))。
- **主线挂 rootfs + 进 GNOME 桌面**:✅ **能**。eMMC `mmcblk0p3` ext4 rootfs,GDM 起、gnome-shell 跑、
  Panthor renderD128 出、桌面显示在 1024×600 屏。这条把 GPU 固件内建([notes/48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md))、
  LCD 视频管线([notes/47](notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md))、
  Ubuntu 用户/ownership([notes/56](notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md))都啃过。
- **主线产品级(外设全可用)**:🟡 **部分**。核心 + GMAC0 + eMMC + USB2 host×2 + GPU + LCD + GT911 坐标链路
  通;但 WiFi/BT、NPU、VPU、摄像头、PCIe/NVMe、USB3/Type-C、SD、gmac1、音频、RTC 全未接 DT;**且 VOP2
  hardlock 候选(patch 0009)连续冷/热启动稳定性未闭环**——不能写成"产品稳态"。详见 [notes/51](notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)
  2026-08-02 纠偏(已观测到的随机挂死尚未完成因果归属)。

## 主线 vs vendor 的"真差距"在哪

1. **启动前段(DDR / secure)**:跟 RK3506B 一样,主线没法自己 init RK3588 DDR → 借闭源 rkbin DDR blob +
   BL31/ATF。比 RK3506B 进步的是 **SPL 已切主线**(vendor `rk3588_spl` 与 BL31 v1.54 基址错配会 bootloop,
   见 [notes/49](notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md));但 DDR + BL31 这两层闭源 blob 改不了。
2. **GPU 驱动路线**:vendor 用 Arm 私有 mali_kbase CSF DDK(`drivers/gpu/arm/bifrost/`),主线用 Panthor。
   **不是同一个驱动**——主线 Panthor 已能驱动 Mali-G610 出桌面(renderD128 + GNOME),但 vendor CSF DDK 的
   某些 command-stream 特性 / 性能调优主线未必对齐;固件(`mali_csffw.bin`)必须 early-probe 前到位 → 内建
   进 kernel([notes/48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md))。
3. **显示 pipeline**:vendor 默认屏其实是 MIPI1 / FT5x06 800×1280(`topeet-screen-lcds.dts` 只开 `LCD_TYPE_MIPI1`);
   我们移植的 1024×600 / GT911 分支在 vendor 那边是**编译关闭**的。主线用 OOT panel 驱动重放 vendor init-seq,
   再靠 VOP2 dclk handoff patch(0009)才出图;**0009 是候选,hardlock 未闭环**。
4. **加速器全线 roadmap**:vendor 的 NPU(rknpu2)、VPU(MPP RKVDEC2/RKVENC2)、RGA3、rkisp 全是私有驱动,主线
   要么没驱动(RGA),要么驱动在但没接 DT(NPU Rocket、VPU Hantro/rkvdec2、rkisp1)。这是 RK3588 主线最大的
   "功能面"差距。
5. ~~vendor mkimage / afptool / rkImageMaker 税~~:已纯 Python 化([scripts/fit-pack.py](../scripts/fit-pack.py) /
   [scripts/rkfw-pack.py](../scripts/rkfw-pack.py),同 RK3506B)。

## 下一步优先级

1. **VOP2 hardlock 闭环**(最高):patch 0009 候选需连续冷/热启动 + 桌面运行验证;通过标准 = 启动阶段不再
   VP2 vblank timeout、连续多轮无 hard lock([notes/54](notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md))。
   当前不得写成稳定。
2. **GT911 触摸 GNOME UX 验收**:坐标事件已取证([notes/55](notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)),
   需 GNOME 虚拟键盘 / 拖动 / 多点触控板验,且与 hardlock 调查解耦。
3. ~~**WiFi / BT(RTL8723DU,USB combo)**~~:**WiFi 已闭合**(2026-08-15,rtw88_8723du 关联 + DHCP
   routable,[notes/58](notes/58-2026-08-15-rk3588-wifi-rtl8723du-rtw88-bringup.md));BT 半边
   (btusb/btrtl 配置与固件已全)板验待做;`network-manager` 已补进 packages.list 待下次 rootfs 重建。
4. **NPU(Rocket)/ VPU(Hantro + rkvdec2)/ PCIe**:主线驱动在,逐项接 DT + 板验。
5. **音频(ES8388)/ RTC(hym8563)/ 摄像头**:Phase 2/3,DT 接线。
6. ~~boot 到 GNOME 桌面~~:**已闭合**([notes/48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md) /
   [50](notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md) / [56](notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md))。
7. ~~0007 / 0008(I²C v5 + GT911 polling)~~:**失败实验已排除**([notes/52](notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md) /
   [54](notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)),patch 文件仅留作失败证据,不在 `series` 里。

## 证据

- 首启 boot 日志:[logs/rk3588/202608011826.txt](logs/rk3588/202608011826.txt)(Linux 7.1.0、8 核 big.LITTLE、
  GICv3、GMAC RGMII、eMMC HS400、Panthor Mali-G610 probe、rockchip-drm bind)
- RK860X 修复后:[logs/rk3588/202608012117.txt](logs/rk3588/202608012117.txt)(ttyFIQ0 + systemd 259.5、
  graphical.target 排队、hostname `rk3588-topeet`)
- bootloop 分析:[logs/rk3588/bootloop-analysis.md](logs/rk3588/bootloop-analysis.md)(vendor `rk3588_spl` →
  BL31 v1.54 基址错配,改 mainline SPL 修复)
- 主线 patch:`patches/rk3588-topeet/linux/{0001,0002,0003,0004,0005,0006,0009,0010}.patch` +
  `patches/rk3588-topeet/uboot/{0001,0002,0003}.patch`(逐字节干净上游 replay,见各 note 的静态闸门)
- 板配置:[config/boards/rk3588-topeet.env](../config/boards/rk3588-topeet.env)、
  [board/rk3588-topeet/kernel.config](../board/rk3588-topeet/kernel.config)
- 里程碑 notes:[43](notes/43-2026-07-31-rk3588-autoboot-baud-bootcmd.md) autoboot、
  [44](notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)–[47](notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md) LCD、
  [48](notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md) GPU/GNOME、
  [49](notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)–[50](notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md) bootloop/首启、
  [51](notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md) RK860X/ttyFIQ0、
  [52](notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)–[53](notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md) GT911/hardlock、
  [54](notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md) VOP2 候选、
  [55](notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md) GT911 轴、
  [56](notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md) Ubuntu 用户/ownership
