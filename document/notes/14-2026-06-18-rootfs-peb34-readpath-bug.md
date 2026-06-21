# 14 — rootfs PEB3/4 "loader 弱写" 复查（★最终:loader 弱写真,翻案作废）

> ## ★★★ 最终结论(2026-06-18,trace + datasheet 铁证):loader 弱写**真**,翻案作废
> 本文前半段("翻案 H1=Linux 读 bug")**作废**。trace v2 + W25N04KV datasheet §7.3.1 推翻:
> - rootfs PEB3/4 pg=3,5 **st=0x20** = SR bit[5:4]=10 = "NOT corrected"(>8 flip **不可纠**)。pg=4 st=0x10(1-4 corrected)。
> - **mainline ecc_get_status 正确**(0x20=UNCOR_ERROR ✓,0x30=5-8 corrected ✓)——不需要改 mainline。
> - **loader 写这几页弱(>8 flip)坐实**,saga 原结论对,ubiprog 必要。
> - 翻案错因:①U-Boot 无-74 是那次 loader 写 ≤8 flip(ECC 纠了);loader 写**抖动**(1427 烧 >8)。①②"同次烧"前提也不成立。单次 ECC 读不能判 loader 写稳定性,要看 SR 真值(trace)。
> - 副产物:80MHz 读速定型(real 75M,DLL cell 130 窗口[90,170],读稳);100M 不行(PLL 98M tap,DLL wid=[0,0])。
> - 证据: boot-sdl-202606181427.txt(trace v2 SR)、boot-sdl-202606181508.txt(80MHz)、W25N04KV datasheet §7.3.1(mouser PDF)。

---

# 14 — rootfs PEB3/4 "loader 弱写" 翻案 + H1（Linux 读 bug）板上定论（已作废,见上方最终结论）

**日期**: 2026-06-18  **状态**: 验证全部做完，根因 H1 板上定论。直接开修 Linux 读路径（暂未固化正式记忆，防修复中翻新）。
**关联 log**: `boot-sdl-202606180943.txt`(①) · `boot-sdl-202606181000.txt`(②③)

## 一句话结论
rootfs PEB3/4 的 `-74` ECC error **根因 = Linux SFC 驱动读路径 bug**，非 loader 弱写。和 boot `0x920000` 同款读侧误诊。saga「rkbin loader 弱写通病」彻底作废。

## 验证矩阵（写者 × 读者，4 格全板上证据）
| # | 写者 | 读者 | 结果 | 证据 |
|---|---|---|---|---|
| ① | loader | U-Boot | ✅ 干净（RAW 零 flip，md.b bit-exact 源） | 0943 log |
| ② | loader | Linux | ❌ 爆 uncorrectable（3/64 页） | 1000 log 行 344-345 |
| ③ | Linux（ubiprog+commit） | U-Boot | ✅ 干净（RAW 零 flip，md.b==源） | 1000 log 行 448-480 |
| ④ | Linux | Linux | ❌ 爆 -74 | saga |

②③ 交叉 → **H1 定论**：loader 写干净（①）、Linux 写也干净（③）→ 写侧完全无辜；只要 Linux 读就爆（②④）、U-Boot 读永远干净（①③）→ 纯 Linux 读路径 bug。

## 爆页特征（修复关键线索）
- Linux 读 PEB3/4：**64 页里仅 3 页爆** uncorrectable，其余 61 页（含 page0 的 `55 42 49 23`）Linux 读也干净
- → 读 bug 对**特定数据模式**触发，非整块、非 DLL 窗口（Linux cell 96/窗口[0,240]，U-Boot cell 92/窗口[0,230]，都在中点）
- **反物理铁证**：U-Boot `real=100MHz` 读干净，Linux `real=50MHz` 读爆——50MHz 比 100MHz 宽松却爆，信号完整性不可能，必是读路径逻辑 bug

## ubiprog 重新定性
不是「兜 loader 弱写」，是**绕过 Linux 读 bug**：
1. loader 写 PEB3/4（含触发 bug 的 3 页数据模式）
2. Linux 读这 3 页 → misread → uncorrectable
3. ubiprog page recovery 把 3 页填 0xFF + Linux 重写其余（写干净，③证）
4. 重写后 3 页是 0xFF（不再触发读 bug）→ UBIFS 容忍 → mount OK
→ **真修 = 修 Linux 读路径让那 3 页也干净读 → ubiprog 可去除**

## 修复方向（三方对比，差异即 bug）
U-Boot 读干净、vendor 读干净（saga 证 ATK RW 稳）、Linux 主线读爆：
- Linux 主线（嫌疑）：`third_party/explore/linux/drivers/spi/spi-rockchip-sfc.c`
- U-Boot（参考，读干净）：`third_party/explore/uboot/drivers/spi/rockchip_sfc.c`
- vendor（参考，读干净）：vendor-sdk `spi-rockchip-sfc.c`
- ECC 读路径：`drivers/mtd/nand/spi/{core,winbond}.c`（saga 疑 `spinand_upd_cfg` 缓存对 `ECC_EN` 撒谎）

重点对比维度：读命令序列（x4 / cache opcode）、ECC 状态机读取、DLL cell 选取逻辑、中断/时序、page 读取的 DMA/FIFO 处理。

## P5 悖论消除
loader 写 boot `0x920000` 干净、写 rootfs PEB3/4 也干净 → 同一 loader 两处都干净。「为什么 boot 干净 rootfs 弱」的悖论源于**用 Linux 读 rootfs**——换 U-Boot 读，两处都干净。

## 待办（修复后）
- 定位 Linux 读 bug → 修 `spi-rockchip-sfc.c` 读路径 → 板验那 3 页干净读
- 修好后：ubiprog 降级为可选/移除，rootfs loader 直挂可读
- 再固化正式记忆（reexam 标结果 / saga 第二条翻案横幅 / roadmap P5 转 Linux 读侧）

## ★ 100MHz cell-92 实验结论（2026-06-18 11:15，log boot-sdl-202606181115）— 排除速率/DLL/cell，锁定读路径代码
改 DT 100MHz 上板：
- **Linux 100MHz DLL 调谐失败**（`widest=[0,0]` 0 cells，行 487）→ 回退 24MHz（无 DLL）。Linux 100MHz DLL 和 U-Boot 100MHz（cell 92/窗口[0,230]）表现完全不同（98MHz real vs 100MHz，或调谐实现差异）。
- **24MHz 无 DLL 下 ubiprog 读 PEB3/4 仍爆 3/64 页**（行 552-553）。
- **决定性推理**：24MHz 是最慢最稳、无采样调谐的读；U-Boot 100MHz（更快）读 PEB3/4 干净。若根因是速率/DLL/cell/采样，24MHz 不可能爆。→ **根因彻底排除速率/DLL/cell/采样，锁定 Linux 读路径代码本身**（SFC PIO `read_fifo`/`xfer_data_poll` 或 spinand core ECC 处理）。
- 印证 saga 早年"v5 24MHz 照样爆 PEB 3/4"——saga 误归写，实为读（U-Boot 读干净）。
- 24MHz 数据物理该干净（①证 loader 写零 flip）却报 uncorrectable → 最像 **ECC 状态读取/处理被代码搞错**（`w25n02kv_ecc_get_status` 嫌疑 #2 升为主嫌；`spinand_upd_cfg` CFG 缓存对 ECC_EN 撒谎）。
- **下一步**：深挖 mainline vs vendor 的 spinand core ECC 读路径（不靠 agent 泛泛对比，自己盯 24MHz 无 DLL 这条最简路径）+ 必要时加 trace 看那 3 页的 SR ECC status byte。
