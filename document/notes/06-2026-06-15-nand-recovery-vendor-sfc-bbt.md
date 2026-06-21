# 2026-06-15 NAND 全擦恢复 + vendor SFC bad block 扫描笔记

> ⚠️ **本文状态:历史记录,corrupt 问题已在后续解决。** 本文结尾的"corrupt 依旧、
> 交给下一个 AI"已不成立——真因是 SFC 80MHz 无 DLL 调谐(非 ECC),已修(50MHz)。
> 主线 Linux 已启动到 UART。**以 [07-...-milestone-mainline-linux-boots.md](07-2026-06-15-milestone-mainline-linux-boots.md) 为准。**
> 保留本文仅为 vendor SFC bad-block 扫描证据 + 救砖流程参考。

> 承接 [05-...-nand-boot-bbm-ecc-debug.md](05-2026-06-15-nand-boot-bbm-ecc-debug.md)(BBM/ECC corrupt 排查)。
> 本篇: 强制 raw hack 把 NAND 搞砖后全擦恢复 + 恢复时 **vendor SPL 的 SFC bad block 扫描输出**(关键新证据)。
> 完整 corrupt 问题现状 + 给大 AI 的 prompt 见 [nand-ecc-debug-handoff.md](nand-ecc-debug-handoff.md)(已二次复核)。

## 发生了什么(本篇)

1. 强制 raw hack(`spinand_mtd_read` 开头 `ops->mode = MTD_OPS_RAW`)版烧板 → **vendor SPL 读 NAND 失败**(`NAND read offset 400000 failed -74` EBADMSG,DDR 显示 v1.04 原厂)→ 板砖。
2. **全擦 NAND(RKDevTool EraseFlash)+ 重烧稳定版**(回滚强制 raw,isbad return false + prepare 总关 ECC + sfc-no-dma)。
3. 恢复成功: DDR v1.06 + vendor SPL `#charliechen` + 主线 U-Boot 2026.07-rc4 prompt 回来。

## ⭐ 关键新证据: vendor SFC 的 bad block 扫描(全擦后首次启动)

全擦 + 重烧后,**vendor SPL/DDR init 阶段**打印了大量 `sfc_nand_check_bad_block` 行(这是 vendor BSP 的 SPI NAND 驱动在扫 bad block,主线 U-Boot 不打印这些):

```
sfc_nand_check_bad_block page=  40 ret= ffffffff spare= ffff
sfc_nand_check_bad_block page=  80 ret= ffffffff spare= ffff
...（大量 page,全 spare=ffff 即 good）
sfc_nand_check_bad_block page= 3340 ret= ffffffff spare= ffbf   ← 注意! spare=ffbf(非 ffff)
w: LBA=cd00 PBA=cd00 is bad block skip0                          ← vendor 判这个 block bad(skip)
...（继续扫描,其余全 ffff）
```

### 这个输出说明什么

1. **vendor 用 `spare`(OOB) 判 bad block**——`spare=ffff` = good,`spare=ffbf` = bad(byte 有 bit 非 1)。这印证了之前 dump 的"OOB byte 非 ff"判断,但 vendor 看的是**整 spare 字节序列**(不只 byte0-1),且 **`ffbf` 才判 bad**(byte1 的某 bit)。
2. **全擦后绝大多数 block good**(spare=ffff),只有零星 `ffbf`(`page=3340` 一个)被 vendor 判 bad skip。这和之前主线 `mtd bad` 报 71/128 bad **完全不同**——说明之前那 71 个"bad"是 **vendor 写 kernel/uboot 时 OOB 被 ECC/metadata 覆盖**导致的误判,**全擦后 OOB 恢复 ffff,真 bad block 几乎没有**。
3. **vendor 的 BBM 判定比主线宽松**: 主线 `spinand_isbad` 读 OOB byte0-1(`!= 0xff` 即 bad),vendor 读整 spare(`!= 0xffffffff...` 即 bad)。vendor 写时 OOB byte0-1 被 ECC 占,但 vendor 自己的判定看的是别的 byte(或整 spare),所以 vendor 不误判自己写的。

## 对 corrupt 问题(d00ddeed)的启示

全擦恢复后,板子回到稳定版(能 prompt + mtd list)。**corrupt 问题依旧**(isbad hack + prepare 关 ECC + sfc-no-dma 版,mtd read 仍会 d00ddeed)。但这次有了 vendor SFC 扫描的新视角:

- vendor 的 SPI NAND 驱动(`sfc_nand_*`)和主线 spinand 框架**完全不同**——vendor 是 RK 私有 SFC + 私有 NAND driver,主线是通用 spinand + ondie ECC engine。
- vendor 写 NAND 用自己的 ECC 算法(写 OOB spare),主线读走通用 spinand 框架。**两者 OOB/ECC 语义不一致**是 corrupt 的根因层级。
- 之前确认: ECC 关了(bit4=0)、PIO 也 corrupt、rdesc_ecc=rdesc(同 dirmap)。剩下最可能: **`spinand_mtd_regular_page_read`(core.c:789) 的 `spinand_cont_read_enable(true)` + `nanddev_io_for_each_block` 的 continuous 假设**——即使 W25N04KV 无 set_cont_read,regular_page_read 仍按 continuous 逻辑读(nbytes=round_up),和 vendor 写的 page 布局不匹配。

## 当前稳定版状态(全擦恢复后)

- **U-Boot**: 2026.07-rc4,md5 `5520bc46`(isbad return false + prepare 总关 ECC + sfc-no-dma,无强制 raw)。
- **能**: prompt、mtd list(spi-nand0 W25N04KV + boot 分区)。
- **不能**: mtd read 读 kernel.itb(data corrupt d00ddeed,bootm Wrong Image Type)。
- **mtd read.raw**: 读正确(d00dfeed,FIT 结构完整)。

## 下一步(交给下一个 AI)

1. **核心未解**: `mtd read`(非 raw) corrupt vs `mtd read.raw` 正确,即使 ECC 关(bit4=0)+ PIO(sfc-no-dma)+ rdesc_ecc=rdesc。
2. **重点查**: `spinand_mtd_regular_page_read`(core.c:787)的 `spinand_cont_read_enable` + `nanddev_io_for_each_block` 的 `iter.req.continuous`——读 nbytes 算法(core.c:388 `round_up` vs `pagesize`)是否导致跨页读错位。
3. **避免**: 不要再用 `spinand_read_reg_op` 做 printf(它发 GET_FEATURE 命令,打断 SFC DMA 状态,之前导致全 ee + 可能扰动 NAND CFG 把板搞砖)。
4. **vendor SFC 扫描日志**(本篇上面的 `sfc_nand_check_bad_block` 输出)是宝贵参照——vendor 怎么读 spare 判 bad,主线怎么读,对比差异。

## 关键文件

- corrupt 问题完整现状: [nand-ecc-debug-handoff.md](nand-ecc-debug-handoff.md)
- U-Boot spinand driver: `third_party/explore/uboot/drivers/mtd/nand/spi/core.c`
- 当前稳定版 U-Boot FIT: `board/aes/fit/rk3506-mainline.itb`(md5 5520bc46)
- 内核 FIT: `board/aes/fit/rk3506-kernel.itb`
- 上板日志(恢复后): 本篇上面的输出(含 vendor SFC bad block 扫描)
