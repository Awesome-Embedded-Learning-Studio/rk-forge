# 49 RK3588 移植起点：bootloop + mainline SPL 修复 (2026-07-27)【前传】

> RK3588（iTOP-RK3588 / topeet）主线移植的**第 0 关**。本篇是 43-48 的前传（早于 autoboot/LCD）。详细 bootlog + 分析见 `document/logs/rk3588/bootloop-analysis.md`（自包含）。

## 目标

RK3588 topeet 走主线优先（跟 RK3568 同款）：主线 kernel v7.1 + 主线 u-boot 2026.07-rc4（binman）+ Ubuntu 26.04，产 RKAF update.img 烧 eMMC。对照板 RK3568-atk（主线 u-boot + rkbin SPL/BL31 真机 OK）。

## 症状：bootloop

```
BootROM → @0x40 idblock（rkbin DDR init + rk3588_spl v1.14）
  → U-Boot SPL 2017.09 ... → 验 atf/u-boot/fdt 全 sha256 OK
  → Jumping to U-Boot via ARM Trusted Firmware(0x00060000)
  → 【没出 banner】立即复位 → 回 DDR → 循环（观察 23+ 次）
```

**关键诊断点**：bootlog 有没有 `NOTICE:  BL31:`——没有就是 SPL→BL31 断了。

## 根因：vendor rk3588_spl + BL31 v1.54 基址错配（最坑）

- rkbin vendor `rk3588_spl_v1.14`（U-Boot SPL 2017.09）**早于** BL31 v1.54。
- BL31 v1.54 把 `bl31_base` 从旧地址迁到 **0x60000**，但旧 SPL（v1.14）还按旧基址跳 → **BL31 没进** → bootloop。
- RK3568 的 `rk356x_spl` 没这基址迁移，所以 RK3568 用 vendor SPL OK，**RK3588 不行**。

## 修复：SPL_SOURCE=mainline

`config/boards/rk3588-topeet.env` 设 `SPL_SOURCE=mainline`：pack-loader 不用 vendor `rk3588_spl`，改用 build-uboot 编出来的 `u-boot-spl.bin`（主线 SPL，跟 BL31 v1.54 同代）。U-Boot 官方 RK3588 流程就是 **rkbin DDR 作 TPL + mainline SPL + binman**。

boot 链变成：BootROM → idblock（rkbin DDR init + **mainline SPL**）→ BL31 v1.54（`NOTICE: BL31` 出现✓）→ u-boot。

## 教训

- **SPL/BL31 必须同代**：vendor rkbin 的 rk3588_spl 老于 bl31 时会踩基址迁移。诊断靠 bootlog 的 `NOTICE: BL31:` 有无。
- 别照搬 RK3568 的"vendor SPL + 主线 u-boot"——RK3588 的 rkbin rk3588_spl 有这坑，得用 mainline SPL。

## 关键文件

- `config/boards/rk3588-topeet.env`：`SPL_SOURCE=mainline`、rkbin blob tuple（BL31=`rk3588_bl31_v*.elf`、DDR=`rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.*.bin`）
- `document/logs/rk3588/bootloop-analysis.md`：完整 bootlog + 诊断 + 排除法（自包含）
- 后续首启见 [50](50-2026-07-27-rk3588-first-boot-baud-root-dt.md)；autoboot/LCD 见 43-48。
