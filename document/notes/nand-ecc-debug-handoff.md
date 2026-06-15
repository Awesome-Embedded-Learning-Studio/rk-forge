# RK3506B NAND 内核引导 — mtd read data corrupt 排查现状

> ⚠️ **本文状态:历史记录,根因判断已推翻。** 这篇"给大 AI 裁决"的核心怀疑(ECC/prepare/
> continuous read)全部**已证伪**。真因是主线 `rockchip_sfc.c` 80MHz 无 DLL 调谐,已修(50MHz)。
> 主线 Linux 已启动到 UART。**以 [07-...-milestone-mainline-linux-boots.md](07-2026-06-15-milestone-mainline-linux-boots.md) 为准。**
> 保留本文仅为排查时间线 + 代码位置参考(别再按它的方向查)。

> **给大 AI 裁决/解决用。自包含,无需其它上下文。**
> 项目: rk-forge(把主线 Linux + 主线 U-Boot 在 ATK RK3506B 跑起来)。
> 问题性质: SPI NAND 读路径的 ECC/data corrupt,bit 级。

---

## TL;DR

主线 U-Boot 从板载 SPI NAND(Winbond W25N04KV)读内核 FIT。`mtd read.raw`(关片内 ECC)读出**正确** data(FIT magic `d0 0d fe ed`),但 `mtd read`(默认非 raw)读出的 data 被 **corrupt**(同一字节变 `d0 0d de ed`,bit5 翻转)。已 hack ECC engine 的 prepare 让它总关片内 ECC,但 corrupt **依旧**。二次复核后:continuous read 基本可排除,更应优先验证 **prepare 是否运行、REG_CFG bit4(CFG_ECC_ENABLE)是否真的在硬件里清掉、raw/non-raw 的 req 参数差异**。请裁决根因 + 解法。

## 项目背景

- **板子**: ATK RK3506B(arm32 Cortex-A7 ×3, **SPI NAND** Winbond W25N04KV 4Gbit/512MB, 从 SPI NAND 启动)。
- **主线内核**: Linux v7.0.12(`third_party/explore/linux`,已编出 `zImage` 11.4MB + `rk3506b-aes.dtb`)。
- **主线 U-Boot**: `2026.07-rc4`(`third_party/explore/uboot`,借 vendor DDR+SPL+op-tee 跑到 prompt——方案 B)。
- **vendor SDK**: ATK-DLRK3506 BSP(`third_party/vendor-sdk`,linux 6.1,U-Boot 2017 fork)。

## 已达成(都验证过)

1. 主线 U-Boot 跑到交互 prompt(vendor SPL 加载主线 U-Boot FIT,`U-Boot 2026.07-rc4` banner)。
2. U-Boot 加了 SPI NAND 能力:
   - defconfig 加 `CONFIG_ROCKCHIP_SFC` + `CONFIG_MTD_SPI_NAND` + `CONFIG_DM_MTD` + `CONFIG_CMD_MTD`
   - dtsi 加 `sfc: spi@ff488000 { compatible="rockchip,sfc"; ... }` + `flash@0 { compatible="spi-nand"; ... }`(compatible 改 `rockchip,sfc` 适配主线 `drivers/spi/rockchip_sfc.c`,该驱动只认 `rockchip,sfc` 单一 compatible)
3. `mtd list` 正常: `spi-nand0`(Winbond W25N04KV, 512MiB, ECC 8-bit/512B, OOB 128) + `boot` 分区(16MB @ offset 0x1740000, mtdparts defconfig 设)。
4. 内核 `kernel.itb`(zImage + rk3506b-aes.dtb 的 FIT,vendor `mkimage -f kernel.its -E -p 0x800` 打包,12MB)已写 boot 分区(vendor RKDevTool "下载镜像")。

## 问题(data corrupt)

```
=> mtd read boot ${kernel_addr_r} 0 0xc00000      # 读 12MB FIT
=> md.b ${kernel_addr_r} 0x10
02080000: d0 0d de ed 00 00 04 00 00 00 00 48 ...   ← FIT magic 应是 d0 0d fe ed
                                                     ← byte[2]: fe(11111110)→de(11011110), bit5 翻
=> bootm ${kernel_addr_r}
Wrong Image Type for bootm command
ERROR -91: Protocol wrong type for socket: can't get kernel image!
```

## 关键矛盾(核心)

| 读法 | 片内 ECC | 结果 |
|---|---|---|
| `mtd read.raw boot ${addr} 0 0x840`(raw) | 关(MTD_OPS_RAW) | `d0 0d fe ed` **正确** + 完整 FIT 结构 |
| `mtd read boot ${addr} 0 0xc00000`(默认) | 开(非 raw) | `d0 0d de ed` **corrupt**(bit 翻) |
| `mtd read`(hack prepare 总关 ECC 后) | 应关 | `d0 0d de ed` **仍 corrupt** |

**raw 读正确、非 raw 读 corrupt,且 hack 了 prepare 关 ECC 还是 corrupt。**

## 排查时间线

1. `mtd read` 失败 offset 0x1000000(越界)→ `mtd bad boot` 列 **71/128** block bad(含 erase 区 block 93-125,erase page OOB 本该 0xff 却判 bad)→ 推断不是 OOB byte0-1 值问题,是 `spinand_read_page` 中途失败(marker 保持初值 0)。曾根据 dump 怀疑 boot 区 OOB byte0-1 被 vendor 写成 `4d 58`(ECC/metadata,覆盖了 BBM),但注意:现有 `mtd read.raw boot ${addr} 0 0x840` 会被命令层 round 到 0x1000、读两个 data page,且没有 `.oob`;dump 中 `0x800` 的 `4d 58...` 很可能是 FIT `mkimage -E -p 0x800` 的 external data 开头,**不能单独当作 OOB 证据**。若要坐实 OOB,需 `mtd read.raw.oob` 或专门读 OOB。
2. hack `spinand_isbad` return false(core.c:970)→ `mtd read` 不再越界,读 12MB 成功。
3. `bootm` Wrong Image Type → `md.b` 见 `d0 0d de ed`(corrupt)。
4. `mtd read.raw` 见 `d0 0d fe ed`(正确)→ 怀疑片内 ECC 把 vendor 软件 ECC 写的 page 当 bit-flip 去"纠正",反而 corrupt。
5. hack `spinand_read_page`(core.c:636)跳过 ondie ECC → 还 corrupt。**发现 hack 点错**:`mtd read` 不走 `spinand_read_page`,走 `spinand_mtd_regular_page_read`(core.c:819)。
6. `spinand_read_page` 恢复原样;hack `spinand_ondie_ecc_prepare_io_req`(core.c:302)让它总 `spinand_ecc_enable(spinand, false)`(关片内 ECC)→ **还 corrupt**(Banner `Jun 15 07:47:00` 确认是新编译的二进制,prepare 改动已在)。

## 当前两处 hack(`drivers/mtd/nand/spi/core.c`)

1. `spinand_isbad`(行 970): `return false`(不检查 BBM)。
2. `spinand_ondie_ecc_prepare_io_req`(行 302): 注释 `Force the on-die ECC engine OFF`,总 `return spinand_ecc_enable(spinand, false);`(去掉 `bool enable = (req->mode != MTD_OPS_RAW)` 逻辑)。

`spinand_read_page`(行 636)已**恢复原样**(之前误改跳过 ondie ECC,发现无效后回滚)。

## 怀疑根因(请重点排查)

**[二次复核:continuous read 基本排除]** W25N04KV 在 winbond.c 没设 cont_read flag/`set_cont_read` → `spinand->cont_read_possible`=false → `spinand_use_cont_read`(core.c:876)第一行就 `return false` → `mtd read` **走 `spinand_mtd_regular_page_read`**(core.c:919)。该路径会调用 `spinand_read_page` → `spinand_ondie_ecc_prepare_io_req`(core.c:647/302,即 hack 的函数)。另外,即便走 continuous path,当前 `spinand_mtd_continuous_page_read` 也会在 core.c:815 调 `spinand_ondie_ecc_prepare_io_req`。所以“绕过 prepare”不再是首要怀疑点。**真正矛盾是:prepare 理论上被调且总关 ECC,但 data 仍像被 on-die ECC 改过。**

`spinand_mtd_read`(core.c:897)顶层:
```c
if (spinand_use_cont_read(mtd, from, ops)) {
    ret = spinand_mtd_continuous_page_read(mtd, from, ops, &max_bitflips);
} else {
    ret = spinand_mtd_regular_page_read(mtd, from, ops, &max_bitflips);
}
```

### 二次复核后的高优先级怀疑点

1. **prepare hack 运行时没真的把硬件 ECC 关掉**
   - `spinand_ondie_ecc_prepare_io_req` 现在只是 `spinand_ecc_enable(spinand, false)`。
   - `spinand_ecc_enable` 最终走 `spinand_upd_cfg(... CFG_ECC_ENABLE, 0)`。该函数用 `cfg_cache`;如果 cache 与芯片真实 `REG_CFG(0xb0)` 不一致,可能认为已经关了而跳过实际 `SET_FEATURE`。
   - 需要在 prepare 内直接读硬件 `REG_CFG` before/after,确认 bit4 真的清 0。

2. **prepare hack 编译/运行镜像仍需强证据**
   - Banner 时间新只能证明换过镜像,不能证明该函数路径和该二进制逻辑都执行到了。
   - 必须在 `prepare` 打一次限频 printf,或打印 magic 字符串,确认 `mtd read` 实际调用。

3. **raw/non-raw 的 `read_from_cache_op` opcode 差异基本排除**
   - `read_from_cache_op` 按 `req->mode` 选 `rdesc`/`rdesc_ecc`(core.c:410)。
   - 但当前 `spinand_create_dirmap` 里 `rdesc_ecc = rdesc`、`wdesc_ecc = wdesc`(core.c:1185),所以不是“非 raw 发了另一种 read-cache opcode”。

4. **`finish_io_req` 不会改 data**
   - 非 raw 会继续查 ECC status,但 `spinand_ondie_ecc_finish_io_req` 只更新统计或返回 bitflips/`-EBADMSG`,不修改 data buffer。
   - 所以若 byte 真被翻,发生点应在 NAND page-to-cache 阶段(on-die ECC 仍实际开启)或 SFC/DMA 读 cache 阶段。

5. **SFC/DMA 是次级怀疑**
   - 普通读 2048B、raw 读 4096B/页循环,都超过 `SFC_DMA_TRANS_THRETHOLD` 会走 DMA,不是一个 DMA 一个 FIFO。
   - 若 CFG bit4 已确认关掉但仍 corrupt,可再试 DT 加 `rockchip,sfc-no-dma` 排除 DMA/cache 问题。

## 待解决(具体问题)

**为什么 `mtd read`(hack prepare 关片内 ECC 后)仍读 corrupt,而 `mtd read.raw` 读正确?**

排查方向(建议):
1. 在 `spinand_ondie_ecc_prepare_io_req` 加限频 `printf`:打印 `req->mode/type/pos(target/lun/plane/block/page)/dataoffs/datalen/ooblen/continuous`。
2. 在 prepare 里绕过 cfg cache,直接 `spinand_read_reg_op(spinand, REG_CFG, &cfg_before)`;调用 `spinand_ecc_enable(false)` 后再直接读 `cfg_after`,确认 `CFG_ECC_ENABLE` bit4 是否清 0。
3. 在 `spinand_load_page_op` 前后或 `spinand_wait` 后打印 status/CFG,确认 page read 期间 ECC 没被别处重新打开。
4. 对比 `mtd read` vs `mtd read.raw` 的 `spinand_read_from_cache_op` 参数:nbytes,column,req->mode,req->continuous。注意 raw 命令层会 round 到整页,不等同于 `.oob`。
5. 如果 CFG bit4 已确认清 0 但 corrupt 仍在:试 `rockchip,sfc-no-dma` 或强制 SFC FIFO,排除 DMA/cache;也可临时把普通 `mtd read` 的 `iter.req.mode` 强制改成 `MTD_OPS_RAW`,看是否立刻变正确。

## 关键代码位置

- `third_party/explore/uboot/drivers/mtd/nand/spi/core.c`:
  - `spinand_mtd_read`:897(顶层,分 cont/regular)
  - `spinand_mtd_regular_page_read`:~790(行 810 调 `spinand_ondie_ecc_prepare_io_req`)
  - `spinand_mtd_continuous_page_read`:?(cont read)
  - `spinand_use_cont_read`:?(判断)
  - `spinand_ondie_ecc_prepare_io_req`:302(**已 hack**: 总关 ECC)
  - `spinand_ondie_ecc_finish_io_req`:317(raw 返 0;非 raw 查 ECC status)
  - `spinand_isbad`:970(**已 hack**: return false)
  - `spinand_read_from_cache_op`:385(OOB 读,column 计算)
- `third_party/explore/uboot/drivers/mtd/nand/spi/winbond.c`: W25N04KV 配置 行 483(`NAND_MEMORG(1,2048,128,64,4096,40,2,1,1)`,`NAND_ECCREQ(8,512)`,`w25n02kv_ooblayout`,`w25n02kv_ecc_get_status`)。
- vendor 对照: `third_party/vendor-sdk/u-boot/drivers/mtd/nand/spi/core.c` 的 `spinand_read_page(req, bool ecc_enabled)`(行 527)——vendor 用 ecc_enabled 参数,isbad 调 `(req, false)` 不查 ECC;**vendor 2017 没有 continuous read / ondie ECC engine 框架**。

## 复现命令(U-Boot prompt, UART **1500000** baud)

```
=> mtd list                              # 确认 spi-nand0 + boot 分区
=> mtd read boot ${kernel_addr_r} 0 0xc00000
=> md.b ${kernel_addr_r} 0x10            # 见 d00ddeed (corrupt)
=> mtd read.raw boot ${addr} 0 0x840
=> md.b ${addr} 0x10                     # 见 d00dfeed (正确)
```

## 关键证据(mtd read.raw dump,offset 0x0-0x840)

- `0x000`: `d0 0d fe ed`(FIT magic,**正确**) + FIT 结构("Mainline Linux FIT for RK3506B (NAND boot)"、"Kernel"、"zImage, self-decompressing"、sha256 hash、"RK3506B AES board flat DT"、"Boot mainline Linux With FDT")。
- **注意修正**:`mtd read.raw boot ${addr} 0 0x840` 因 size 未按 0x800 对齐,命令层会 round 到 0x1000,读两个 data page;且没有 `.oob`,`io_op.ooblen=0`。所以 dump 中 `0x800` 的 `4d 58...` 很可能是 FIT `mkimage -E -p 0x800` 的 external data,**不能直接当 OOB 128 byte 证据**。要验证 OOB/BBM 覆盖,需 `mtd read.raw.oob` 或专门 OOB dump。

→ 目前最硬证据仍是:**raw 读 FIT header 正确,非 raw 读 FIT header 被改坏**。这足以证明问题在 U-Boot 非 raw 读路径/硬件读配置,但 OOB 覆盖证据需要重新采样确认。

## 烧录链路(供参考)

vendor RKDevTool "下载镜像": Loader=`rk3506-vendor-loader.bin`(vendor DDR+SPL+usbplug) + parameter=`parameter-nand.txt`(boot 扩 16MB @ 0xBA00) + uboot 分区=`rk3506-uboot-mainline-vendor-fit.itb`(主线 U-Boot FIT) + boot 分区=`rk3506-kernel.itb`(内核 FIT)。板子: bootrom → vendor idblock(vendor DDR+SPL) → 读 uboot 分区(我们 FIT) → 主线 U-Boot → 读 boot 分区(内核) → (应为)Linux。

## 约束

- 板名/compatible 用 **`aes`** 非 `atk`(正点原子商标版权)。
- 尽量**最小改动**(hack 要标注 `XXX: rk-forge bring-up hack`,可回滚;最终形态是 U-Boot 自写 kernel 用主线 ECC,届时去掉 hack)。
- 工具链: vendor bundled `arm-none-linux-gnueabihf-`(gcc 10.3),`third_party/vendor-sdk/prebuilts/...`。
