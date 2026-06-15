# 2026-06-15 ✅ 里程碑:主线 Linux 在 RK3506B 从 SPI NAND 启动到 UART

> **进入仓库/接手时先读这篇。** 自包含,记录"主线 Linux 7.0.12 在 ATK RK3506B 跑起来"的完整成功态 + 最小复现路径。
> 承接 [02](02-2026-06-14-mainline-bringup-handoff.md)(U-Boot 移植)→ [04](04-2026-06-14-mainline-uboot-via-vendor-spl.md)(方案 B prompt)→ [05](05-2026-06-15-nand-boot-bbm-ecc-debug.md)/[06](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md)(NAND corrupt 排查,**已解决,见下**)。
> 定型成功日志:`third_party/logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt`。

## TL;DR

**主线 Linux 7.0.12 在 ATK RK3506B(SPI NAND W25N04KV, Cortex-A7×3)从 SPI NAND 经主线 U-Boot 启动,跑到 userspace handoff**(SMP 3 核、pinctrl 5 GPIO bank、earlycon 全起来;唯一"卡点"是预期的 `Unable to mount root fs` panic——没配 root=,不是 bug)。这是 PLAN §5 的硬里程碑。

**干净态 = 只有板级 DT + defconfig,零 hack**。两个曾经的 spinand hack(isbad return false / prepare 总关 ECC)已验证**不需要**、已回退。真正的修复是 DT 里 `spi-max-frequency` 从 80MHz 降到 50MHz 一行。

## 启动链(端到端)

```
bootrom → vendor idblock(vendor DDR v1.06 + SPL + usbplug)
       → vendor SPL 读 uboot 分区(我们的主线 U-Boot FIT, vendor FIT 结构)
       → OP-TEE NS 跳转 → 主线 U-Boot 2026.07-rc4(交互 prompt)
       → mtd read boot 读 kernel FIT(主线 zImage + rk3506b-aes.dtb)
       → bootm → 主线 Linux 7.0.12(到 prepare_namespace → panic: 无 root)
```

## 拿到这里的 4 个关键点(都是已解决的)

1. **SFC 读 corrupt → DT `spi-max-frequency` 80→50MHz**。根因:主线 `rockchip_sfc.c` **从不写 `SFC_DLL_CTRL0`**(无采样延迟线调谐),vendor 驱动会调 DLL 或降到 ≤50MHz;80MHz 裸奔 → 非确定性 bit 错 + latch-up(全 0xee)。详见 [nand-ecc-debug-handoff.md](nand-ecc-debug-handoff.md) 的排查(但那篇结论"卡 ECC"是**错的**,真因是 SFC 时钟,见 [06](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md) 之后)。
2. **bootm 地址自覆盖 → FIT 暂存 `0x04000000`**(避开 kernel load `0x02080000`)。`mtd read boot 0x04000000 0 0xc00000; bootm 0x04000000`。
3. **console "卡 ttyS0" → bootargs 带 `console=ttyS0,1500000`**(带波特)。handoff 干净通过,无需 keep_bootcon / 改 uart clock。
4. **两个 spinand hack 已回退、验证不需要**:`mtd bad boot`=空(零坏块,证明之前"55% bad"是 80MHz 把 OOB 读坏的假象)+ 正常 ECC `mtd read` 读对 + Linux 全程引导。无 hack 版 U-Boot FIT uboot hash = `ccfc329856...`。

## 最小复现配方(给下一个 AI / 新会话)

**前置**:`source scripts/env-setup.sh`(toolchain.conf 已指向 vendor gcc 10.3);`third_party/explore/{uboot,linux,rkbin}` + `third_party/vendor-sdk` 在位。

**0. 应用 patches 到干净上游**:
```bash
cd third_party/explore/uboot && git checkout 5ca1a73c && git am ../../patches/uboot/*.patch   # 2026.07-rc4
cd third_party/explore/linux && git checkout v7.0.12 && git am ../../patches/linux_mainline/*.patch
```
(两 patch 均已验证可干净复现:uboot rebuild 与参考 binary 仅差构建时间戳串;linux dtb 字节一致。)

**1. 编 U-Boot + 打 FIT + 拷 Windows**(命令同 [05](05-2026-06-15-nand-boot-bbm-ecc-debug.md) §64-75):
```bash
cd third_party/explore/uboot
TC=third_party/vendor-sdk/prebuilts/gcc/linux-x86/arm/gcc-arm-10.3-2021.07-x86_64-arm-none-linux-gnueabihf/bin/arm-none-linux-gnueabihf-
RK=third_party/explore/rkbin/bin/rk35
make ARCH=arm CROSS_COMPILE=$TC -j$(nproc) ROCKCHIP_TPL=$RK/rk3506b_ddr_750MHz_v1.06.bin TEE=$RK/rk3506_tee_v2.40.bin
cp u-boot-nodtb.bin u-boot.dtb third_party/bringup/fit/
(cd third_party/bringup/fit && ../../vendor-sdk/u-boot/tools/mkimage -f rk3506-mainline.its -E rk3506-mainline.itb)
cp third_party/bringup/fit/rk3506-mainline.itb /mnt/d/DownloadFromInternet/rk3506-uboot-mainline-vendor-fit.itb
```
(kernel FIT `rk3506-kernel.itb` 已在 bringup/fit/ 和 Windows 侧,复用即可。)

**2. RKDevTool 烧板**(下载镜像模式):Loader=`rk3506-vendor-loader.bin` + uboot 分区=`rk3506-uboot-mainline-vendor-fit.itb` + boot 分区=`rk3506-kernel.itb`。

**3. 上电,prompt 上跑**:
```
=> mtd read boot 0x04000000 0 0xc00000
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> bootm 0x04000000
```
→ 应见 `Starting kernel ...` → `Linux version 7.0.12` → SMP/pinctrl → ttyS0 注册 → panic(无 root,预期)。

## 踩坑清单(别再走这些死胡同)

- ❌ **on-die ECC 是 corrupt 根因**——已证伪(prepare 关 ECC 后仍 corrupt;50MHz 才是真因)。
- ❌ **vendor/主线框架失配**——已证伪(主线自写自读 round-trip 也 corrupt)。
- ❌ **DMA / continuous read / rdesc_ecc**——都不是。
- ❌ **isbad 的"55% bad"是 vendor OOB 语义失配**——错,是 80MHz 把 OOB 读坏。
- 完整弯路见 [sfc-read-corruption-rootcause memory](../../) + [05](05-2026-06-15-nand-boot-bbm-ecc-debug.md)/[06](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md)/[handoff](nand-ecc-debug-handoff.md)(这几篇的"未解决"结论均已过时,以本篇为准)。

## 当前边界 / 下一步

- **panic `Unable to mount root fs`** = 没给 `root=`(预期)。要 shell:做最小 initramfs(busybox + /init)塞 kernel FIT 当 ramdisk 节点。板子暂无 mmc(SD)/net(eth),只能从 NAND 起或 initramfs。
- **还没进内核 DT/config 的外设**(诚实差距,= sdk-diff 的料):mmc、spi-nand、ethernet、usb。内核侧只有 CPU 核心子系统(CPU/timer/pinctrl/gpio/uart/psci/smp/iommu/clk)起来。
- **里程碑另一半**(PLAN §5 退出标准第二项):写诚实的 sdk-diff 差距报告(主线 vs 我们 / 还差什么 / 能否 boot)。
- 可选打磨:从 vendor 移植 `rockchip_sfc_delay_lines_tuning` 到主线 rockchip_sfc.c 拿回全速(50MHz 够 bringup)。

## 关键文件

- patches: `patches/uboot/0001-...patch`、`patches/linux_mainline/0001-...patch`(均含 series)
- FIT 打包配方: `third_party/bringup/fit/rk3506-mainline.its`、`rk3506-kernel.its`
- 定型日志: `third_party/logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt`
- memory: `kernel-port-state`、`sfc-read-corruption-rootcause`、`mainline-uboot-bringup-state`、`uboot-build-flash-commands`
