# sdk-diff — RK3506B: vendor BSP vs 主线移植(诚实差距报告)

> rk-forge 的"诚实证明器"。逐子系统对比 ATK vendor BSP(`third_party/vendor-sdk/`,linux 6.1.118)与我们主线移植(linux 7.0.12 + U-Boot 2026.07-rc4)的差距。**不美化、不隐藏**:说清 BSP 有什么、主线有没有、差什么、还能不能 boot。
> 最新状态以 [07-...-milestone-mainline-linux-boots.md](notes/07-2026-06-15-milestone-mainline-linux-boots.md) 为准。本表随 bringup 推进更新。

## 一句话结论

**主线 Linux 7.0.12 在 RK3506B 启动到 userspace handoff——但只覆盖 CPU 核心子系统;所有外设(mmc/nand/eth/usb/...)都还没进主线 DT。** 外设驱动主线**都有**,差的只是"接线"(DT 节点 + config + bringup),不是"写驱动"。启动链仍**借 vendor SPL/DDR/TEE blob**(方案 B),非纯主线 boot。

## "RK-SDK residue" 残留度量(PLAN 核心论点)

PLAN 论点:**"取代 RK-SDK 的 build.sh,不是取代整个 RK-SDK"**。诚实地量一下主线 boot 还残留多少 vendor 东西:

| 残留项 | 性质 | 能否消除 |
|---|---|---|
| vendor idblock(DDR v1.06 + SPL + usbplug) | 闭源 blob + vendor SPL 代码 | **方案 A 未成**(自己的 SPL 在 DDR 后崩,见 notes/02、04)。纯主线 boot 的硬阻塞 |
| vendor `tee.bin`(OP-TEE v2.10) | 闭源 blob | rkbin 提供;可换主线 TF-A/OP-TEE,工作量大 |
| board DT(rk3506.dtsi/rk3506b-aes.dts) | **我们写的**,非残留 | rk-forge 的贡献点(上游化目标) |
| SFC 50MHz cap | 主线 `rockchip_sfc.c` 无 DLL 调谐的 workaround | 移植 vendor `rockchip_sfc_delay_lines_tuning` 即可消除 |
| spinand core.c hack | — | **已消除**(验证不需要,见 notes/07) |

→ 残留 = **vendor SPL/DDR/TEE blob + SFC 50MHz 临时 cap**。论点**部分成立**:build 已换主线(U-Boot+kernel 全主线源码 + patch),但启动前段(DDR/secure)仍离不开 vendor blob。这是 RK 平台的硬现实(rkbin)。

## 子系统逐项对比

图例:✅ 工作并验证 · ⚠️ 驱动在主线但未接进我们 DT · ❌ 主线缺/未做 · 🟡 借 vendor blob

| 子系统 | vendor BSP(6.1.118) | 主线移植(7.0.12) | 差距 / 闭合路径 |
|---|---|---|---|
| **CPU 核心(A7×3 SMP)** | ✅ | ✅ 3 核起来 | 无 |
| **clk / reset** | ✅ vendor clk | ✅ 主线 `clk-rk3506`/`rst-rk3506`(6.19+) | 无 |
| **pinctrl / GPIO** | ✅ | ✅ 5 bank probe | 无 |
| **UART console(uart0@ff0a0000)** | ✅ | ✅ ttyS0 1500000 | 无 |
| **PSCI / SMP boot** | 🟡 vendor OP-TEE | 🟡 同一颗 tee.bin | blob 残留(见上) |
| **GIC / timer / iommu** | ✅ | ✅ | 无 |
| **OTP(cpuid)** | ✅ | ✅ ff4f0000 已加(notes/04 阶段6) | 无 |
| **MMC / SD(dw_mmc)** | ✅ `MMC_DW_ROCKCHIP=y` | ⚠️ 驱动主线有,**DT 无节点** | +DT `&sdmmc`/`&sdhci` + config + io-domain |
| **SPI NAND(W25N04KV)** | ✅ vendor 私有 `sfc_nand` | ⚠️ 主线 `spi-nand`+`rockchip-sfc` 有,**内核 DT 无 sfc 节点** | +内核 sfc DT + MTD_SPI_NAND + 移植 DLL 调谐拿全速 |
| **Ethernet(STMMAC/dwmac)** | ✅ `STMMAC_ETH=m` + `rk3506-ethernet.config` | ⚠️ 驱动主线有,**DT 无节点** | +DT `&gmac` + phy + config |
| **USB(DWC2 host/otg/peripheral)** | ✅ `USB_DWC2=m` + 3 fragment | ⚠️ 驱动主线有,**DT 无节点** | +DT `&usb` + config |
| **Display(DRM)** | ✅ `rk3506-display.config` | ⚠️ 主线 DRM rockchip | +DT + config(非 bringup 必需) |
| **CAN** | ✅ `rk3506-can.config` | ⚠️ | +DT + config |
| **WiFi/BT** | ✅ `rk3506-wifibt.config` | ❌ | 产品特性,后置 |
| **4G/5G** | ✅ `rk3506-4g_5g.config` | ❌ | 产品特性,后置 |
| **AMP(非对称多核)** | ✅ `rk3506-amp.config` | ❌ | RK 私有特性,主线无 |

## 能否 boot?——分能力回答

- **主线 Linux 启动到 UART / userspace handoff**:✅ **能**(硬里程碑已达成)。CPU 核心 + console 全主线。
- **主线挂载 rootfs / 进 shell**:❌ **暂不能**。无 `root=`(没配 rootfs);且 mmc/nand 都没进内核 DT,无块设备可挂。下一步:最小 initramfs(ramdisk,不依赖块设备)即可拿 shell。
- **主线产品级(外设全可用)**:❌ **不能**。mmc/nand/eth/usb 都要逐个接 DT + bringup。但**全是接线活,无驱动原创**——主线驱动都在。

## 主线 vs vendor 的"真差距"在哪

1. **启动前段(DDR/secure)**:主线没法自己 init RK3506 DDR → 借 vendor blob。这是最大的"非主线"成分。
2. **板级外设接线**:主线 DT 只有最小 earlycon 集;vendor 有完整产品 DT。差的是 DT 节点 + 各自的 bringup(时钟/电源/io-domain/phy 调通)。
3. **SFC DLL 调谐**:主线 `rockchip_sfc.c` 缺采样延迟线调谐(50MHz cap 的根因)。vendor 有。一行 DT cap 是临时,移植调谐是正解。

## 下一步优先级建议

1. **initramfs 拿 shell**(快,不依赖外设)→ 验证 userspace + 给后续 bringup 一个可交互环境。
2. **SPI NAND 进内核 DT**(+MTD+UBI)→ 能挂 NAND rootfs(板子本就从 NAND 起,最自然)。
3. **MMC/SD 进 DT** → 可挂 SD 卡 rootfs(比 NAND 简单,rootfs 镜像好换)。
4. Ethernet / USB → 联网 / 外设,产品化方向。
5. 移植 SFC DLL 调谐 → 消除 50MHz 临时 cap。
6. (远期)方案 A:自己的 SPL/DDR → 消除 vendor blob 残留。

## 证据

- 主线 boot 日志:`third_party/logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt`(SMP/pinctrl/uart 起,外设未 probe)
- vendor defconfig:`third_party/vendor-sdk/kernel-6.1/arch/arm/configs/rk3506_defconfig` + `rk3506-*.config` fragments
- 主线 DT/patch:`patches/linux_mainline/0001-...patch`、主线 `kernel.config` fragment
