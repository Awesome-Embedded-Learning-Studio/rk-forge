# sdk-diff — RK3568: vendor BSP vs 主线移植（诚实差距报告）

> rk-forge 的"诚实证明器"，RK3568 版。逐子系统对比 Rockchip RK3568 vendor BSP（kernel 5.10 SDK）
> 与主线移植（linux 7.1 + U-Boot 2026.07）的差距。**不美化、不隐藏**：说清 BSP 有什么、主线有没有、
> 差什么、还能不能 boot。本文随 bringup 推进持续更新。
>
> **状态（活文档，partial）**：主线 7.1 + 主线 U-Boot 在 ATK-DLRK3568 真机 boot 到 busybox login，
> LCD ILI9881C / Panfrost Mali-G52 / 双 GMAC / CAN / RTC / Goodix 触摸板上验证。最新里程碑见
> [notes/40（首次 boot）](notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)、
> [notes/42（主线移植交接）](notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)。

## ⚠ 阅读前必须知道的限制（诚实声明）

本篇与 [RK3506B 版](sdk-diff.md) 的扎实程度**不同**，原因有二，读者请据此校准置信度：

1. **vendor 侧未逐文件实地核对**：`reference/rk3568/`（Rockchip RK3568 Linux SDK，5.10）当前未保留在本仓库工作区（gitignored，未拉取）。下表的 vendor BSP 列基于移植笔记（notes/40、42）里的对照记录 + Rockchip 公开 SDK 常识概括，**不是逐 defconfig / 逐 DT 文件实地比对的结果**。凡未在笔记中落实的 vendor 细节，标"未实地核对"。
2. **主线移植产物多数尚未 patch 化**：RK3568 的板级设备树（`rk3568-atk-evb1-ddr4-v10.dts`）、ILI9881C panel descriptor（`panel-ilitek-ili9881c.c` 的 `atk_10p1_desc`）、U-Boot defconfig 改动当前是 `third_party/src/rk3568-atk/` 里的 **working-tree delta**，**尚未 quilt 化进 `patches/rk3568-atk/linux/series`**（该 series 目前只带 rtl8852bs WiFi wire）。也就是说：这些主线移植成果**还不在版本控制里**，第二人 `forge setup` clone 后不能直接复现显示/触摸。把这部分 patch 化是单独的工程任务（见文末"下一步"）。

## 一句话结论

**主线 Linux 7.1 + 主线 U-Boot 在 RK3568 ATK 真机 boot 到 login——CPU 核心 + eMMC + 双 GMAC +
LCD（ILI9881C）+ GPU（Panfrost G52）+ 触摸 + CAN + RTC 全主线打通并板验。** 启动链前段仍借闭源
`rkbin` blob（DDR/SPL/BL31）。**尚未闭合**：WiFi（rtl8852bs 待移植）、音频（RK809 GPIO 冲突）、
USB3/PCIe/VPU/NPU（roadmap），以及上条所述的 patch 化工程债。

## 子系统逐项对比

图例：✅ 工作并验证 · ⚠️ 驱动在主线但未接通或部分 · ❌ 主线缺/未做 · 🟡 借闭源 blob · ❔ 未实地核对

| 子系统 | vendor BSP（5.10） | 主线移植（7.1） | 差距 / 闭合路径 |
|---|---|---|---|
| **CPU 核心（A55×4 SMP）** | ✅ | ✅ 4 核起来 | 无 |
| **clk / reset / pinctrl** | ✅ | ✅ 主线 clk/pinctrl-rk3568 | 无 |
| **UART console（uart2）** | ✅ | ✅ ttyS2 @115200 | 已闭合（ddrbin baud + DT stdout 统一 115200） |
| **PSCI / SMP boot / ATF** | 🟡 vendor BL31 | 🟡 公开 rkbin BL31（binman 自产 loader+u-boot.itb，零 vendor 工具） | blob 残留（闭源 rkbin） |
| **eMMC（HS200）** | ✅ | ✅ mmcblk1 HS200，GPT p1/p2/p3，ext4 rootfs | 已闭合（notes/40） |
| **Ethernet（双 RTL8211F RGMII）** | ✅ | ✅ eth0/eth1（gmac0/gmac1 + ATK rgmii delay），板验 | 已闭合（`STMMAC_ETH` 等 =y，曾因 =m 无 eth，notes/40） |
| **LCD（10.1" MIPI ILI9881C）** | ✅ vendor panel-init-sequence | ✅ 点亮（card0-DSI-1，fb0） | 主线 ILI9881C 驱动 + 新增 `atk_10p1_desc`（194 条 init 机械翻译 + lanes=4 + 67MHz）。**panel descriptor 未 patch 化、精调未完**（init delay/尾命令，notes/42 待办） |
| **GPU（Mali-G52）** | ❔ vendor mali blob | ✅ **Panfrost**（id 0x7402，card1），主线开源 | 主线 Panfrost 闭合；VPU（Hantro+rkvdec2）仍 roadmap |
| **触摸（Goodix GT928）** | ✅ | ✅ /dev/input/event0，板验 | 已闭合（`TOUCHSCREEN_GOODIX=y`） |
| **CAN** | ✅ | ✅ rockchip_canfd can0，板验 | 已闭合 |
| **RTC** | ✅ | ✅ pcf8563，板验 | 已闭合 |
| **HDMI** | ✅ | ⚠️ driver bound（card0-HDMI-A-1）但未接显示 | 驱动在，显示未接 |
| **音频（RK809）** | ✅ | ⚠️ **card 没 probe** | hp-det（gpio1 PA4）抢 i2s1 mclk → rk809-sound 不 probe；只有 BT SCO（card0）。修：换 hp-det gpio 或 i2s1 mclk pinctrl（notes/42 待办） |
| **WiFi（rtl8852bs，SDIO）** | ✅ vendor 851 文件私有驱动 | ❌ **待移植** | SDIO 总线通（mmc2:0001:1 枚举），主线 rtw89 无 SDIO；A1 路径=搬 vendor 驱动适配 5.10→7.1（notes/42 §三） |
| **USB3 / PCIe / SATA** | ✅ | 🚧 roadmap | dwc3 defer-probe（notes/40）；PCIe/SATA DT+cfg 开但未板验 |
| **VPU / RGA / NPU / 摄像头** | ✅ | 🚧 roadmap | RGA/CIF cfg=y 无 DT 节点；NPU 需 vendor rknpu2 + 闭源 librknnrt（主线 Rocket 只 RK3588），未移植 |

## 能否 boot？——分能力回答

- **主线启动到 UART / userspace handoff**：✅ **能**。BootROM → rkbin DDR/SPL/BL31 → 主线 U-Boot → 主线 kernel 7.1 → buildroot rootfs → login（notes/40 全链真机确认）。
- **主线挂 rootfs 进 shell + 外设可用**：✅ **能（部分）**。eMMC / 双 eth / LCD / GPU / 触摸 / CAN / RTC 都板验；但 WiFi 没移植、音频 card 没 probe。
- **主线产品级（外设全可用）**：🟡 **未达**。WiFi + 音频 + USB3/PCIe 仍需收尾。

## 主线 vs vendor 的"真差距"在哪

1. **启动前段（DDR/secure）**：和 RK3506 一样，借闭源 rkbin blob（DDR/SPL/BL31），这是 RK 平台硬现实。比 RK3506 好一点的是 RK3568 有 ATF（BL31），且 binman 自产 loader+u-boot.itb，零 vendor 打包工具。
2. **WiFi 是最大的 vendor 例外**：rtl8852bs 走 SDIO，主线 rtw89 不支持 SDIO，必须搬 vendor 851 文件私有驱动并适配 5.10→7.1——这是 RK3568 主线移植里工作量最大的一块（notes/42 §三 A1 方案）。
3. **音频 GPIO 冲突**：主线 DT 的 hp-det GPIO 抢了 i2s1 mclk，rk809-sound 不 probe。这是 DT 接线问题，不是主线驱动缺失，修 pinctrl 即可。
4. **工程化债（patch 化）**：板 DT + panel descriptor + u-boot defconfig 还是 working-tree delta，没进 `patches/rk3568-atk/series`。这是 RK3568 落后 RK3588（已完整 patch 化）一个工程化阶段的地方。

## 下一步优先级

1. **patch 化（最高优先，工程债）**：在真机把 LCD/panel 精调定稳后，`forge setup --board=rk3568-atk` 拉干净带 `.git` 的 v7.1 源树，把 ATK DT + panel descriptor + u-boot defconfig 改动做成 quilt patch 进 `patches/rk3568-atk/series`。**panel descriptor 当前未定稳（notes/42 待办：init delay + 尾命令），定稳前不应 patch 化。**
2. **rtl8852bs WiFi 移植**：A1 路径（搬 vendor 851 文件 + 5.10→7.1 适配，见 notes/42 §三）。
3. **音频 RK809 GPIO 冲突**：换 hp-det gpio 或调 i2s1 mclk pinctrl，让 rk809-sound card probe。
4. **USB3 / PCIe / VPU / NPU**：roadmap，按需推进。

## 证据

- 首次 boot 全链：[notes/40](notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)（boot 链 + 关键修复 + 剩余问题表）
- 主线移植交接 + 子系统状态表：[notes/42](notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)
- kernel fragment：[board/rk3568-atk/kernel.config](../board/rk3568-atk/kernel.config)
- 板配置：[config/boards/rk3568-atk.env](../config/boards/rk3568-atk.env)
- 闭源 blob 清单：[blobs.md](blobs.md)
