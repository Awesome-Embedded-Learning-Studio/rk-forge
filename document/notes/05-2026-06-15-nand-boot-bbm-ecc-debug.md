# 2026-06-15 NAND 内核引导 — BBM/ECC 排查笔记

> ⚠️ **本文状态:历史记录,结论已过时。** 这篇把 corrupt 归因到 ECC/BBM 是**错的**——
> 真因是主线 `rockchip_sfc.c` 在 80MHz 跑且无 DLL 调谐(不是 on-die ECC,不是框架失配)。
> 已修复(DT `spi-max-frequency` 80→50MHz),主线 Linux 已启动到 UART。
> **以 [07-...-milestone-mainline-linux-boots.md](07-2026-06-15-milestone-mainline-linux-boots.md) 为准。**
> 保留本文仅为记录排查弯路(别再走)。

> 承接 [04-...-mainline-uboot-via-vendor-spl.md](04-2026-06-14-mainline-uboot-via-vendor-spl.md)(方案 B U-Boot prompt 达成)。
> 本篇: 让 U-Boot 从 SPI NAND 读内核引导,卡在 data corrupt。

## 目标

主线 U-Boot 从板载 SPI NAND(W25N04KV)读 `kernel.itb`(zImage+dtb FIT),`bootm` 引导到 earlycon。PLAN 唯一硬里程碑("主线 Linux 启动到 UART")。

## 已达成

1. U-Boot 加 SFC+SPI NAND(defconfig + dtsi sfc 节点 compatible=`rockchip,sfc`)→ `mtd list` 见 `spi-nand0`(W25N04KV 512MB)+ `boot` 分区(16MB)。
2. `kernel.itb` 写 boot 分区(vendor RKDevTool)。dump 证实 data 100% 正确(FIT 结构完整)。

## 卡点:data corrupt

`mtd read`(默认)读出 `d0 0d de ed`(FIT magic 第 3 字节 bit 翻 `fe`→`de`),bootm Wrong Image Type。`mtd read.raw`(关 ECC)读出正确的 `d0 0d fe ed`。

## 排查过程(时间线)

1. **mtd read 越界**(offset 0x1000000)→ `mtd bad` 71/128 bad(含 erase 区)→ 不是 OOB 值问题,是 `spinand_read_page` 中途失败。
2. hack `spinand_isbad` return false → mtd read 不越界,读 12MB 成功。
3. **bootm Wrong Image Type** → md.b `d00ddeed`(corrupt)。
4. `mtd read.raw` `d00dfeed`(正确)→ 怀疑片内 ECC 错误"纠正"vendor 软件 ECC 的 page。
5. 误 hack `spinand_read_page`(发现 mtd read 不经它,走 `spinand_mtd_regular_page_read`)→ 回滚。
6. hack `spinand_ondie_ecc_prepare_io_req` 总关片内 ECC → **仍 corrupt**。

## 现状矛盾

hack prepare 关片内 ECC 后,`mtd read`(非 raw)仍读 corrupt,而 `mtd read.raw` 读正确。二次复核后 continuous read 基本排除:W25N04KV 无 `set_cont_read`,且 continuous path 本身也会调 prepare。当前更怀疑 prepare 运行时没有真的清掉硬件 `REG_CFG` bit4(`CFG_ECC_ENABLE`),或 cfg cache 与真实寄存器状态不一致;需加 printf 直接读 `REG_CFG` before/after。

## 当前 hack(`drivers/mtd/nand/spi/core.c`)

- `spinand_isbad`(970): return false
- `spinand_ondie_ecc_prepare_io_req`(302): 总 `spinand_ecc_enable(spinand, false)`
- `spinand_read_page`(636): 已恢复原样(误改回滚)

## 下一步

~~printf + REG_CFG~~(已做,证 ECC bit4 清 0,corrupt 不是 ECC)。~~sfc-no-dma~~(已做,PIO 也 corrupt)。

## ⭐ 根因找到(2026-06-15,大 AI 裁决): SFC 采样时序(不是 ECC/DMA/dirmap!)

大 AI 二次复核 + vendor SFC bad block 扫描日志(见 [06-...-nand-recovery-vendor-sfc-bbt.md](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md))定位真因:

**主线 `drivers/spi/rockchip_sfc.c` 没有 DLL(采样延迟线)调优,vendor driver 有 `rockchip_sfc_delay_lines_tuning`。** 80MHz 不调优时,SFC 读采样边际 → 非确定性 bit 错误(FIT magic `fe`→`de`→`dc`) + 最终锁死(全 `0xee`)。

这解释了之前所有现象:
- ECC 关了(bit4=0 printf 实证)没用 — 不是 ECC
- PIO(`sfc-no-dma`)也 corrupt — 不是 DMA
- `rdesc_ecc=rdesc`(core.c:1185) — 不是 dirmap
- `mtd read.raw` 偶尔对 — 采样边际,非确定性
- printf `spinand_read_reg_op` 打断 SFC 状态 → 全 ee + 扰动 CFG 搞砖板

**解法**: `spi-max-frequency` 降到 **50MHz**(vendor `SFC_DLL_THRESHOLD_RATE`)。`arch/arm/dts/rk3506-u-boot.dtsi` 的 `flash@0` 已改:
```dts
spi-max-frequency = <50000000>;  /* ≤50MHz safe without DLL; 80MHz marginal */
```
50MHz 版 U-Boot FIT md5 `2f81f8e9`,**待上板测试**(只换 uboot 分区,mtd read 应读正确 d00dfeed)。

## 编译 + 拷贝指令(速查,详见 memory `uboot-build-flash-commands`)

```bash
# 编译 U-Boot(改 defconfig 后先 evb-rk3506_defconfig + olddefconfig):
cd third_party/explore/uboot
TC=third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
RK=third_party/explore/rkbin/bin/rk35
make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) ROCKCHIP_TPL=$RK/rk3506b_ddr_750MHz_v1.06.bin TEE=$RK/rk3506_tee_v2.40.bin

# 打包方案 B FIT:
cp u-boot-nodtb.bin u-boot.dtb third_party/bringup/fit/
(cd third_party/bringup/fit && ../../vendor-sdk/u-boot/tools/mkimage -f rk3506-mainline.its -E rk3506-mainline.itb)

# 拷 Windows:
cp third_party/bringup/fit/rk3506-mainline.itb /mnt/d/DownloadFromInternet/rk3506-uboot-mainline-vendor-fit.itb
```

## 当前状态(2026-06-15)

- **50MHz 修复版**(md5 `2f81f8e9`)待上板: 烧 uboot 分区 → `mtd read` → `md.b` 应 `d00dfeed`(正确)→ `bootm` → earlycon。
- 板子已全擦恢复(稳定版能 prompt)。
- vendor SFC bad block 扫描日志在 [06 笔记](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md)。
- **避坑**: 不要用 `spinand_read_reg_op` 做 printf(打断 SFC + 扰动 CFG,搞砖板)。

## 关键文件

- U-Boot spinand driver: `third_party/explore/uboot/drivers/mtd/nand/spi/core.c`
- W25N04KV 配置: `third_party/explore/uboot/drivers/mtd/nand/spi/winbond.c:483`
- 内核 FIT: `third_party/bringup/fit/rk3506-kernel.itb`(+ `.its`)
- U-Boot FIT(方案 B): `third_party/bringup/fit/rk3506-mainline.itb`
- 上板日志: `document/logs/boot-sdl-202606150723.txt`(mtd read corrupt)、`uboot-debug.txt`(dump)
