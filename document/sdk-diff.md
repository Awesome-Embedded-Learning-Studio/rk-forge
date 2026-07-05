# sdk-diff — RK3506B: vendor BSP vs 主线移植(诚实差距报告)

> rk-forge 的"诚实证明器"。逐子系统对比 ATK vendor BSP(`reference/vendor-sdk/`,linux 6.1.118)
> 与我们主线移植(linux 7.1 + U-Boot 2026.07-rc4)的差距。**不美化、不隐藏**:说清 BSP 有什么、
> 主线有没有、差什么、还能不能 boot。本文随 bringup 推进持续更新。
>
> **状态(活文档)**:主线 7.1 + 主线 U-Boot 从 NAND/SD 启动到交互 shell,UBIFS rootfs 跨冷重启
> RW 持久;外设(Ethernet 双口 / SPI / MMC-SD / USB / WiFi RTL8733BU / I2C / UART2 / Audio 数字链路)
> 全部点亮、板上验证;rkbin 已切公开仓 submodule、toolchain 已切 ArmGNU 15.2、vendor-sdk 从 build 链
> 消除。最新里程碑见 [pitfalls/04(RW saga)](pitfalls/04-sfc-nand-saga.md)、[notes/13(P1 rkbin)](notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md)、[notes/20(mkimage saga)](notes/20-2026-06-19-mkimage-saga-handoff.md)。

## 一句话结论

**主线 Linux 7.1 + 主线 U-Boot 在 RK3506B 从 NAND 启动到交互 shell,UBIFS rootfs 跨冷重启 RW
持久——CPU 核心 + console + SPI-NAND + 外设(Ethernet/MMC/USB/WIFI/I2C/UART/Audio)全主线打通。**
启动链前段仍**借闭源 rkbin blob**(DDR/SPL/tee,方案 A 未成),非纯主线 boot——但 rkbin 来源已是
公开仓 submodule,vendor-sdk 不再是依赖。

## "RK-SDK residue" 残留度量(PLAN 核心论点)

PLAN 论点:**"取代 RK-SDK 的 build.sh,不是取代整个 RK-SDK"**。诚实量一下主线 boot 还残留多少
vendor 东西:

| 残留项 | 性质 | 状态 |
|---|---|---|
| idblock(DDR v1.06 + SPL v1.12 + usbplug v1.03) | 闭源 blob(rkbin) | **方案 A 未成**(自己的 SPL 在 DDR 后崩,见 [notes/02](notes/02-2026-06-14-mainline-bringup-handoff.md)、[notes/04](notes/04-2026-06-14-mainline-uboot-via-vendor-spl.md))。纯主线 boot 的硬阻塞。**来源已于 P1 切到公开 rkbin submodule**([notes/13](notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md) + [blobs.md](blobs.md)) |
| tee.bin(OP-TEE v2.40) | 闭源 blob(rkbin) | ~~方案 B 借 vendor SPL 时必须 v2.10~~;**P1 起默认链用公开 rkbin tee v2.40**(SPL v1.12,板上验证,见 [notes/13](notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md) + [blobs.md](blobs.md))。blob 仍闭源,但来源已是公开仓、不再绑 vendor-sdk |
| ~~vendor mkimage 2017.09~~ | ~~rkbin SPL 的 FIT 布局税~~ | **已消除(P4)**:[scripts/fit-pack.py](../scripts/fit-pack.py)(纯 Python)复刻 vendor SPL 认的 -E 外部布局,替代 vendor mkimage 打 uboot FIT;主线 mkimage 仅留 `-l` 校验(见 [notes/20](notes/20-2026-06-19-mkimage-saga-handoff.md)) |
| ~~vendor afptool / rkImageMaker~~ | ~~update.img 打包税~~ | **已消除(D)**:[scripts/rkfw-pack.py](../scripts/rkfw-pack.py)(纯 Python)替代 vendor afptool + rkImageMaker |
| board DT(rk3506.dtsi / rk3506b-aes.dts) | **我们写的**,非残留 | rk-forge 的贡献点(上游化目标) |
| ~~SFC 50MHz cap~~ | ~~主线 sfc 无 DLL 调谐的 workaround~~ | **已消除**:移植 vendor DLL 调谐,80MHz 读稳、cell 130 / 窗口 [90,170](见 [pitfalls/04](pitfalls/04-sfc-nand-saga.md) 坑 #5) |
| ~~spinand core.c hack~~ | — | **已消除** |

→ 残留 = **SPL/DDR/TEE blob**(均闭源 rkbin;来源已于 P1 切到公开仓 submodule,vendor-sdk 不再是
依赖。vendor mkimage 税 P4 消除、afptool/rkImageMaker 税 D 消除)。论点**基本成立**:build 全换主线
(U-Boot + kernel 全主线源码 + patch,[notes/11](notes/11-2026-06-16-patch-verification-rw-rootfs.md) 干净
上游逐字节验证过),但启动前段(DDR/secure)仍离不开闭源 rkbin blob——RK 平台的硬现实。

## 子系统逐项对比

图例:✅ 工作并验证 · ⚠️ 驱动在主线但未接进我们 DT · ❌ 主线缺/未做 · 🟡 借闭源 blob

| 子系统 | vendor BSP(6.1.118) | 主线移植(7.1) | 差距 / 闭合路径 |
|---|---|---|---|
| **CPU 核心(A7×3 SMP)** | ✅ | ✅ 3 核起来 | 无 |
| **clk / reset** | ✅ vendor clk | ✅ 主线 clk-rk3506 / rst-rk3506 | 无 |
| **pinctrl / GPIO** | ✅ | ✅ 5 bank probe | 无 |
| **UART console(uart0@ff0a0000)** | ✅ | ✅ ttyS0 1500000 | 无 |
| **PSCI / SMP boot** | 🟡 vendor OP-TEE | 🟡 公开 rkbin tee v2.40(P1 起,SPL v1.12) | blob 残留(闭源 rkbin) |
| **GIC / timer / iommu** | ✅ | ✅ | 无 |
| **OTP(cpuid)** | ✅ | ✅ ff4f0000 | 无 |
| **SPI NAND(W25N04KV) + SFC** | ✅ vendor 私有 sfc_nand | ✅ **主线 spi-nand + rockchip-sfc,DLL 调谐已移植,80MHz 读稳,RW 通** | 已闭合([pitfalls/04](pitfalls/04-sfc-nand-saga.md));写侧加 powergood + WPEN |
| **UBIFS rootfs(busybox)** | ✅ | ✅ **RW 跨冷重启持久** | 已闭合(Linux 落盘 + 页级恢复,[pitfalls/04](pitfalls/04-sfc-nand-saga.md) 坑 #12) |
| **MMC / SD(dw_mmc)** | ✅ MMC_DW_ROCKCHIP | ✅ DT 已接(patch 0005),板验 | 已闭合(外设 A1) |
| **Ethernet(STMMAC/dwmac)** | ✅ STMMAC_ETH + rk3506-ethernet.config | ✅ DT 已接(gmac1 patch 0004 + gmac0 patch 0006,YT8512 RMII),双口板验 | 已闭合(外设 A1) |
| **SPI** | ✅ | ✅ DT 已接,SPI_ROCKCHIP=y | 已闭合(外设 A1) |
| **USB(DWC2 host)** | ✅ USB_DWC2 + fragment | ✅ DT 已接(USB2PHY patch 0014 + DWC2 patch 0015),双 host 板验 | 已闭合(外设 B) |
| **WiFi(RTL8733BU)** | ✅(vendor 私有驱动) | ✅ out-of-tree 移植到 7.1(forge fork + patch 0016),wlan0/wlan1 板验 | 已闭合(Phase WiFi) |
| **I2C / UART2(RMIO)** | ✅ | ✅ RMIO 交叉开关(patch 0007),I2C×3 + UART2 板验 | 已闭合(外设 A2) |
| **Audio(ES8388 + SAI1)** | ✅ | ✅ SAI of_match + PL330 5-cell dmamux(patch 0009/0010),数字链路板验 | 已闭合(Phase E);模拟输出待耳机线 |
| **Display(DRM 800×1280 DSI)** | ✅ rk3506-display.config | ⚠️ 主线 DRM rockchip 在 | +DT + config(等 LCD 到位,非 bringup 必需) |
| **CAN** | ✅ rk3506-can.config | ⚠️ | +DT + config |
| **BT · 4G/5G · AMP** | ✅ | ❌ | 产品特性 / RK 私有,主线无或后置 |

## 能否 boot?——分能力回答

- **主线启动到 UART / userspace handoff**:✅ **能**。CPU 核心 + console 全主线。
- **主线挂 RW rootfs + 进 shell**:✅ **能**。UBIFS rootfs 跨冷重启持久,`/persist.log` 三轮 stress 全在。这条从"暂不能"到"能",是 [pitfalls/04 saga](pitfalls/04-sfc-nand-saga.md) 啃下来的。
- **主线产品级(外设全可用)**:✅ **能**(已达成)。Ethernet 双口 / MMC-SD / SPI / USB / WiFi / I2C / UART2 / Audio 全部接 DT + 板上验证;Display 等屏幕到位再补。

## 主线 vs vendor 的"真差距"在哪

1. **启动前段(DDR/secure)**:主线没法自己 init RK3506 DDR → 借闭源 rkbin blob。最大的"非主线"成分,方案 A(自己 SPL)未成。来源已是公开 rkbin submodule,但 blob 本身闭源这块改不了。
2. **板级外设接线**:已基本接完——核心 + SPI-NAND + Ethernet + MMC + USB + WiFi + I2C/UART + Audio 都在 DT 里、板上验过;只剩 Display(等屏幕)这类非必需项。
3. ~~vendor mkimage 税~~(P4 已消除):uboot FIT 现由 [scripts/fit-pack.py](../scripts/fit-pack.py)(纯 Python)打,vendor-layout 兼容;update.img 由 [scripts/rkfw-pack.py](../scripts/rkfw-pack.py) 打。kernel/boot FIT 也用同一套 packer,不再依赖 vendor 2017.09 mkimage。
4. ~~vendor afptool/rkImageMaker 税~~(D 已消除):assemble 链也纯 Python 化。

## 下一步优先级

1. ~~**RW 加固**~~:**已闭合**——ubiprog/init 固化、PEB 3/4 页级恢复、powergood/WPEN 移植、板上多轮 stress + 冷重启验过([pitfalls/04](pitfalls/04-sfc-nand-saga.md) 闭环)。
2. ~~**P3 外设 DT**~~:**已闭合**——Ethernet 双口 / MMC-SD / SPI / USB / WiFi / I2C / UART2 / Audio 全部接 DT + 板验。
3. ~~**P1 源码层零 vendor-sdk**~~:**已闭合**——rkbin→公开仓 submodule + toolchain→ArmGNU 15.2 + busybox→upstream buildroot([notes/13](notes/13-2026-06-17-p1-rkbin-public-loader-conquest.md))。
4. **(远期)方案 A**:自己的 SPL/DDR → 消除闭源 rkbin blob 残留。这是唯一剩余的"非主线"硬阻塞。

## 证据

- 主线 boot 日志:[boot-sdl-stage-end-of-kernel-uboot-202606151100](logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt)(SMP/pinctrl/uart 起)
- RW 达成日志:[boot-sdl-202606162254](logs/boot-sdl-202606162254.txt)(recovery ×2,`/persist.log` c1/c2/c3)、[boot-sdl-202606162310](logs/boot-sdl-202606162310.txt)(页级恢复)
- 全链(外设全绿):[boot-sdl-2026-06211109](logs/boot-sdl-2026-06211109.txt)(`rk3506 login: root`)
- 主线 patch:`patches/linux/`、`patches/uboot/`(干净上游逐字节相同,见 [notes/11](notes/11-2026-06-16-patch-verification-rw-rootfs.md))
- 闭源 blob 清单 + 公开仓来源:[blobs.md](blobs.md)
