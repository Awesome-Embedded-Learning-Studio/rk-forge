# SFC 写损坏调查 Postmortem(RK3506B + W25N04KV SPI-NAND)

> 结论先行:**根因是 RK vendor loader 的 SPI-NAND 写例程不可靠(写侧无 DLL 调谐,某些块写下去位不牢)。
> 不是物理坏块、不是 Linux 代码、不是 ECC 配置、不是 reboot/掉电。** Linux 写路径全程可靠。
> 修法:rootfs 由 Linux 落盘(不让 loader 写)。

本文记录从"rw 写必崩"到"定位 loader 写"的完整调查链,供后续会话/他人接手。

## 硬件 / 软件

- SoC RK3506B(Cortex-A7),板 "aes"。W25N04KV(4Gb SPI-NAND,on-die ECC)挂 SFC@0xff488000,SFC VER_5。
- 主线 Linux 7.1 + 主线 U-Boot 2026.07-rc4。UBIFS rootfs 在 UBI/mtd5(1392 PEB,PEB 128KiB)。
- 烧录:Windows RKDevTool,MaskROM 模式,vendor rkbin loader(`rk3506_spl_loader`)写各分区。
- 读路径此前已根治:主线 `rockchip_sfc` 从不写 `SFC_DLL_CTRL0` → 移植 vendor DLL 调谐(230-cell 采样窗口)→ 高速读稳。

## 症状(误判的起点)

RW UBIFS:`echo X > /file && reboot` → 下次 boot 爆 `ubi_io_read error -74 (ECC)` 在固定几个 PEB
(早期 v6: PEB 3/4/26)。**当时以为是"Linux 写把数据写坏了"。** 这是全程最大的误判。

## 调查时间线(每一步排掉一个假说)

| 实验 | 结果 | 排掉 |
|---|---|---|
| 速度 24/50/80MHz 都炸 | 写坏与速率无关 | "高频写不稳" |
| TXLV mask 5→6-bit(v6)仍炸 | mask 不是根因 | "FIFO 电平 mask 错" |
| SFC 写代码逐行比对 vendor | 完全相同 | "mainline 写代码 bug" |
| `echo>file;sync;sleep3;mount -o remount,ro /;reboot` 仍崩 | 干净 commit+关机也坏 | "unclean shutdown / commit 未收敛" |
| 同会话 `echo>/probe.txt;sync;echo3>/proc/sys/vm/drop_caches;cat` → 读回干净 | 全新数据写同会话回读 OK | "数据写路径坏" |

到这里已收窄:**崩的只在 UBIFS 元数据 PEB(每次 commit erase+rewrite),且写路径本身没问题。**

## 决定性探针(v7 instrumented 内核)

在 `drivers/mtd/nand/spi/core.c` + `winbond.c` 加 `dev_info` 探针(只挂写/擦侧,读不挂免刷屏):

- `spinand_write_page`:prepare_io_req 后**读 REG_CFG 原值**(绕缓存)确认 ECC_EN 真值;wait 后打 `PROBE WRITE peb page ecc_en cfg status prog_fail wait_ret`。
- `spinand_erase`:打 `PROBE ERASE peb status erase_fail wait_ret`。
- `winbond` `STATUS_ECC_UNCOR_ERROR` 分支:打读失败原始 status。

板上结果(`boot-sdl-202606161120.txt`):
- commit 的所有 WRITE/ERASE:**`ecc_en=1 prog_fail=0 erase_fail=0 wait_ret=0`** → 写都"成功",ECC 也开着。
- 但同会话(没 reboot)读 PEB 27 → `ECC_UNCOR status=0x20`。
- PEB 27 这次 boot **没被写过** → 是 **loader 烧进去的存量**就坏。

**第一次明确指向 loader**:坏数据是 loader 写的,不是 Linux 写的。

## mtdrawdump + mtdbb(板上取证 + 治理工具)

自写两个静态 armhf 工具(进 rootfs,`scripts/mk-rootfs.sh` 用 vendor gcc 编):

- **mtdrawdump**:MEMREAD ioctl,`-r` 无 ECC 原始读;stderr 打摘要(0xFF 占比、non-0FF 范围、ecc_stats)。
- **mtdbb**:`scan`(全分区 ECC 扫坏块)/`test`(erase+写pattern+回读比对的硬/软判定)/`mark`(MEMSETBADBLOCK)/`isbad`/`erase`。

### 全分区 ECC 扫描(扫两次完全一致,确定性)

每次 loader 重刷,坏块都是**零星几个,且每次换一批**:
- v6 镜像:PEB 3 / 4 / 26
- v7 镜像:PEB 3 / 4 / 27 / 29
- v8 镜像:PEB 3 / 4 / 5 / 30

PEB 3/4 三次都在;其余变。`/sys/class/mtd/mtd5/bad_blocks = 0`(UBI 没标坏——见下)。

PEB 27 raw 取证:连读 3 次 md5 相同(位稳定,非漂移);0xFF=64.3%、数据集中 0x0–0xc7ff、0xc800 后全 0xFF(擦除干净、无残留)。
→ 弱写(program 没写牢),不是部分擦除、不是细胞不稳。

### ★ 决定性一锤:mtdbb test(Linux erase+重写+回读)

```
mtdbb test /dev/mtd6 0x0        (PEB 1706)  → CLEAN
mtdbb test /dev/mtd5 0xa0000    (PEB 5)     → CLEAN
mtdbb test /dev/mtd5 0x3c0000   (PEB 30)    → CLEAN
mtdbb test /dev/mtd5 0x60000    (PEB 3)     → CLEAN
mtdbb test /dev/mtd5 0x80000    (PEB 4)     → CLEAN
```

**所有"坏块"在 Linux erase+重写下全部读回干净。零硬坏物理块。** 块本身全好,是 loader 把它们写坏了。

## 根因(终局 — 三个独立问题,均已板上坐实)

不是单一"loader 写不可靠",是三件事叠加(之前把出厂坏块误当 retention,纠正):

**① rootfs 写坏 = 我们挑错了 loader 版本。**
- **我们的 loader**(`bringup/out/MiniLoaderAll.bin`, md5 `6645685a`, **276928B 偏大**)写 rootfs 弱 → PEB 3/4/5 等块位不牢 → on-die ECC 回读不可纠。
- **vendor 的 loader 写可靠**:板上 read 测试 —— 用 vendor loader 烧我们的 rootfs,PEB 3/4/5(以前我们 loader 写坏的)**全干净零 -74**。三个 loader 全不同:我们 `6645685a`、vendor-squashfs `91a663`、vendor-ubifs `4762d6`(后两个都 270784,可靠)。
- UBI `bad_blocks=0`:loader 写"成功"(status 干净)只是位不牢,UBI 无写后回读校验 → 永不标坏 → 坏只在读时 -EBADMSG。
- **原 saga 的"rw 写 corrupt"是误判**:坏数据一直是 loader 存量;**Linux/U-Boot 写从没坏过**(mtd6 + 所有坏块重写全 CLEAN)。

**② boot 读不全 = 出厂坏块 + 内核太大。**
- chip `0x2060000`(boot-relative `0x920000`)是**出厂坏块**(loader 日志 `PBA=10300 spare=ffbf is bad block skip0`),loader 正确跳过它。**不是写毛、不是 retention。**
- 我们的 **zImage 11.5MB**(multi_v7 臃肿)→ boot.img 12MB,**跨过这个出厂坏块** → `mtd read boot` / bootflow 读到 0x920000 就 -74。
- vendor 的 boot.img 只有 **6MB**(内核小),整段在坏块之前,所以没事。

**③ 不 autoboot = bootcmd 没配 NAND。**
- `printenv bootcmd` = `bootflow scan -lb`,bootflow 只扫 mmc/nvme/scsi/usb/pxe/dhcp,**没 MTD bootdev** → 0 bootflows。得用直接 `mtd read boot + bootm`。

## 修法(对齐 vendor,保住 mainline 栈 — 取代 B 方案)

比"U-Boot 搬运 rootfs(B)"简单得多,直接对齐 vendor 的可靠姿势:

1. **换 loader**:`assemble-update.sh --loader` 用 vendor ubifs 镜像的 loader(`4762d6`,270784)替换我们的(`6645685a`)。→ rootfs 写可靠,RW ubifs 干净。
2. **缩内核**:精简 defconfig(multi_v7 → 只留 rk3506 要的驱动),zImage <9.2MB → boot.img 整段在出厂坏块之前。
3. **bootcmd**:改回直接 `mtd read boot ${kernel_addr_r} 0 <len>; bootm`(或给 bootflow 加 MTD bootdev)。
4. 验证:RW ubifs 干净 boot + write/reboot 持久。

loader 是固定 rkbin 依赖(黑犀牛),用可靠的 vendor 版本天经地义;rk-forge 的价值在 **mainline U-Boot + kernel + DT**,不在 loader。U-Boot 100MHz 写可靠已证(备用:若哪天要彻底脱离 loader 写,B 方案仍成立)。

## 关键坑(别再踩)

1. **"rw 写 corrupt"是误判**:坏数据是 loader 存量,不是 Linux 写的。别再往 Linux 写路径/SFC 写代码里钻。
2. **UBI 不会自动管这种块**:写"成功"+无写后校验 → `bad_blocks` 恒 0。靠 `bad_blocks` 判健康会漏。
3. **scan 要扫两次**:边际块读可能抖动;扫两次一致才确定。
4. **判硬/软坏用 erase+重写+回读**,不是 raw dump 形态(raw 形态像正常数据,误导)。
5. **dyndebug 没用**(CONFIG_DYNAMIC_DEBUG 没开):看调谐/状态用 dev_info/printf 硬编进驱动。
6. **PEB 号会随镜像变**:UBIFS LEB→PEB 映射随 rootfs 内容变,所以"坏的 PEB"每次换(除 3/4 这种 loader 一致写坏的)。别把 PEB 号当物理定位。

## 工具产物

- `third_party/bringup/rootfs/mtdrawdump.c` / `mtdbb.c`(源,随 rootfs 树重编)。
- 探针补丁(未 commit,探测代码):`drivers/mtd/nand/spi/core.c`(WRITE/ERASE)+ `winbond.c`(ECC_UNCOR)。定位完成后可留可删。
- 镜像:`update-nand-probe-v8.img`(探针内核 + rootfs 带 mtdrawdump/mtdbb)。

## 相关

记忆 `sfc-dll-saga-and-writepath`(终局根因 + 全决策)。读路径治理见同条上半段。
