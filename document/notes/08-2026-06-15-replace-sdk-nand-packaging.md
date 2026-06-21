# 接力 Prompt:取代 SDK 的 NAND 打包流程 + 接入清爽 buildroot

> **给下一个 AI**。先读 [07](07-2026-06-15-milestone-mainline-linux-boots.md) + [sdk-diff](../sdk-diff.md) 接现状,再读本篇接任务。
> 本篇是"下一程"的方向交接,不是已完成记录。

## 你接手的项目现状(一句话)

主线 Linux **7.1** + 主线 U-Boot 2026.07-rc4 已在 ATK RK3506B(SPI NAND W25N04KV)boot 到**交互 shell**(busybox initramfs)。板级 patch 可复现、零 hack、版本无关(v7.0.12/v7.1 双验证)。

**但"怎么把这套东西打包成能烧进 NAND 的镜像"这条链,还重度借用 vendor SDK**——这一程就是把它换成 forge 自有、可复现、mainline-first 的流程,之后接入一个清爽 buildroot 产真 rootfs。

## 第一要务:先吃透现在的 NAND 打包流程

别急着改,先画清"一个能 boot 的 NAND 现在由哪些块组成、每块怎么产、谁的工具"。已知的拼图:

| 块 | 当前怎么来 | 工具 | 性质 |
|---|---|---|---|
| **partition 表(parameter)** | `board/aes/parameter-nand-aes.txt`(RK parameter 格式,mtdparts= uboot/misc/vnvm/recovery/boot/rootfs/userdata) | 手写 | 文本,需理解 RK 扇区单位约定 |
| **idblock / loader** | `rk3506-vendor-loader.bin` = vendor DDR(rk3506b_ddr_750MHz_v1.06.bin)+ vendor SPL + usbplug | vendor `boot_merger` | **纯 vendor blob**,写 NAND boot 区(RKDevTool "Loader" 字段) |
| **uboot 分区** | `rk3506-mainline.itb`(主线 u-boot-nodtb.bin + u-boot.dtb + vendor tee.bin) | **vendor mkimage 2017.09** `-E` | 内容是我们的,打包工具是 vendor 的 |
| **boot 分区** | `rk3506-kernel.itb`(zImage + rk3506b-aes.dtb + initramfs.cpio.gz) | **vendor mkimage 2017.09** `-E -p 0x800` | 同上 |
| **rootfs 分区** | (暂无,只有 initramfs);vendor 有 `rk3506b_update_ubi_squashfs.img`(144MB UBI+squashfs) | vendor mkupdate/afptool | 空缺 |
| **烧录** | Windows **RKDevTool** "下载镜像":Loader 字段 + 逐分区镜像 → 写 NAND 扇区 | RKDevTool(Windows) | 手动 cp 到 `/mnt/d/DownloadFromInternet/` 后人工点烧 |
| **整包 update.img** | vendor 的单一可烧镜像(含 loader + 全分区 + rootfs) | vendor `mkupdate`/`afptool`(RK firmware 打包格式) | **待逆向**:格式、怎么从 Linux 产 |

**要查清的(没现成答案,你要挖)**:
1. RK `parameter` 格式详解(扇区单位、各分区 offset/size 换算、与 mtdparts 的关系)。
2. vendor `update.img` 的二进制格式(头 + 各分区打包)——能不能从 Linux 用开源工具(rkdeveloptool / afptool 逆向版)产?
3. vendor build.sh 里打包相关的 `mk-*.sh` 钩子(见 memory `vendor-build-pipeline-for-forge`:20 个钩子,核心 4 阶段),哪些是 NAND 打包、哪些可弃。
4. `boot_merger` 怎么把 DDR+SPL+usbplug 合成 idblock——能否主线/开源替代(短期不能,DDR 是 rkbin blob)。

知识源:`third_party/vendor-sdk/`(build.sh、RKBOOT/*.ini、tools/mkimage、tools/boot_merger)、[01-vendor-uboot-build-flow](01-2026-06-14-vendor-uboot-build-flow.md)、[04-mainline-uboot-via-vendor-spl](04-2026-06-14-mainline-uboot-via-vendor-spl.md)。

## 目标态:forge 自有 NAND 打包

1. **用主线 mkimage/dtc 打 FIT**,不再借 vendor 2017 mkimage(主线 U-Boot 自带 tools/mkimage,验证字节兼容 vendor SPL 读取即可;若 vendor SPL 对 FIT 结构有特殊要求,记下来)。
2. **Linux 侧组装完整可烧 NAND 镜像**:要么产 RK `update.img`(开源 rkdeveloptool/afptool),要么直接用 `rkdeveloptool`(Linux)写板,摆脱 Windows RKDevTool + 手动 cp。
3. **脚本化、可复现**:纳入 `scripts/`(forge 已有 bash-first 约定,见 `config/toolchain.conf`、`scripts/apply-series.sh`),产物落 `board/aes/out/`。
4. **loader 近期仍借 vendor**(方案 A 自己的 SPL/DDR 是远期,见 sdk-diff "RK-SDK residue")——但**从 forge 脚本组装**(调 boot_merger 或预提取),不让人工干预。

## 之后:接入清爽 buildroot(产真 rootfs)

vendor 的 buildroot 臃肿且绑死其 SDK。目标:拉一个**最小 buildroot**(或更轻的 rootfs 生成法),产一个小 rootfs(busybox + 必要 init),打包成 **UBI/squashfs** 写 rootfs 分区 → 从 initramfs-shell 升级到**持久 rootfs**。
- 先决:NAND 打包流程已 owned(否则 rootfs 烧不进去)。
- 内核侧要补 SPI-NAND 进 DT(`rockchip,sfc` + `spi-nand` + MTD/UBI,主线驱动都在,见 sdk-diff)。
- 参照:`document/sdk-diff.md` 的"下一步优先级"。

## 约束(别破)

- **mainline-first**:工具优先主线,只在没有开源替代时才借 vendor(且文档化进 BLOBS.md)。
- **可复现**:patches + 脚本,不依赖手动 cp / Windows / 某次手敲。
- **不破坏已验证 boot 链**:每步改动后,仍能从干净源码一路 bootm 到 shell(回归基线 = note 07 的复现配方)。
- **板名 aes 非 atk**(商标)。
- **诚实**:blob 先用、文档化、目标消除(sdk-diff 已记 residue)。

## 建议第一步

别写代码。先把"vendor 怎么产一个能 boot 的 NAND"彻底拆清楚:
- 拆 vendor `rk3506b_update_ubi_squashfs.img`(afptool/unsquashfs/十六进制看头),画出"镜像 = [header][idblock][parameter][uboot 分区][boot 分区][rootfs]…"的结构图。
- 对照 vendor build.sh 的打包阶段,标注每块"vendor 工具 / 我们的输入 / 可替代性"。
- 产出一份"现状打包流程"笔记(补本篇上面的表),再设计 forge 替代。

## 关键文件 / 知识指针

- 现状交接:[07](07-2026-06-15-milestone-mainline-linux-boots.md)、[sdk-diff](../sdk-diff.md)
- 打包配方:`board/aes/fit/{rk3506-mainline.its, rk3506-kernel.its}`、`board/aes/parameter-nand-aes.txt`、`board/aes/initramfs/README.md`
- vendor 流程:[01](01-2026-06-14-vendor-uboot-build-flow.md)、[04](04-2026-06-14-mainline-uboot-via-vendor-spl.md)、`third_party/vendor-sdk/build.sh` + `mk-*.sh`、`tools/{mkimage,boot_merger}`
- rkbin blob:`third_party/explore/rkbin/bin/rk35/`(DDR/TEE)
- memory:`vendor-build-pipeline-for-forge`、`vendor-sdk-atk-bsp`、`uboot-build-flash-commands`、`kernel-port-state`、`sfc-read-corruption-rootcause`
- 工具链:`config/toolchain.conf`(vendor gcc 10.3);脚本约定见 `scripts/`(bash-first,留 Python seam)

---

*一句话给接力者:主线软件栈已通;现在把"从源码到可烧 NAND 镜像"这条路也夺回主线。先理解 vendor 打包,再逐块替换,最后接 buildroot 产真 rootfs。*
