# sdk-diff — RK3506B: vendor BSP vs 主线移植(诚实差距报告)

> rk-forge 的"诚实证明器"。逐子系统对比 ATK vendor BSP(`third_party/vendor-sdk/`,linux 6.1.118)
> 与我们主线移植(linux 7.1 + U-Boot 2026.07-rc4)的差距。**不美化、不隐藏**:说清 BSP 有什么、
> 主线有没有、差什么、还能不能 boot。本文随 bringup 推进持续更新。
>
> **2026-06-17 状态**:主线 7.1 + 主线 U-Boot 从 NAND 启动到 busybox 交互 shell,UBIFS rootfs
> 跨冷重启 RW 持久。最新里程碑见 [pitfalls/04(RW saga)](pitfalls/04-sfc-nand-saga.md) 与
> [notes/11](notes/11-2026-06-16-patch-verification-rw-rootfs.md)、[notes/12](notes/12-2026-06-17-kill-vendor-sdk-assessment.md)。

## 一句话结论

**主线 Linux 7.1 + 主线 U-Boot 在 RK3506B 从 NAND 启动到 busybox 交互 shell,UBIFS rootfs 跨冷
重启 RW 持久——CPU 核心 + console + SPI-NAND 全主线打通。** 剩下的外设(mmc/eth/usb/display/can)
主线驱动**都有**,差的只是"接线"(DT 节点 + config + bringup),不是写驱动。启动链前段仍**借 vendor
blob**(DDR/SPL/tee,方案 A 未成),非纯主线 boot。

## "RK-SDK residue" 残留度量(PLAN 核心论点)

PLAN 论点:**"取代 RK-SDK 的 build.sh,不是取代整个 RK-SDK"**。诚实量一下主线 boot 还残留多少
vendor 东西:

| 残留项 | 性质 | 状态 |
|---|---|---|
| vendor idblock(DDR v1.06 + SPL + usbplug) | 闭源 blob + vendor SPL 代码 | **方案 A 未成**(自己的 SPL 在 DDR 后崩,见 [notes/02](notes/02-2026-06-14-mainline-bringup-handoff.md)、[notes/04](notes/04-2026-06-14-mainline-uboot-via-vendor-spl.md))。纯主线 boot 的硬阻塞 |
| vendor `tee.bin`(OP-TEE v2.10) | 闭源 blob | rkbin SPL verified boot 锁的 hash,必须 v2.10(见 [pitfalls/01](pitfalls/01-rkbin-spl-contracts.md) 坑 #2) |
| vendor mkimage 2017.09 | rkbin SPL 的 FIT 布局税 | 打 uboot FIT 必须用它(主线 mkimage 的 -E 布局 SPL 不认,见 [pitfalls/01](pitfalls/01-rkbin-spl-contracts.md) 坑 #3) |
| board DT(rk3506.dtsi / rk3506b-aes.dts) | **我们写的**,非残留 | rk-forge 的贡献点(上游化目标) |
| ~~SFC 50MHz cap~~ | ~~主线 sfc 无 DLL 调谐的 workaround~~ | **已消除**:移植 vendor DLL 调谐,扫出 230-cell 采样窗(见 [pitfalls/04](pitfalls/04-sfc-nand-saga.md) 坑 #5) |
| ~~spinand core.c hack~~ | — | **已消除** |

→ 残留 = **vendor SPL/DDR/TEE blob + vendor mkimage 税**。论点**基本成立**:build 全换主线
(U-Boot + kernel 全主线源码 + patch,[notes/11](notes/11-2026-06-16-patch-verification-rw-rootfs.md) 干净
上游逐字节验证过),但启动前段(DDR/secure)仍离不开 vendor blob——RK 平台的硬现实(rkbin)。

## 子系统逐项对比

图例:✅ 工作并验证 · ⚠️ 驱动在主线但未接进我们 DT · ❌ 主线缺/未做 · 🟡 借 vendor blob

| 子系统 | vendor BSP(6.1.118) | 主线移植(7.1) | 差距 / 闭合路径 |
|---|---|---|---|
| **CPU 核心(A7×3 SMP)** | ✅ | ✅ 3 核起来 | 无 |
| **clk / reset** | ✅ vendor clk | ✅ 主线 clk-rk3506 / rst-rk3506 | 无 |
| **pinctrl / GPIO** | ✅ | ✅ 5 bank probe | 无 |
| **UART console(uart0@ff0a0000)** | ✅ | ✅ ttyS0 1500000 | 无 |
| **PSCI / SMP boot** | 🟡 vendor OP-TEE | 🟡 同一颗 tee v2.10 | blob 残留 |
| **GIC / timer / iommu** | ✅ | ✅ | 无 |
| **OTP(cpuid)** | ✅ | ✅ ff4f0000 | 无 |
| **SPI NAND(W25N04KV) + SFC** | ✅ vendor 私有 sfc_nand | ✅ **主线 spi-nand + rockchip-sfc,DLL 调谐已移植,RW 通** | 已闭合([pitfalls/04](pitfalls/04-sfc-nand-saga.md));写侧加 powergood + WPEN |
| **UBIFS rootfs(busybox)** | ✅ | ✅ **RW 跨冷重启持久** | 已闭合(Linux 落盘 + 页级恢复,[pitfalls/04](pitfalls/04-sfc-nand-saga.md) 坑 #12) |
| **MMC / SD(dw_mmc)** | ✅ MMC_DW_ROCKCHIP | ⚠️ 驱动主线有,**DT 无节点** | +DT `&sdmmc`/`&sdhci` + config + io-domain(P3) |
| **Ethernet(STMMAC/dwmac)** | ✅ STMMAC_ETH + rk3506-ethernet.config | ⚠️ 驱动主线有,**DT 无节点** | +DT `&gmac` + phy + config(P3) |
| **USB(DWC2 host/otg)** | ✅ USB_DWC2 + fragment | ⚠️ 驱动主线有,**DT 无节点** | +DT `&usb` + config(P3) |
| **Display(DRM)** | ✅ rk3506-display.config | ⚠️ 主线 DRM rockchip | +DT + config(非 bringup 必需) |
| **CAN** | ✅ rk3506-can.config | ⚠️ | +DT + config |
| **WiFi/BT · 4G/5G · AMP** | ✅ | ❌ | 产品特性 / RK 私有,主线无或后置 |

## 能否 boot?——分能力回答

- **主线启动到 UART / userspace handoff**:✅ **能**。CPU 核心 + console 全主线。
- **主线挂 RW rootfs + 进 shell**:✅ **能**(已达成)。UBIFS rootfs 跨冷重启持久,`/persist.log` 三轮 stress 全在。这条从"暂不能"到"能",是 [pitfalls/04 saga](pitfalls/04-sfc-nand-saga.md) 啃下来的。
- **主线产品级(外设全可用)**:❌ **还不能**。mmc/eth/usb 都要逐个接 DT + bringup(P3)。但**全是接线活,无驱动原创**——主线驱动都在。

## 主线 vs vendor 的"真差距"在哪

1. **启动前段(DDR/secure)**:主线没法自己 init RK3506 DDR → 借 vendor blob。最大的"非主线"成分,方案 A(自己 SPL)未成。
2. **板级外设接线**:主线 DT 现在覆盖了核心 + SPI-NAND;mmc/eth/usb/display/can 还没接(P3)。差的是 DT 节点 + 各自 bringup(时钟 / 电源 / io-domain / phy)。
3. **vendor mkimage 税**:uboot FIT 必须用 vendor 2017.09 mkimage 打(rkbin SPL 的 -E 布局),kernel FIT 才能用主线 mkimage。是 rkbin SPL 的隐性税。

## 下一步优先级

1. **RW 加固**:多轮 stress 确认 PEB 3/4 不衰减;ubiprog/init 固化进 patch;powergood 非致命→致命([pitfalls/04](pitfalls/04-sfc-nand-saga.md) 待办)。
2. **P3 外设 DT**:MMC/SD → Ethernet → USB,逐个接 DT + 板验(主线驱动都在,接线活)。
3. **P1 源码层零 vendor-sdk**:rkbin→公开仓 submodule + toolchain→bootlin + busybox→upstream([notes/12](notes/12-2026-06-17-kill-vendor-sdk-assessment.md))。
4. **(远期)方案 A**:自己的 SPL/DDR → 消除 vendor blob 残留。

## 证据

- 主线 boot 日志:[boot-sdl-stage-end-of-kernel-uboot-202606151100](logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt)(SMP/pinctrl/uart 起,外设未 probe)
- RW 达成日志:[boot-sdl-202606162254](logs/boot-sdl-202606162254.txt)(recovery ×2,`/persist.log` c1/c2/c3)、[boot-sdl-202606162310](logs/boot-sdl-202606162310.txt)(页级恢复)
- vendor defconfig:`third_party/vendor-sdk/kernel-6.1/arch/arm/configs/rk3506_defconfig` + `rk3506-*.config` fragments
- 主线 patch:`patches/linux_mainline/`、`patches/uboot/`(干净上游逐字节相同,见 [notes/11](notes/11-2026-06-16-patch-verification-rw-rootfs.md))
