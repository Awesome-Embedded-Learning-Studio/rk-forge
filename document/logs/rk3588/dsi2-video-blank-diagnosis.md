# RK3588 mainline DSI2：panel 背光亮但无画面（视频模式不通）— 诊断交接

> 自包含，直接给 AI 诊断。RK3588 + 主线内核，DSI→LVDS 桥 panel：命令模式通（屏亮），视频模式不通（无画面）。

## 一句话问题

RK3588 主线 DSI2 控制器：DRM 管线全 bind、VOP2 在扫描、DSI2 成功进视频模式、panel 背光亮（init-seq 命令模式送达）——**但屏无任何画面**（往 /dev/fb0 灌随机像素，屏不出现雪花）。vendor BSP 用**同样的 mode + DSI 配置**能正常点亮+使用屏。

## 硬件 / 软件

- 板：iTOP-RK3588（topeet），RK3588（8 CPU big.LITTLE，LPDDR4X 16GB，eMMC）。
- 屏：10.1" 1024×600，走 **DSI0 → bridge IC → LVDS**（桥 IC 未知，init-seq 是 generic 厂商寄存器写入；无主线驱动）。
- 内核：主线 **Linux 7.1.0**（DSI2 rockchip 驱动 6.18-rc1 才进主线，很新）。
- DSI host：`dw-mipi-dsi2-rockchip.c` + core `bridge/synopsys/dw-mipi-dsi2.c`；PHY：`phy-rockchip-samsung-dcphy.c`（mipidcphy0，PHY_TYPE_DPHY）。
- panel 驱动：自写 OOT `panel-topeet-dsi.c`（照 panel-himax-hx8394，`module_mipi_dsi_driver`，重放 DT 的 `panel-init-sequence`/`panel-exit-sequence` 字节 blob）。

## 症状 + 证据

dmesg（干净，无报错）：
```
rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[drm] Initialized rockchip 1.0.0 for display-subsystem on minor 0
rockchip-drm: fb0: rockchipdrmfb frame buffer device
```
- panel 背光亮（DSI 命令模式 init-seq 送达，桥配好了）。
- `card0-DSI-1: connected, enabled, dpms=On, modes=1024x600`。
- debugfs `/sys/kernel/debug/dri/0/state`：
```
crtc[83]: video_port2   active=1
mode: "1024x600": 47 82000 1024 2604 2614 2714 600 610 620 645 0x48 0xa
connector[85]: DSI-1   crtc=video_port2
```
（hsync_start=2604 → hfront-porch=1580；htotal=2714；47Hz）
- **关键测试**：`head -c 2457600 /dev/urandom > /dev/fb0` → 屏**仍空白**，无雪花。说明像素没到 panel。
- `nomodeset` boot → 系统干净启动（无显示）。开 KMS 时，DRM 接管 fbcon 那一瞬**偶发**串口乱码+挂死（cold/warm boot 相关，非必现；`fbcon=disable` 可避）。

## 已排除（mainline vs BSP 逐行对照，功能等价）

把 mainline 的 DSI2 core + rockchip glue + samsung-dcphy 跟 vendor BSP（5.10 `dw-mipi-dsi2-rockchip.c`，能点亮屏）逐行对照：
- ✅ 视频模式切换序列（`DSI2_DSI_VID_TX_CFG` + `DSI2_MODE_CTRL=VIDEO_MODE` + poll `MODE_STATUS`）——一致，且 mainline 进视频模式**没报错**。
- ✅ IPI 配置（`IPI_RSTN` + 全套 IPI timing：HSA/HBP/HACT/HLINE/VSA/VBP/VACT/VFP + `PIX_PKT_CFG`）——一致。
- ✅ lane rate 计算（`crtc_clock*bpp/lanes` + VIDEO_BURST 的 10/9 overhead）——一致。
- ✅ samsung-dcphy power_on 序列（bias/pll/clk_lane/data_lane enable）——一致。
- ✅ GRF 写（两边都只写 IPI_COLOR_DEPTH/FORMAT）。
- ✅ IPI timing 不溢出（hline_time≈66.7M，30-bit 字段装得下）。
- → **mainline 没漏写 DSI2 控制器寄存器**。

## 剩余嫌疑

1. **VOP2 → DSI2 IPI 像素喂入**：BSP encoder 设 `s->output_if |= VOP_OUTPUT_IF_MIPI0`；**mainline VOP2 重构后完全不用 output_if**。怀疑主线 VOP2 没把 vp2 的扫描输出实际 mux 到 DSI2 的 IPI 输入（DRM 层看 vp2 active+connector 绑了，但硬件 mux 可能没设）。
2. **DSI→LVDS 桥没锁住视频同步**：桥收不到有效 DSI sync/line packet → 驱动空白 LVDS。`BLK_*_HS_EN` / burst-vs-sync-pulse 可能相关（但 vendor 同配置能锁）。
3. 主线 VOP2/DSI2 回归（驱动很新，6.18-rc1 才进）。

## panel DT 配置（关键段）

```dts
&dsi0 {
    panel@0 {
        compatible = "topeet,dsi-panel-seq";
        reg = <0>; power-supply = <&vcc3v3_lcd_n>; backlight = <&backlight>;
        panel-init-sequence = [ 29 02 06 3C 01 09 ... 9C 04 31 04 00 00 ];  /* 全 0x29 = GENERIC_LONG_WRITE，vendor 原值 */
        panel-exit-sequence = [ 05 05 01 28  05 78 01 10 ];
        display-timings { dsi0_timing0: timing0 {
            clock-frequency=<82000000>; hactive=<1024>; vactive=<600>;
            hfront-porch=<1580>; hsync-len=<10>; hback-porch=<100>;
            vfront-porch=<10>; vsync-len=<10>; vback-porch=<25>; ... }; };
        port { mipi_panel_in: endpoint { remote-endpoint=<&dsi0_out_panel>; }; };
    };
};
&dsi0_in  { dsi0_in_vp2:  endpoint { remote-endpoint = <&vp2_out_dsi0>; }; };
&dsi0_out { dsi0_out_panel: endpoint { remote-endpoint = <&mipi_panel_in>; }; };
&vp2 { vp2_out_dsi0: endpoint@ROCKCHIP_VOP2_EP_MIPI0 { reg=<ROCKCHIP_VOP2_EP_MIPI0>; remote-endpoint=<&dsi0_in_vp2>; }; };
&mipidcphy0 { status="okay"; }; &vop{status="okay";}; &vop_mmu{status="okay";};
```
panel 驱动固化：`dsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST | MIPI_DSI_MODE_LPM | MIPI_DSI_MODE_NO_EOT_PACKET`；`format=RGB888`；`lanes=4`（跟 vendor `dsi,flags/dsi,format/dsi,lanes` 完全一致）。

## 想问的

1. 主线 rk3588 DSI2：进视频模式没报错、VOP2 active 在扫描、命令模式通——但视频像素到不了 DSI→LVDS 桥（屏空白）。最可能的原因？是 VOP2→DSI2 IPI 路由没设、还是桥同步没锁、还是主线已知回归？
2. 主线 VOP2 重构后不用 `output_if`，那它**怎么**把指定 vp 的输出路由到 DSI2 的 IPI？rk3588 上 DSI0 该用哪个 vp（vp0/1/2/3）？我用的 vp2（vendor 注释 //VP2），gameforce-ace 用 vp3——有没有约束？
3. 下一步该 dump 哪些寄存器确认？（DSI2 base 0xfde20000：MODE_STATUS / VID_TX_CFG / IPI 系列 / INT_ST_IPI；VOP2 cluster→DSI mux？）
4. 有没有已知的主线 patch（6.18 之后）修过 rk3588 DSI2 视频模式？
