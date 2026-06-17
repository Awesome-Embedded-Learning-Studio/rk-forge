# DT 迁移:让主线 Linux 看见 SPI-NAND(对齐 vendor、主线纯)

> 承 [09](09-2026-06-15-vendor-nand-packaging-forensics.md)(NAND 打包)+ 计划 `twinkling-kindling-marble.md`。
> 目标:把"内核 + U-Boot 设备树"对齐 vendor_sdk,让主线 Linux boot 后能看见 W25N04KV SPI-NAND + MTD 分区(持久 rootfs 的头号前提)。
> **板无关 + 板门验证均通过(2026-06-15)**:Linux boot 到 `~ #`,W25N04KV 被探测、7 MTD 分区全见。证据 log `document/logs/boot-sdl-2026-06151834.txt`。

## 关键发现(反直觉但省事):vendor DT 对这块板很稀疏

实地查 vendor SDK 的板级 DT include 链(`rk3506b-alientek-mipi720x1280-nand-ubi-squashfs.dts` → `rk3506b-alientek.dtsi` + `rk3506-alientek-mipi720x1280.dtsi` → SoC `rk3502.dtsi`)发现,"对齐 vendor"能对齐的不多:

| 项 | vendor DT 里有没有 | 我们怎么处理 |
|---|---|---|
| **io-domains** | **没有** —— vendor 不通过 DT 建模(无 binding、无 vccio 属性,exhaustive grep 确认) | 不做(vendor 也没;非 boot 拦路,loader 配 IO 电压)。之前 memory 说的"io-domains 是贡献点"实为 vendor-SDK build 的一个 warning,不是 vendor 提供 |
| **PMIC(rk801/rk816)** | **alientek 板不用** —— 全 fixed regulator(i2c0/1 启用但无子设备) | 不加 PMIC |
| **MTD 分区** | **没有** —— vendor 用 `parameter.txt` + cmdline(`ubi.mtd=5 ubi.block=0,rootfs root=/dev/ubiblock0_0 rootfstype=squashfs`) | DT fixed-partitions(对齐自己的 `parameter-nand-aes.txt`,比 cmdline 自描述) |
| **SPI 控制器** | vendor 用 `fspi`/`rockchip,rk3506-fspi`(vendor FSPI 驱动,80MHz + DLL 调谐),**且 alientek 内核侧压根没启用**(NAND 全靠 U-Boot) | 用主线 `rockchip,sfc`(rk-forge 给 U-Boot 写的、已验证读 NAND 的节点),有意背离 |

→ 迁移的真身 = **补上 vendor 省略掉的主线板级 DT**,复用 rk-forge 已验证的主线 sfc 节点 + 主线 binding。

## 做了什么

**Linux DT**(`patches/linux_mainline/0002-...patch`):
- `rk3506.dtsi` 加 `sfc: spi@ff488000`(主线 `rockchip,sfc` binding + `rockchip,sfc-no-dma` + clocks SCLK_FSPI/HCLK_FSPI)。
- `rk3506b-aes.dts` 启用 `&sfc` + `flash@0`(compatible=spi-nand=W25N04KV,50MHz,rx4) + fixed-partitions(uboot/misc/vnvm/recovery/boot/rootfs/userdata,对齐 parameter,128KB 擦除块对齐,0–4MB loader 区留空)。

**内核 config**(`boards/rk3506-evb/kernel.config`):+`CONFIG_SPI_ROCKCHIP_SFC=y` +`CONFIG_MTD_SPI_NAND=y`(UBI/UBIFS/squashfs/MTD_BLOCK/MTD_OF_PARTS 主线 multi_v7 已带)。

**`scripts/build-linux.sh`**:12 行 stub → 真 merge_config 流程(merge_config multi_v7 + kernel.config → olddefconfig → zImage + dtb,带 `--just-dtb` 快检)。

**驱动核实**:W25N04KV 主线 `drivers/mtd/nand/spi/winbond.c` 已支持(id `(0xaa,0x23)`,4Gb);`rockchip,sfc-no-dma` 主线驱动 `spi-rockchip-sfc.c:658` honor。无新驱动代码。

## 有意背离 vendor(记这里,可改)

- **主线 `rockchip,sfc`@50MHz vs vendor `fspi`@80MHz**。主线 `rockchip_sfc.c` 无采样延迟线(DLL)调谐(vendor `rockchip_sfc_delay_lines_tuning` 是私货),80MHz 下读采样 marginal → 非确定性 bit 错(见 [[sfc-read-corruption-rootcause]]),故封 50MHz。**主线纯度换 ~40% 读速**(否则得带 vendor FSPI 驱动 patch,违 mainline-first)。
- **DT fixed-partitions vs vendor cmdline/parameter**。选自描述 DT。

## U-Boot 分区:为什么不动 U-Boot DT

查清 U-Boot 现在 `mtd read boot` 的解析机制:`.config` 有 `CONFIG_MTDPARTS_DEFAULT="mtdparts=spi-nand0:16m@0x1740000(boot)"`——U-Boot 用 **mtdparts env**(只一个 "boot" 分区,16m@0x1740000,和我 Linux DT 的 boot 分区内容一致),**不用 DT 分区**。所以给 U-Boot DT 加分区会和 env 冲突(重复 "boot" → `mtd read boot` 歧义),有破坏能跑的 boot 的风险。**结论:U-Boot DT 不动**,两侧内容一致、机制不同(kernel DT / U-Boot env),干净。U-Boot 的 sfc 节点 rk-forge 早写好且已验证。

## 板无关验证(全过 ✅)

- `make rockchip/rk3506b-aes.dtb` 编通;`fdtget` 确认 `/spi@ff488000`(rockchip,sfc + no-dma + status okay + clocks 168/167)+ `flash@0`(spi-nand,50MHz,rx4)+ 7 个 partition(label + reg 字节级对齐 parameter)。
- merge_config + olddefconfig 后 `.config`:`SPI_ROCKCHIP_SFC=y`、`MTD_SPI_NAND=y`。
- `make zImage` 增量构建:`spi-rockchip-sfc.o` + `winbond.o` + spi-nand `core.o` 编进,zImage 出(12059136 B)。
- `pack-fit.sh` 重打 `boot.img`(主线 mkimage,13036864 B,结构 kernel+fdt+ramdisk 对)。

## 板门验证 ✅ 已通过(2026-06-15)

烧 boot 分区(Windows RKDevTool,只勾 boot + parameter 加载 16MB 表;loader/uboot 不动),上电:
```
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> mtd read boot 0x04000000 0 0x1000000
=> bootm 0x04000000
```
到 `~ #` 实测结果(log `boot-sdl-2026-06151834.txt`):
```
[0.343594] spi-nand spi0.0: Winbond SPI NAND was found.
[0.344101] 512 MiB, block size: 128 KiB, page size: 2048, OOB size: 128   # W25N04KV 全对
[0.344993] 7 fixed-partitions partitions found on MTD device spi0.0
mtd0 uboot 4M | mtd1 misc 1M | mtd2 vnvm 256K | mtd3 recovery 14M
mtd4 boot 16M | mtd5 rootfs 0xae00000(172M) | mtd6 userdata 0x12ac0000(299M)
```
→ Linux 起到 shell、sfc@50MHz PIO 读没 corrupt、NAND + 7 分区全见。**DT 迁移板上坐实**。

### 踩坑(记下来,别再犯):控制台波特率

首版 bootargs 用 `console=ttyS0`(漏波特率)→ 内核在 `ttyS0 is a 16550A`(earlycon→真控制台交接)后就**没输出**了(像卡死,实则内核在跑只是看不见)。**必须 `console=ttyS0,1500000`**(带波特率,同 [[kernel-port-state]] / initramfs README 的验证配方)。这是 RK DW 8250 控制台没 options 时波特率不对的通病,不是内核死。

## 下一程

Linux 能看见 NAND 后:**装 mtd-utils(ubinize/mkfs.ubifs)+ squashfs-tools → 造真 rootfs(busybox+/sbin/init)→ 打 ubifs → bootargs 加 `root=ubi0:rootfs ubi.mtd=<N> rootfstype=ubifs rootwait`(或 vendor 那套 squashfs-on-ubi via ubiblock)→ 写 rootfs 分区 → 持久 rootfs boot**。见 [[next-phase-nand-packaging-and-buildroot]]。

## 相关

[[next-phase-nand-packaging-and-buildroot]] [[kernel-port-state]] [[sfc-read-corruption-rootcause]] [[vendor-build-pipeline-for-forge]] [09](09-2026-06-15-vendor-nand-packaging-forensics.md) [07](07-2026-06-15-milestone-mainline-linux-boots.md)
