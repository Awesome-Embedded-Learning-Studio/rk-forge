# RK3588 topeet — update.img 产出流程 + bootloop 问题梳理

> 给大 AI 诊断用。自包含，不依赖 forge 上下文。

## 1. 目标

RK3588 板（iTOP-RK3588 / topeet，`rockchip,rk3588-evb3-lp5-v10`，eMMC 16G，LPDDR4X 2112MHz）走**主线优先**：主线 linux kernel v7.1 + 主线 u-boot 2026.07-rc4 + Ubuntu 26.04 rootfs，产 RKAF update.img 烧 eMMC。

对照板：RK3568-atk（atk EVB1 DDR4），**同款 forge 流程已真机 boot 成功**（主线 u-boot + rkbin SPL/BL31 + buildroot rootfs）。

## 2. update.img 怎么产的（forge 工具链）

### 2.1 各组件

| 组件 | 来源 | 产物 |
|---|---|---|
| **kernel** | 主线 linux **v7.1**（kernel.org stable） | `Image`（arm64，44MB）+ `rk3588-topeet.dtb`（板 DT，97KB）|
| **u-boot** | 主线 u-boot **2026.07-rc4**（denx，pin `5ca1a73c`），`evb-rk3588_defconfig` + binman | `u-boot.itb`（1.18MB）+ `idbloader.img`（binman 主线 SPL，202KB）|
| **loader** | boot_merger（rkbin public blobs）+ `RKBOOT-RK3588-topeet.ini` | `MiniLoaderAll.bin`（558KB）|
| **rootfs** | Ubuntu 26.04（ubuntu-base + apt，GNOME） | `rootfs.ext4`（3 GiB）|
| **boot.img** | kernel FIT（Image + dtb，no ramdisk） | `boot.img`（44MB）|

### 2.2 u-boot.itb 结构（binman，dumpimage 确认）

```
Image 0 (u-boot):  Load 0x00800000  Entry 0x00800000  (818288 B, sha256 e0f0a73688…)
Image 1 (atf-1):   Load 0x00060000                     (149020 B, sha256 f99c6f8fb6…)
Image 2 (atf-2):   Load 0x000f0000                     (24576 B,  sha256 13b94d9d5a…)
Image 3 (atf-3):   Load 0xff100000                     (36864 B,  sha256 74bbc58e20…)
+ fdt-1 (u-boot.dtb, 203520 B, sha256 26e3a4a389…)
```
- BL31 = rkbin `rk3588_bl31_v1.54.elf`（binman 经 `BL31` env 嵌入）
- ROCKCHIP_TPL（DDR）= rkbin `rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.21.bin`
- TEE/bl32 **省略**（rkbin bl32 是 raw .bin，binman tee-os 要 ELF；OP-TEE 非必需）

### 2.3 MiniLoaderAll.bin（boot_merger，RKBOOT ini）

含 idblock：rkbin `rk3588_ddr_lp4_2112_lp5_2400MHz_v1.21.bin`（FlashData/DDR init）+ `rk3588_spl_v1.14.bin`（FlashBoot/SPL）+ `rk3588_usbplug_v1.11.bin`（download 协议）。**`rk3588_spl_v1.14.bin` 是 vendor 编译的 SPL（U-Boot SPL 2017.09-gc28d9f4e210-250928 #lxh，topeet SDK）**。

### 2.4 update.img 组装（rkfw-pack，RKFW+RKAF）

`package-file-emmc.txt`：
```
bootloader  MiniLoaderAll.bin   # download loader（boot_merger，含 rkbin ddr+spl idblock）
parameter   parameter.txt       # GPT: uboot@0x4000(4MiB) boot@0x6000(64MiB) rootfs@0x26000(8GiB)
uboot       u-boot.itb          # 主线 u-boot（binman），写 @0x4000
boot        boot.img            # kernel FIT，写 @0x6000
rootfs      rootfs.img          # ext4，写 @0x26000
```
→ `update.img`（3.06G，rkfw-pack self-check round-trip 过）。

### 2.5 烧录（RKDevTool uf / rkdeveloptool）

- loader（MiniLoaderAll）→ `db`（download 模式）+ **写 idblock @0x40**（rkbin ddr + `rk3588_spl_v1.14`）
- RKAF → GPT + uboot（@0x4000）+ boot（@0x6000）+ rootfs（@0x26000）
- **注意**：主线 binman `idbloader.img`（主线 TPL+AARCH64 SPL）**没进 update.img**——@0x40 用的是 boot_merger 的 rkbin SPL（vendor 2017.09）。RK3568-atk 同款（rkbin `rk356x_spl` @0x40）真机 OK。

## 3. bootloop 现象（bootlog: document/logs/rk3588/202607271337.txt）

```
BootROM
 → @0x40 idblock: rkbin DDR init（LPDDR4X 2112MHz, 4×4096MB=16GB）✓ + rk3588_spl v1.14（vendor 2017.09 SPL）
   → U-Boot SPL 2017.09-gc28d9f4e210-250928 #lxh  ← rkbin rk3588_spl，正常
   → MMC2 空 / MMC1 no misc → fit @0x4000
   → 验证 atf-1/u-boot/fdt-1/atf-2/atf-3 全 sha256 OK（u-boot=e0f0a73688 匹配主线产物）
   → Jumping to U-Boot(0x00800000) via ARM Trusted Firmware(0x00060000)
 → 主线 u-boot（2026.07）跳进去后【没出 banner】立即复位
 → 回到 DDR，循环（bootloop，已观察 23+ 次）
```

**关键**：
- DDR 训练、SPL 加载、u-boot.itb 验证全过（sha256 匹配）
- 主线 u-boot 跳转后**没任何输出**（连 early DEBUG_UART banner 都没有），立即重启
- 主线 u-boot 配置：`CONFIG_DEBUG_UART_BASE=0xFEB50000`（uart2），`CONFIG_BAUDRATE=1500000`（串口 1500000 匹配，vendor SPL 输出可读）

## 4. 根因怀疑（未最终定位）

1. **vendor rkbin `rk3588_spl_v1.14`（2017.09）跳主线 u-boot（2026.07）不兼容**——跨 9 年版本，ATF 跳转协议 / fit 解析约定可能不兼容。但 RK3568（rkbin `rk356x_spl` + 主线 u-boot）真机 OK，所以是 RK3588 的 rkbin SPL 特有。
2. 主线 u-boot 自身在 topeet 板跑挂（DRAM/时钟/console init 前）——但主线 evb-rk3588 defconfig 是主线 CI 测过的。
3. rkbin `rk3588_bl31_v1.54`（BL31）跳 BL33（u-boot）异常。

## 5. 排除法（建议但未验——用户当前烧不了 @0x40）

烧**主线 binman idbloader.img**（主线 TPL+AARCH64 SPL，build-uboot 已产）到 @0x40，替代 rkbin SPL，让 boot 链全主线：

```
rkdeveloptool db MiniLoaderAll.bin
rkdeveloptool wl 0x40 idbloader.img     # 主线 binman idbloader
rkdeveloptool uf update.img
rkdeveloptool rd
```

- 出 `U-Boot 2026.07-rc4` banner → rkbin `rk3588_spl` 是凶手
- 仍 bootloop → 主线 u-boot 自身/DARM 问题，需 early-debug / kgdb

## 6. 关键文件

- `update.img` / `u-boot.itb` / `idbloader.img` / `MiniLoaderAll.bin`：`board/rk3588-topeet/out/`
- bootlog：`document/logs/rk3588/202607271337.txt`（212 行，bootloop 循环）
- u-boot 源：`third_party/src/rk3588-topeet/uboot`（主线 2026.07-rc4，pin 5ca1a73c）
- kernel 源：`third_party/src/rk3588-topeet/linux`（v7.1）
- rkbin blobs：`third_party/rkbin/bin/rk35/`（rk3588_ddr/spl/bl31/bl32/usbplug）

## 7. 待大 AI 诊断的问题

1. vendor rkbin SPL（2017.09）+ 主线 u-boot（2026.07）的跳转链，有哪些已知不兼容点？为什么 RK3568 的 rk356x_spl + 主线 u-boot OK，而 RK3588 的 rk3588_spl 不行？
2. 主线 u-boot 跳进去后连 DEBUG_UART early banner 都没有，立即复位——最可能挂在 _start 到 console init 之间的哪一步？（reloc？DRAM 重配？ATF SMC？）
3. RK3588 主线 u-boot + rkbin BL31/TPL 的已知正确组合（rkbin blob 版本 / u-boot 配置）是什么？是否有 rkbin `rk3588_spl` 的替代（主线 SPL）的已知坑？
