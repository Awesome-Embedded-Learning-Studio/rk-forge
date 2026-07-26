# RK3568 主线移植交接 (2026-07-26) — 当前状态 + rtl8852bs 下一步

这篇是**交接笔记**:RK3568 主线移植的当前完成状态 + 待办 + **rtl8852bs WiFi 移植方案(A1)**,供新对话直接接上。

## 一、当前状态(真机验证,2026-07-26)

板 ATK-DLRK3568 (RK3568B2),主线 **Linux 7.1.0** + **u-boot 2026.07-rc4** + buildroot **2026.08-git** Qt6 rootfs。boot 到 login,**主线驱动**(非 vendor BSP)。

| 子系统 | 状态 | 证据 |
|---|---|---|
| **boot 链** | ✅ 全通 | BootROM→SPL(vendor)→ATF→U-Boot→bootm→kernel→rootfs→login |
| **LCD** | ✅ 点亮 | `card0-DSI-1 connected`, fb0 写入, ILI9881C driver + ATK DT |
| **GPU** | ✅ Panfrost | `panfrost mali-g52 id 0x7402`, DRM card1 |
| **网络 eth** | ✅ | eth0/eth1 (gmac0/1 RGMII + ATK delay), 2× RTL8211F |
| **触摸** | ✅ | Goodix GT928 (ID 928), /dev/input/event0 |
| **CAN1** | ✅ | rockchip_canfd can0 |
| **RTC** | ✅ | pcf8563 |
| **HDMI** | ✅ bound | card0-HDMI-A-1 (disconnected 但 driver OK) |
| **音频** | ⚠️ RK809 gpio 冲突 | `gpio1-4 already requested by fe410000.i2s; cannot claim for rk809-sound` — hp-det(gpio1 PA4)抢 i2s1 mclk,card 没 probe。只有 BT SCO (card0) |
| **WiFi** | ❌ 待移植 | SDIO 总线通(mmc2:0001:1 = rtl8852bs, vendor:0x024c device:0xb852),无主线驱动(rtw89 无 SDIO) |

## 二、关键 host 改动(本次移植做的)

1. **主线 ATK DT** `arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dts`(脱离复用 evb1-v10):
   - `DT_NAME` (config/boards/rk3568-atk.env) + `rk3568-kernel.its` 都改成 ATK dtb(之前一直烧 evb1-v10,这是大坑)
   - dsi1 ILI9881C panel(power-supply, reset GPIO4_PB5) + gmac0/1 RTL8211F rgmii delay + RK809 sound + GT911/928 touch + CAN1 + RTC + fan + leds
2. **LCD panel descriptor** `drivers/gpu/drm/panel/panel-ilitek-ili9881c.c` 加 `atk_10p1_desc`(194 条 init 从 vendor panel-init-sequence 机械翻译 + **.lanes=4**[漏了会卡死] + vendor 67MHz timing + VIDEO_BURST)
3. **kernel.config** `board/rk3568-atk/kernel.config`:DRM/SOUND/STMMAC/GOODIX/ILI9881C/PHY_ROCKCHIP_INNO_DSIDPHY/RESET_GPIO/CFG80211/MAC80211 全 =y(框架总开关一个不能漏,漏了整栈 =m,busybox 无 modules 不 probe)
4. **u-boot** `evb-rk3568_defconfig`:`BOOTCOMMAND` 改 mmc dev 0 + read 0x08000000 + bootm(绕 bootflow dev0 不扫 partition) + `BAUDRATE=115200`
5. **boot.scr** `board/rk3568-atk/fit/boot-emmc.cmd`:FIT 读 0x08000000(避开 kernel load 0x02000000 重叠) + console ttyS2,115200。pack-emmc.sh 生成 boot.scr 放 rootfs /boot/
6. **eMMC resize** parameter rootfs 0x100000→0x200000(1G) + pack-emmc ROOTFS_MIB 1024
7. **DDR bin baud** `ddrbin_tool.py` 改 rk3568_ddr_1560MHz_v1.25.bin uart baud 115200(BootROM/SPL/BL31 统一,备份 .bak 在)

## 三、rtl8852bs WiFi 移植方案(A1,新对话接这)

板上 SDIO 设备 = **rtl8852bs**(`vendor=0x024c device=0xb852`),走 SDIO(mmc2,不是 USB)。主线 rtw89 无 SDIO。

**A1 路径(推荐)**:搬 vendor 整个驱动(851 文件)进 kernel,适配 5.10→7.1。
- vendor 驱动:`reference/rk3568/external/rkwifibt/drivers/rtl8852bs/`(851 .c/.h,`CONFIG_SDIO_HCI=y`,Realtek 私有 phl/core 框架,非主线 rtw89)
- 借鉴:aes 的 rtl8733bu(`third_party/src/aes/linux/drivers/net/wireless/realtek/rtl8733bu`,7.1 适配过的 Realtek 框架,patch 0016 + `scripts/fetch-rtl8733bu-driver.sh`)— 同框架,7.1 适配经验可参考
- firmware:rtl8852bs_fw + config(`reference/rk3568_android/hardware/realtek/rtkbt/vendor/firmware_box/rtl8852bs_*`)
- SDIO DT:已有(sdio-pwrseq + sdmmc2,RESET_GPIO=y 已让 SDIO 总线起,rtl8852bs 枚举 mmc2:0001:1)

**移植步骤(估)**:
1. 复制 vendor rtl8852bs(851 文件)→ `drivers/net/wireless/realtek/rtl8852bs/`
2. Kconfig/Makefile 注册(参考 aes patch 0016)
3. 适配 5.10→7.1 API(mac80211/cfg80211/netdev 漂移,参考 aes rtl8733bu 的适配 patch)
4. CONFIG_RTL8852BS=y + CFG80211/MAC80211 已 =y
5. firmware 进 rootfs(`/lib/firmware/`)
6. SDIO bind → wlan0 → wpa_supplicant + udhcpc

**估工作量**:数日(851 文件 + API 适配)。建议开 workflow 深入分析 5.10→7.1 适配点 + SDIO bus + firmware,产可执行路线。

## 四、待办(收尾 + 下一步)

- **音频 RK809 gpio 冲突**:DT 的 hp-det(gpio1 PA4)抢 i2s1_8ch mclk → rk809-sound card 不 probe。修:hp-det 换 gpio,或 i2s1 mclk pinctrl 不用 gpio1-4
- **rtl8852bs 移植**(A1,单独一轮)
- **LCD 精调**:屏亮但 init sequence 的 delay 没移植(vendor 每条 5ms)+ 尾命令(sleep out/display on)和 driver 通用 prepare 重复(大 AI 建议的 #2,屏黑/花屏时调)
- **Qt6 rootfs**:Qt6 进了(455M)但没真机验 Qt app(无 LCD GUI 测试)

## 五、关键文件索引(新对话参考)

- ATK DT:`third_party/src/rk3568-atk/linux/arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dts`
- ili9881c descriptor:`third_party/src/rk3568-atk/linux/drivers/gpu/drm/panel/panel-ilitek-ili9881c.c`(atk_10p1_desc)
- kernel fragment:`board/rk3568-atk/kernel.config`
- u-boot defconfig:`third_party/src/rk3568-atk/uboot/configs/evb-rk3568_defconfig`
- boot.scr:`board/rk3568-atk/fit/boot-emmc.cmd`
- vendor rtl8852bs 驱动:`reference/rk3568/external/rkwifibt/drivers/rtl8852bs/`
- aes rtl8733bu(7.1 参考):`third_party/src/aes/linux/drivers/net/wireless/realtek/rtl8733bu/` + `patches/aes/linux/0016-wifi-rtl8733bu-wire-realtek.patch`
- notes:36(多板主线)/37(android)/38(rootfs 等价)/39(qt6webengine)/40(首次 boot)/41(ATK DT 移植方案)/42(本文)

参见 MEMORY:rk3568-migration-status / rk3568-build-gotchas / rk3568-forge-vs-vendor-rootfs。
