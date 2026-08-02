# 45 RK3588 LCD 真机 bringup：PHY + BACKLIGHT_PWM + panel 点亮 (2026-07-31)

[44](44-2026-07-31-rk3588-lcd-dsi-panel-port.md) 把代码/patch 都落好了，真机上一路踩两个 **kernel.config blocker**（都是"=m 没编进内核 / 符号没开"类），逐一破。本篇记 symptom→cause→fix + 最后 panel 点亮。

## update.img MD5 演进（每版一个 blocker）

| MD5 | 改动 | 真机结果 |
|---|---|---|
| `1d972c21` | 原始（autoboot 手动） | ✅ systemd，无 LCD |
| `9e3de8e1` | +autoboot+LCD | ❌ u-boot 乱码（baud 回归，见 [43]） |
| `6c41870e` | +baud 115200 | ❌ autoboot 落 prompt（bootflow 不找 boot.scr，见 [43]） |
| `8520c77f` | +直接 bootcmd | ✅ autoboot✓；❌ panel deferred（PHY 没编） |
| `69d5d278` | +PHY_ROCKCHIP_SAMSUNG_DCPHY | ❌ panel 仍 deferred（BACKLIGHT_PWM=m） |
| `b8d0abf3` | +BACKLIGHT_PWM=y | ✅ DRM 起 + panel 亮；⏳ 视频模式 blocker（见 [46]） |

## Blocker 1：mipi DCPHY 驱动没编（8520c77f）

- **症状**：`dmesg | grep dsi` → `platform fde20000.dsi: deferred probe pending: dw-mipi-dsi2: failed to get mipi phy`。
- **根因**：mipidcphy0（compatible `rockchip,rk3588-mipi-dcphy`）的驱动是 `phy-rockchip-samsung-dcphy.c`（Kconfig `PHY_ROCKCHIP_SAMSUNG_DCPHY`），**默认没开**。Plan agent 当初说"DSI2 host 会自动 select PHY 符号"是**错的**——它 select 的是 `GENERIC_PHY_MIPI_DPHY` 框架，不是 mipidcphy0 这个具体驱动。mipidcphy0 没 probe → dsi2 拿不到 PHY → panel 永久 deferred → `/dev/dri` 都没。
- **诊断**：`grep PHY_ROCKCHIP_SAMSUNG_DCPHY .config` → `# ... is not set`。
- **修**：kernel.config 加 `CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y`。

## Blocker 2：BACKLIGHT_PWM=m（69d5d278）

- **症状**：PHY 修好后 dmesg 变 `mipi-dsi fde20000.dsi.0: deferred probe pending: (reason unknown)`；`/sys/class/backlight/` 空、`/sys/class/drm/` 空、dmesg 无任何 pwm/backlight 行。
- **根因**：`CONFIG_BACKLIGHT_PWM=m`（pwm-backlight 驱动是模块）。rootfs 没 modprobe → backlight 设备永不出现 → panel 卡 `drm_panel_of_backlight()` **永久 deferred**（我的驱动 `drm_panel_of_backlight()` 返回 -EPROBE_DEFER）。kernel.config 只声明 `BACKLIGHT_CLASS_DEVICE=y`（框架）不够，要单独 `BACKLIGHT_PWM=y`（具体驱动）。踩的是"=m busybox-no-modprobe"坑——显示链路符号都得显式 =y。
- **诊断**：`grep BACKLIGHT_PWM .config` → `=m`；+ dmesg 无 backlight 行 + `/sys/class/backlight/` 空 = backlight 没 probe。
- **修**：kernel.config 加 `CONFIG_BACKLIGHT_PWM=y`（顺带扫一遍 display 相关 =m，只有这一个）。

## 真机结果（b8d0abf3）

```
rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[drm] Initialized rockchip 1.0.0 for display-subsystem on minor 0
rockchip-drm: fb0: rockchipdrmfb frame buffer device
```
- ✅ DRM 起、VOP2+DSI2 bind、fb0 建。
- ✅ **panel 背光亮**（init-seq 命令模式送达，bridge 配好了）。
- ✅ connector `card0-DSI-1: connected, enabled, dpms=On, mode=1024x600`。
- ✅ GDM/graphical.target 跑起来。

## 但：fbcon modeset 偶发挂死 + 视频没出图

- **偶发挂死**：有时 `[drm] Initialized` 后一大坨乱码 + 系统冻结（看着像 panic，其实没 oops）。`nomodeset`（关 KMS）能干净进系统 → 实锤是 DRM/fbcon 接管时触发。**干净重启有时又不挂**（cold/warm boot 时序，非必现）。`fbcon=disable` boot param 能稳定进系统。
- **乱码真相**：不是 oops，是 DRM 接管 fbcon 那一瞬 scanout 异常吐的（DMA/打印缓冲被污染）。
- **视频没出图**：`head -c 2457600 /dev/urandom > /dev/fb0` 灌噪点 → **屏仍只有背光，无雪花**。说明 DSI 视频流没真正到桥。这是下一关，见 [46](46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md)。

## 教训

- "符号会自动 select"的话别信——逐个 `grep .config` 确认 mipidcphy0（PHY_ROCKCHIP_SAMSUNG_DCPHY）、pwm-backlight（BACKLIGHT_PWM）这种具体驱动符号都 =y。
- 真机 bringup 的 deferred probe，先看 `dmesg | grep deferred` + 对应 `/sys/class/...` 是否空，再查具体驱动是否编进内核。
