# 46 RK3588 LCD 当前 blocker：DSI2 视频模式不通 + 交接 (2026-07-31)

[45](45-2026-07-31-rk3588-lcd-bringup-blockers.md) 把 panel 点亮了（DRM/VOP2/DSI/PHY 全 bind、背光亮、connector enabled）。**最后一公里**：DSI 视频流没真正传到 panel——背光亮但无画面。本篇记定位过程 + 深挖计划 + 全局交接。

## 症状

- 板子能进系统（systemd/GDM 跑着，串口可登录）。
- LCD 只亮背光，**无任何画面**。
- `head -c 2457600 /dev/urandom > /dev/fb0` 灌噪点 → 屏仍空白（DSI 视频管道没把像素送到桥）。

## 定位（debugfs 定断点）

```
$ cat /sys/kernel/debug/dri/0/state
crtc[83]: video_port2
active=1
mode: "1024x600": 47 82000 1024 2604 2614 2714 600 610 620 645 0x48 0xa
connector[85]: DSI-1
	crtc=video_port2
```

- **vp2 active=1**：VOP2 在扫描 fb0，mode 1024×600@47Hz 正确应用（hsync_start=2604 → hfront-porch=1580，vendor 原值）。
- connector DSI-1 绑到 vp2 → **vp2→dsi0 路由没问题**（之前怀疑 vp2/vp3 是错的，gameforce 用 vp3 但 vp2 也通）。
- 像素从 VOP2 出去了 → **断点在 VOP2 之后：DSI2 视频编码 / PHY HS / bridge 这段**。

## 根因判断

- 命令模式通（panel init-seq 送达 → 背光亮）→ DSI host + PHY lanes 物理层 OK。
- 视频模式不通（fb0 噪点到不了屏）→ DSI2 切视频/HS 模式那步断了。
- **vendor 用一模一样的 mode + DSI 配置（lanes=4 RGB888 VIDEO|BURST|LPM|EOT）能点亮+使用屏** → 配置无误，是 **mainline `dw-mipi-dsi2` 驱动本身跟 vendor BSP 的实现差异**（视频模式 enable / IPI / HS clk 某步），不是 DT/config 能修的。
- mainline DSI2 rockchip glue（`dw-mipi-dsi2-rockchip.c`）逻辑完整（PHY power_on/set_mode DPHY/lane_mbps/IPI color depth 都在），视频模式核心在 `drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi2.c`。

## 深挖计划（下一步）

对照读，找视频模式 enable 的 diff：
1. mainline core：`third_party/src/rk3588-topeet/linux/drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi2.c`（视频模式 enable、IPI 配置、HS clk、lp2hs/hs2lp timing）。
2. vendor BSP：`reference/rk3588/kernel/drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c` + 其 dsi core（视频模式寄存器序列、`dw_mipi_dsi_set_video_mode` 类）。
3. 重点对照：视频模式寄存器写入序列、HS clock 使能、IPI vs DPI 模式、`PHY_MODE_MIPI_DPHY` 后的 phy_configure 参数。
4. 也要查 mipidcphy0 驱动 `phy-rockchip-samsung-dcphy.c` 是否真出 HS（BSP 的 innos dphy vs samsung dcphy 实现差异）。

## 全局状态（2026-07-31）

| 子系统 | 状态 |
|---|---|
| boot 链（BootROM→mainline SPL→BL31 v1.54→u-boot→kernel） | ✅ |
| autoboot（直接 bootcmd） | ✅ |
| 串口 115200 全链路 | ✅ |
| eMMC mmcblk0p3 rootfs / Ubuntu 26.04 GNOME | ✅ |
| 8 CPU / 16GB / eMMC HS400 / PMIC rk806 / GMAC / USB host | ✅ |
| LCD DRM 管线（VOP2+DSI2+PHY+panel probe） | ✅ bind + panel 亮 |
| **LCD 视频出图** | ❌ DSI2 视频模式不通（本篇） |
| GT911 触摸 | ❌ I2C -110（总线/mux 或 reset 时序，待查） |
| GPU Panthor | ⚠️ `mali_csffw.bin` 加载失败（early probe -ENOENT；要 CONFIG_EXTRA_FIRMWARE 内建或 initramfs） |
| 外设（audio es8388 / RTC hym8563 / USB-typec） | ⏸ 未开始 |

## 产物

- `board/rk3588-topeet/out/update.img`，最新 MD5 `b8d0abf3`（autoboot+baud+LCD+PHY+BACKLIGHT_PWM）。烧录落点 `C:\Users\CharlieChen\Assets\images\RK3588\`。
- 想稳态用板子（绕 fbcon 偶发挂）：bootargs 加 `fbcon=disable`（保 DRM，关内核 console）或 `nomodeset`（全关 KMS）。

## 关键文件指针

- u-boot patch：`patches/rk3588-topeet/uboot/{0001,0002,0003}-*.patch`（见 [43]）
- kernel patch：`patches/rk3588-topeet/linux/{0001,0002}-*.patch`（见 [44]）
- kernel.config：`board/rk3588-topeet/kernel.config`
- 设计 plan：`.claude/plans/joyful-rolling-hartmanis.md`
- bootloop 分析：`document/logs/rk3588/bootloop-analysis.md`
- 记忆：`[[rk3588-migration-status]]` + `[[rk3588-build-gotchas]]` #8
