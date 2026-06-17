# document/notes — dated bringup log

This tier holds **honest, dated bringup notes** — what worked, what didn't, the exact
UART output, the brick scares. It's the project's honesty substrate (on-brand:
rk-forge's identity is "report the gap truthfully").

> 在 [document/](../) 四层结构里,这里是 **raw 过程笔记**层(取证源)。踩坑日记在
> [pitfalls/](../pitfalls/)(回溯提炼的完整叙事 + canonical 结论),被推翻的旧结论在
> [archive/](../archive/),板上日志在 [logs/](../logs/)。本目录不删、不去重 —— 它是按天的
> 流水,和 pitfalls 重叠是正常的,一个记现场、一个讲结论。

## 命名约定

`NN-YYYY-MM-DD-<slug>.md` — **序号 + 日期 + slug**:

- **序号 `NN`** = 推荐阅读顺序(理解项目的递进阶段),主导排序。
- **日期 `YYYY-MM-DD`** = 笔记对应的工作日期。
- **slug** = 内容一句话描述。

跨阶段持续更新的"活文档"用其主工作日期。Don't sanitize failures — they're the
most useful part.

## 阅读顺序(按阶段递进)

| 序号 | 文件 | 阶段 |
|---|---|---|
| 01 | [01-…-vendor-uboot-build-flow](01-2026-06-14-vendor-uboot-build-flow.md) | 先懂 vendor 怎么编 U-Boot(主线迁移的参照基准) |
| 02 | [02-…-mainline-bringup-handoff](02-2026-06-14-mainline-bringup-handoff.md) | 主线 U-Boot bring-up 状态总览(活文档,跨阶段) |
| 03 | [03-…-maskrom-brick-recovery](03-2026-06-14-maskrom-brick-recovery.md) | 救砖插曲:固件写坏 → MaskROM 恢复 |
| 04 | [04-…-mainline-uboot-via-vendor-spl](04-2026-06-14-mainline-uboot-via-vendor-spl.md) | 方案 B:借 vendor SPL 跑主线 U-Boot,真板进提示符(里程碑) |
| 05 | [05-…-nand-boot-bbm-ecc-debug](05-2026-06-15-nand-boot-bbm-ecc-debug.md) | NAND boot 的 BBM/ECC 调试(SFC 读 corrupt 起点,saga 段一误判) |
| 06 | [06-…-nand-recovery-vendor-sfc-bbt](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md) | 借 vendor SFC bbt 恢复 NAND(saga 段二,DLL 初判) |
| 07 | [07-…-milestone-mainline-linux-boots](07-2026-06-15-milestone-mainline-linux-boots.md) | 主线 Linux boot 到 `~ #` 里程碑(定型日志在此) |
| 08 | [08-…-replace-sdk-nand-packaging](08-2026-06-15-replace-sdk-nand-packaging.md) | 取代 SDK 的 NAND 打包(chip tag / parameter / 分区) |
| 09 | [09-…-vendor-nand-packaging-forensics](09-2026-06-15-vendor-nand-packaging-forensics.md) | vendor NAND 打包取证(update.img 结构 / mk-updateimg) |
| 10 | [10-…-dt-migration-sfc-spi-nand-partitions](10-2026-06-15-dt-migration-sfc-spi-nand-partitions.md) | DT 迁移:SFC + SPI-NAND 分区,板门验证通过 |
| 11 | [11-…-patch-verification-rw-rootfs](11-2026-06-16-patch-verification-rw-rootfs.md) | patch 验证:RW rootfs patch 在干净上游逐字节相同 |
| 12 | [12-…-kill-vendor-sdk-assessment](12-2026-06-17-kill-vendor-sdk-assessment.md) | 彻底干掉 vendor_sdk:评估 + P0–P5 路线图(本 P0 的源头) |

另有 [nand-ecc-debug-handoff.md](nand-ecc-debug-handoff.md)(早期 NAND ECC 调试交接,部分结论已被后续 saga 取代,以 [pitfalls/04](../pitfalls/04-sfc-nand-saga.md) 为准)。

## 与 pitfalls 的关系

本目录是按天记的 raw 现场(含失败、噪音、半成品、当时的错判);[pitfalls/](../pitfalls/) 是事后回溯、把 12 条坑按故障域重新组织成的完整叙事 + canonical 结论。要快速理解"踩了哪些坑、怎么解的",直接读 pitfalls;要还原某一天的原始折腾,翻这里。saga 那段被推翻的旧结论(HANDOFF/POSTMORTEM/RW-WRITE-FIX)已移入 [archive/](../archive/)。

## 待补

- `NN-2026-06-13-restructure.md` — repo 重构 + 前提验证(对应 commit `325a3bf`,目前无独立笔记)。
- vendor-sdk 总体调研(当前散在 01 里,可抽独立笔记)。
