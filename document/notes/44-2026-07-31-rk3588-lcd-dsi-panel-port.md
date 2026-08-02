# 44 RK3588 LCD 移植：DSI panel 驱动 + DT 管线 (2026-07-31)

10.1" 1024×600 DSI→LVDS bridge panel + GT911 触摸移植到主线 v7.1。vendor 用私有的 `simple-panel-dsi` + `panel-init-sequence` 绑定（kernel 5.10 BSP）；主线无此驱动也无此 bridge IC 的驱动，所以走 **OOT 自写 `drm_panel` 驱动重放 vendor init-seq**。

## 物理

- 屏：10.1" 1024×600，走 **DSI0 → bridge IC → LVDS**（`LCD_TYPE_LVDS_10_1_1024x600_GT911`，vendor fragment 注释 //VP2）。
- 触摸：GT911 on i2c2 @ 0x14。
- vendor 默认激活的是 MIPI1（800×1280 HX8394）——别被误导，照交接的 1024×600 那套。

## OOT 驱动 `panel-topeet-dsi.c`（照 panel-himax-hx8394.c）

- `module_mipi_dsi_driver` + `devm_drm_panel_alloc` + `drm_panel_funcs`。
- compatible `"topeet,dsi-panel-seq"`（一个通用绑定，重放任意 vendor init-seq）。
- probe 读 DT 字节 blob：`of_property_read_variable_u8_array(np, "panel-init-sequence", buf, 0, 4096)` + `panel-exit-sequence`；delay 用 `device_property_read_u32("…-delay-ms")`。
- 重放核心 `topeet_panel_send_seq`：迭代 `<u8 type><u8 delay_ms><u8 len><payload>`，用 `struct mipi_dsi_multi_context` + 按类型分派：
  - `0x29` MIPI_DSI_GENERIC_LONG_WRITE → `mipi_dsi_generic_write_multi(ctx, payload, plen)`
  - `0x05/0x15/0x39` DCS → `mipi_dsi_dcs_write_buffer_multi(ctx, payload, plen)`
  - 每 record 后 `mipi_dsi_msleep(&ctx, delay)`，末了返回 `ctx.accum_err`。
- panel funcs：`prepare`=regulator_enable(power)（reset gpio 可选，NULL 则只 delay）；`enable`=重放 init-seq；`disable`=重放 exit-seq；`unprepare`=regulator_disable；`get_modes`=`of_get_drm_display_mode` + `drm_mode_probed_add`。
- probe 固化：`dsi->mode_flags = VIDEO|VIDEO_BURST|LPM|NO_EOT_PACKET`、`format=RGB888`、`lanes=4`（跟 vendor `dsi,flags/dsi,format/dsi,lanes` 一致）。

## DT 管线（`rk3588-topeet.dts`，照 `rk3588s-gameforce-ace.dts` 的 OF-graph）

```
root: backlight (pwm-backlight, pwms=<&pwm1 0 25000 0>) + vcc3v3_lcd_n (regulator-fixed, gpio1 PB3, vin vcc_3v3_s3)
&pwm1/{status=okay}; &vop{status=okay}; &vop_mmu{status=okay}; &mipidcphy0{status=okay};
&dsi0 { panel@0 { compatible="topeet,dsi-panel-seq"; power-supply=<&vcc3v3_lcd_n>; backlight=<&backlight>;
    panel-init-sequence = [ 29 02 06 3C 01 09 ... 9C 04 31 04 00 00 ];  /* vendor verbatim */
    panel-exit-sequence = [ 05 05 01 28  05 78 01 10 ];
    display-timings { dsi0_timing0: timing0 { clock-frequency=82000000; hactive=1024; vactive=600;
        hfront-porch=1580; hsync-len=10; hback-porch=100; vfront-porch=10; vsync-len=10; vback-porch=25; ... }; };
    port { mipi_panel_in: endpoint { remote-endpoint=<&dsi0_out_panel>; }; }; }; };
&dsi0_in { dsi0_in_vp2: endpoint { remote-endpoint=<&vp2_out_dsi0>; }; };
&dsi0_out { dsi0_out_panel: endpoint { remote-endpoint=<&mipi_panel_in>; }; };
&vp2 { vp2_out_dsi0: endpoint@ROCKCHIP_VOP2_EP_MIPI0 { reg=<ROCKCHIP_VOP2_EP_MIPI0>; remote-endpoint=<&dsi0_in_vp2>; }; };
&i2c2 { touchscreen@14 { compatible="goodix,gt911"; irq-gpios=<&gpio3 RK_PC0 GPIO_ACTIVE_HIGH>; reset-gpios=<&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>; touchscreen-size-x=<1024>; touchscreen-size-y=<600>; status="disabled"; }; };
```

## kernel.config（`board/rk3588-topeet/kernel.config`）

```
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y      # dsi0 = mipi-dsi2 控制器（NOT _DSI）
CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y # mipidcphy0 驱动（见 [45]）
CONFIG_DRM_MIPI_DSI=y
CONFIG_DRM_PANEL_TOPEET_DSI=y
CONFIG_BACKLIGHT_PWM=y              # 见 [45]（=m 踩坑）
CONFIG_TOUCHSCREEN_GOODIX=y
```

## 致命 gotcha（错一个 panel 静默不亮）

1. **DSI host = `ROCKCHIP_DW_MIPI_DSI2` 不是 `_DSI`**：rk3588 dsi0 compatible=`rockchip,rk3588-mipi-dsi2`，由 `dw-mipi-dsi2-rockchip.c` 绑定。`_DSI` 编旧驱动不绑 dsi0。
2. **init-seq `0x29` = GENERIC_LONG_WRITE（不是 DCS！）**，`0x39` 才是 DCS。1024×600 整段 `29 ...` = 给 bridge 厂商寄存器 generic 写。
3. **PHY 标签主线 `mipidcphy0`**（vendor 写 `mipi_dcphy0`，BSP-only）。
4. **panel 无 reset GPIO**：reset 靠 `vcc3v3_lcd_n`（gpio1 PB3）断电。gpio3 PC1 是**触摸** reset。
5. `MIPI_DSI_MODE_EOT_PACKET` 主线改名 `MIPI_DSI_MODE_NO_EOT_PACKET`（语义同，取反命名）。
6. **init-seq 不 append DCS wake**：1024×600 块在 vendor 同文件里唯独不以 `05 .. 11/29` 收尾（MIPI0/MIPI1 有），vendor `panel-simple.c` 也不自动补 → bridge 自启动。
7. **OF-graph**：主线用 `&dsi0_in/&dsi0_out/&vp2{endpoint}`。vendor 的 `&route_dsi0`/`&dsi0_in_vp2{status}` 是 BSP-only，主线没有。
8. **GT911 绑定**：`goodix,gt911`（vendor `goodix,gt9xx` 不是主线）；`irq-gpios`/`reset-gpios`（vendor `touch-gpio`/`reset-gpio`）。早期照搬的 `touchscreen-size-x/y = 1024/600` 已由 [55](55-2026-08-02-rk3588-gt911-landscape-axis-fix.md) 纠正：芯片的物理轴方向正确，只是原生分辨率为 600×1024；应删除尺寸覆盖，不交换或反转轴。
9. `hfront-porch=1580`：vendor 原值（多半笔误 158?），先照抄——bridge 的 init-seq 是为这个 mode 配的，改 mode 要跟 bridge 配置匹配。

## 关键文件

- `patches/rk3588-topeet/linux/0001-drm-panel-topeet-dsi-driver.patch`（驱动 + Kconfig + Makefile）
- `patches/rk3588-topeet/linux/0002-arm64-dts-rk3588-topeet-panel.patch`（板 DT + Makefile dtb-y）
- 设计 plan：`.claude/plans/joyful-rolling-hartmanis.md`
- vendor 源：`reference/rk3588/kernel/arch/arm64/boot/dts/rockchip/topeet-screen-lcds.dts`（init-seq + timing 逐字抄）

后续真机 bringup 的两个 config blocker（PHY + BACKLIGHT_PWM）见 [45](45-2026-07-31-rk3588-lcd-bringup-blockers.md)；当前 DSI2 视频模式 blocker 见 [46](46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md)。
