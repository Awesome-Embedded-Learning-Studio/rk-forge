# 50 RK3588 首次 boot 到 systemd：baud + root + DT (2026-07-27)【前传】

接 [49](49-2026-07-27-rk3588-bootloop-mainline-spl.md)：bootloop 修了（mainline SPL），再把三个板级细节对齐，让板子真 boot 到 Ubuntu systemd。本篇是前传的收尾（update.img MD5 `1d972c21`，后续 autoboot/LCD 见 43-48）。

## 三件事 + 真机结果

主线 u-boot + kernel 起来后，三个 topeet 板级点要敲定，否则卡在 baud 乱码 / 等根设备 / DT 不匹配：

1. **串口 baud 全链路 115200**（vendor 默认 1500000）：
   - DDR blob：rkbin `ddrbin_tool` 改 `tools/ddrbin_param.txt`（`uart baudrate=115200`）+ `python3 tools/ddrbin_tool.py rk3588 ... bin/rk35/rk3588_ddr_*.bin`（只支持 115200/1500000）。当前直接改 rkbin working tree（重 fetch 会丢，待集成进 setup）。
   - u-boot：`CONFIG_BAUDRATE=115200`（见 [43]——这玩意儿后来被 reset 冲掉过，已落 patch）。
   - kernel：DT `stdout-path = "serial2:115200n8"` + bootargs `console=ttyS2,115200`。
2. **root=mmcblk0p3**（eMMC = mmcblk0，**不是 mmcblk1**）：
   - RK3588 topeet eMMC 是 `mmcblk0`（RK3568-atk 是 mmcblk1）。照 RK3568 写 `mmcblk1p3` 会 kernel `Waiting for root device` 永远等不到。
   - U-Boot 里 eMMC = `mmc 0`（`ls mmc 0:3 /boot` 有 boot.scr）；kernel `mmcblk0: p1 p2 p3`。
   - boot.cmd `root=/dev/mmcblk0p3 rw rootwait`。
3. **topeet DT**：从 vendor 5.10 `topeet-rk3588-linux.dts` 移植到主线 v7.1——PMIC rk806（单 SPI2）+ rk8602/rk8603 CPU 供电照 `rk3588-fet3588-c.dtsi` 模板；`DT_NAME=rk3588-topeet`。（LCD 显示管线是后话，见 44-48。）

## 真机结果（2026-07-27，update.img `1d972c21`）

boot 到 systemd：hostname `rk3588-topeet`，graphical.target。串口 115200 全程可读。全 probe：8 CPU(A55×4+A76×4)/16GB/eMMC HS400/PMIC rk806/rk8602(fan53555)/GMAC0 RGMII/GPU Panthor Mali-G610/USB host。

## 后续（43-48）

- autoboot 自动化 + u-boot baud/bootcmd → [43](43-2026-07-31-rk3588-autoboot-baud-bootcmd.md)
- LCD（DSI0→TC358775→LVDS）移植 + 触摸 → [44](44-2026-07-31-rk3588-lcd-dsi-panel-port.md) / [45](45-2026-07-31-rk3588-lcd-bringup-blockers.md) / [46](46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md) / [47](47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md)
- GPU 固件 + GNOME 桌面 → [48](48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)

## 关键文件

- `config/boards/rk3588-topeet.env`（rootfs 3072Mib / ROOTFS_MIB、RKBOOT ini、rkbin blob tuple）
- `board/rk3588-topeet/fit/boot-emmc.cmd`（mmc dev 0 → root=mmcblk0p3 → mmc read 0x08000000 0x6000 0x20000 → bootm）
- `arch/arm64/boot/dts/rockchip/rk3588-topeet.dts`（Phase 1 boot 部分；LCD 部分在 44 加）
