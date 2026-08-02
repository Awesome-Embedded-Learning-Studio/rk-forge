# 43 RK3588 autoboot + baud + 直接 bootcmd (2026-07-31)

RK3588 topeet 原本能 boot 到 systemd（见 [bootloop-analysis](../../document/logs/rk3588/bootloop-analysis.md)），但 autoboot 要手动 `source`、且 u-boot 阶段 baud 一度回归。本篇记 u-boot 侧三个 patch + 一个自挖的 baud 回归坑。

## 背景

- 原 update.img（MD5 `1d972c21`）boot 到 systemd，但 autoboot 是手动的：bootflow scan 卡 USB/eth BOOTP，需手动 `load mmc 0:3 ${scriptaddr} /boot/boot.scr; source`。
- 全链路串口 115200（DDR blob 用 ddrbin_tool 改 + kernel console=ttyS2,115200 + u-boot CONFIG_BAUDRATE）。

## 三个 u-boot patch（`patches/rk3588-topeet/uboot/series`，apply-series `git am`）

### 0001 boot_targets 收窄到 mmc0
- 根因：`include/configs/rockchip-common.h:17` 的 `#define BOOT_TARGETS "mmc1 mmc0 nvme scsi usb pxe dhcp spi"`（#ifndef 保护）→ bootflow scan 砍不到 USB/pxe/dhcp，卡 BOOTP（PHY autoneg -110/-4）。
- 解：`include/configs/evb_rk3588.h` 在 `#include <configs/rk3588_common.h>` **之前** 加 `#define BOOT_TARGETS "mmc0"`（#ifndef 即覆盖，跟 genbook-cm5-rk3588.h 同款 idiom）。
- **真机结果：不够**。bootflow 只扫 mmc0，但 script bootmeth 仍**不在 mmc 0:3 命中 boot.scr**（"No more bootdevs"，0 bootflow），落 prompt。boot_targets 只砍了 BOOTP 超时，没解决 bootflow 不匹配 boot.scr。

### 0002 baud 115200（+ 自挖回归坑）
- upstream `evb-rk3588_defconfig` 的 `CONFIG_BAUDRATE=1500000`（Rockchip 默认），要改 115200 跟链路对齐。
- **9e3de8e1 回归**：这个 115200 编辑原本是**未提交的 defconfig dirty 改动**。做 0001 时 `git reset --hard` 把它冲掉了 → defconfig 回 1500000 → u-boot 用 1500000，跟 115200 的 DDR/BL31/kernel 打架 → BL31 `Entry point=0x800000` 交班后 u-boot 阶段**全乱码**（`󈤸񏿛󨲝`），看着像挂。
- 诊断：`strings u-boot.itb | grep baudrate=` → `1500000`（该是 115200）。
- 解：落成正经 patch `0002-evb-rk3588-baud-115200.patch`（defconfig `CONFIG_BAUDRATE=115200`）。
- **教训**：third_party 树里任何 dirty 改动，`git reset --hard` 前先 `git status` + stash/commit；最好一开始就落成 patch。

### 0003 直接 bootcmd（绕 bootflow）
- bootflow scan 不找 boot.scr（见 0001 真机结果）→ 把手动那条写死成 `CONFIG_BOOTCOMMAND`：
  ```
  CONFIG_BOOTCOMMAND="load mmc 0:3 ${scriptaddr} /boot/boot.scr; source ${scriptaddr}"
  ```
  `scriptaddr=0x00c00000`（rk3588_common.h:22）。bootcmd 来自 `boot/Kconfig:1975` 默认 `bootflow scan -lb`（BOOTSTD_DEFAULTS），defconfig 显式设 CONFIG_BOOTCOMMAND 即覆盖（依赖 `USE_BOOTCOMMAND=y`，已开）。
- boot_targets（0001）现在是个摆设但无害。

## 真机结果

8520c77f：autoboot 自动 boot → kernel → systemd。✅ 不用手动 source 了。

## 关键文件

- `patches/rk3588-topeet/uboot/0001-boot-targets-emmc-only.patch`
- `patches/rk3588-topeet/uboot/0002-evb-rk3588-baud-115200.patch`
- `patches/rk3588-topeet/uboot/0003-evb-rk3588-bootcommand-emmc.patch`
- `board/rk3588-topeet/fit/boot-emmc.cmd`（boot.scr 源：mmc dev 0 → setenv bootargs → mmc read 0x08000000 0x6000 0x20000 → bootm）
