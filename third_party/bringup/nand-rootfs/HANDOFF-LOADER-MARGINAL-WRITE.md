# 交接:RK3506B SPI-NAND 写损坏 saga(loader/rkbin 边际写)

> 本文档为交接件,记录从"rw 写必崩"到定位 **rkbin loader 边际写** 的完整结论、证据、已试方案、产物,以及下一步"拆 SDK/rkbin"的方向。
> 配套:`SFC-WRITE-CORRUPTION-POSTMORTEM.md`(历程)、记忆 `sfc-dll-saga-and-writepath`。

## TL;DR(当前状态)

- ✅ **内核能 boot 了**:`multi_v7_defconfig` + 用 **XZ 压缩**(非砍代码)→ zImage 11.5MB gzip → **7.1MB**,落在出厂坏块(boot-relative 0x920000=9.2MB)之前。boot/内核这条 saga 解决。RW 写在会话内工作(echo/cat OK)。
- ❌ **rootfs 写损坏未解,根因 = rkbin loader 边际写。** reboot 时读 loader 烧的 PEB(如 PEB 30)报 ECC 不可纠(-74),UBIFS 挂。
- ❌ **换 loader 救不了**:试了 3 个 loader 全边际(见下)。loader-swap 方案死亡。

## 根因(rkbin loader 的 SPI-NAND 写不可靠)

**rkbin 的 `MiniLoaderAll.bin`(vendor loader,负责 MaskROM 烧录时写各分区)写 SPI-NAND 时,部分 erase block 写下去位不牢** → on-die ECC 回读不可纠(-EBADMSG/-74)。每次烧录随机几块中招,低 PEB(UBIFS master/journal/index 所在)常中。

- **写侧无 DLL 调谐**(类读侧同病 —— 读侧我们已用 DLL 230-cell 窗口修好;写侧在 rkbin 里改不了)。
- 写"成功"(instrumented 内核探针:`prog_fail=0 erase_fail=0 ecc_en=1`),只是位不牢。
- 不是物理坏块:`mtdbb test`(Linux erase+重写)对所有"坏块"PEB 3/4/5/27/29/30 等 → **全 CLEAN**。块本身好,是 loader 写弱。
- **3 个 loader 全边际**(关键结论,换版本无效):

| loader | md5 | 大小 | 结果 |
|---|---|---|---|
| 我们(原) | 6645685a | 276928 | PEB 3/4/5/30 边际 |
| vendor squashfs 镜像 | 91a6631e | 270784 | read 测试那次干净,v12 前误用(实际也边际) |
| vendor ubifs 镜像 | 4762d63f | 270784 | PEB 30 边际(v12) |

→ **loader 写不可靠是 rkbin 通病,与版本无关。**

## 关键证据(板上坐实)

1. **instrumented 内核探针**(`drivers/mtd/nand/spi/core.c` + `winbond.c` 加 dev_info):所有 WRITE/ERASE `ecc_en=1 prog_fail=0 erase_fail=0`,但同会话读 loader 写的 PEB → `PROBE ECC_UNCOR status=0x20`。
2. **mtdbb test**(自写工具):所有"坏块"Linux erase+重写+回读全 CLEAN;U-Boot 写 userdata 32 块 4MB 变数据 cmp 全干净(U-Boot/Linux 写可靠)。
3. **全分区 ECC 扫描**(mtdbb scan,扫两次一致):每次 loader 重刷坏块换一批(v6: 3/4/26;v7: 3/4/27/29;v8: 3/4/5/30),随机性 → 写边际非固定坏块。
4. **`/sys/class/mtd/mtd5/bad_blocks=0`**:UBI 不标坏(写"成功"无写后校验)。

## 已澄清的误判(别再踩)

- ~~"Linux 写 corrupt"~~:误判。坏数据一直是 loader 存量,Linux/U-Boot 写从没坏。
- ~~"物理坏块"~~:误判。mtdbb 证全可重写干净。
- ~~"retention 衰减"~~:未被排除但非主因(块每次随机变 = 写时边际,固定物理块才像 retention)。
- **boot 0x920000 是出厂坏块**(PBA 10300, loader 日志 `spare=ffbf skip0`),loader 正确跳过,**不是写毛**。
- `ARM_ATAG_DTB_COMPAT` 依赖 `ARM_APPENDED_DTB`(我们 U-Boot 传 DTB 不走这路)—— 红鲱鱼。

## 已试方案(别重复)

| 方案 | 结果 |
|---|---|
| 换 loader(3 个) | 全边际 ❌ |
| 标坏块+重刷(MEMSETBADBLOCK) | loader 每刷造新坏块,治标不治本 ❌ |
| sync+remount,ro+reboot | 仍崩(remount,ro 本身 rewrite 元数据) ❌ |
| vendor defconfig(alientek_rk3506)直接套主线 | data abort 启动崩(6.1→7.1 不兼容,ATAG/VMSPLIT 都不是) ❌ |
| 砍 multi_v7 子系统(DRM/MEDIA/ext4/NFS…) | EXT4/NFS/PERF 被 select 顶不住,只省 0.5MB ❌ |
| **XZ 压缩 multi_v7(不砍代码)** | **✅ zImage 7.1MB,内核能 boot**(唯一内核侧成功的) |
| lean/vendor config debug | VMSPLIT_3G、ATAG 都不是崩因,隐蔽,搁置 |

## 产物(都在仓库)

- **工具**(静态 armhf,进 rootfs,`scripts/mk-rootfs.sh` 编):
  - `third_party/bringup/rootfs/mtdrawdump.c` — MEMREAD raw/no-ECC dump。
  - `third_party/bringup/rootfs/mtdbb.c` — `scan`/`test`(erase+写+回读)/`mark`/`isbad`/`erase`。
- **内核配置片段**(`boards/rk3506-evb/`):
  - `kernel.config`(板级)、`kernel-trim.config`(砍 DRM/MEDIA… 部分生效)、`kernel-compress.config`(**XZ,关键**)、`kernel-leanfix.config`(搁置)。
- **探针补丁**(未 commit):`drivers/mtd/nand/spi/core.c`(WRITE/ERASE dev_info)+ `winbond.c`(ECC_UNCOR)。诊断完可拆。
- **loader 文件**:`third_party/bringup/vendor-loader-fromSDK.bin`(当前=4762d6)。
- **镜像**:`/mnt/d/DownloadFromInternet/update-nand-ubifsloader-v12.img`(4762d6 + XZ 内核 + rootfs)。
- **vendor 参考镜像**:`third_party/rk3506b_update_ubi_ubifs.img`(RW,#41)、`..._squashfs.img`(RO,#21)。

## 重建命令速查

```bash
# 内核(XZ multi_v7,7.1MB,能 boot)
cd third_party/explore/linux
TC=.../arm-none-linux-gnueabihf-
scripts/kconfig/merge_config.sh -m -O . arch/arm/configs/multi_v7_defconfig \
  $FORGE/boards/rk3506-evb/kernel.config \
  $FORGE/boards/rk3506-evb/kernel-trim.config \
  $FORGE/boards/rk3506-evb/kernel-compress.config
make ARCH=arm CROSS_COMPILE=$TC olddefconfig
make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) zImage rockchip/rk3506b-aes.dtb
# 打包
cd $FORGE && scripts/pack-fit.sh && scripts/assemble-update.sh --nand --loader third_party/bringup/vendor-loader-fromSDK.bin
```

## 下一步方向(用户定:拆 SDK / rkbin)

**核心怀疑:rkbin loader 的 SFC 写侧配置(速度/DLL/驱动强度/io-domain)有问题,导致部分块写不牢。** 拆 SDK 时重点找:

1. **loader 的 SFC 速度/DLL 配置**:rkbin 是否有可配置项(ini?DT?config byte?)能降速或开 DLL? vendor 镜像能"平稳通过"是否因 loader 跑在更稳的速度/配置?
   - 查 `third_party/vendor-sdk` 里 loader 相关:`RKBOOT-RK3506B-aes.ini`、loader 源/配置、rkbin 的 SFC 初始化。
2. **3 个 loader 的 20842 字节差异**:`cmp -l` 出来的差异段是否落在 SFC/NAND-write 代码区(而非版本串)。
3. **vendor 镜像为何"平稳通过"**:是 loader 写稳?还是 vendor 的 image(ubifs/squashfs 布局)容忍边际块(RO squashfs 不 rewrite 元数据)?**实测 vendor ubifs 镜像长期(reboot 多次)是否真稳** —— 若稳,说明 loader/布局有窍门;若也偶崩,则都是 rkbin 通病。
4. **io-domain / 驱动强度**:forge 的 io-domain 配置(见记忆 `vendor-build-pipeline-for-forge`,io-domains 是真贡献点)是否影响 SFC 写信号?对照 vendor SDK 的 io-domain/grf 设置。
5. **rkbin 版本**:是否有更新版 rkbin 修了写?当前 DDR v1.06、loader 各异。

## 兜底方案(若 rkbin 拆不出所以然)

**B 方案:loader 只搬运,我们的栈写 rootfs。** U-Boot 100MHz 写已证可靠(32 块 cmp 干净)。需:
1. rootfs.ubi.img 塞进 boot FIT(data 节点,FIT sha256 验完整性);
2. U-Boot DT 补全分区表(现只认 boot);bootcmd 改直接 `mtd read boot + bootm`;
3. U-Boot bootcmd:读 FIT → `mtd erase rootfs` → `mtd write rootfs`(可靠)→ boot kernel。
4. boot 分区可能要扩(塞镜像)或 FIT 放别处。
复杂但确定有效(我们的栈写可靠已板上证明)。

## 待澄清

- **retention**:Linux/U-Boot 的强写是否长期不衰?(未做时间测试)—— 若衰,则即便 B 也要 markbad 衰减块。
- **vendor 自家镜像长期可靠性**:用户说"平稳通过",但没多轮 reboot stress 数据。

## 指针

- 记忆:`sfc-dll-saga-and-writepath`(全程)、`MEMORY.md` 索引。
- POSTMORTEM:`SFC-WRITE-CORRUPTION-POSTMORTEM.md`(调查历程 + 坑)。
- 日志:`third_party/logs/boot-sdl-*.txt`(各轮)。
