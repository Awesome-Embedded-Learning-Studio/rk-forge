# 12 — 彻底干掉 vendor_sdk:评估 + 路线图(下一轮冲刺用)

> 2026-06-17。RW rootfs 已板上敲定 + patch 存档验证收官后,评估"还差什么能把
> vendor_sdk 完全干掉"。前提:**rkbin 闭源保留**(不打算开源替代),但可从 Rockchip
> 官方公开仓取。本文不急着删 vendor_sdk —— 有些功能和 DT 节点要先对齐(见角色 2)。

vendor_sdk 在 forge 里扮**两个角色**,都要消掉才能删:

## 角色 1:工具 / 二进制提供者(build & flash 流程的直接依赖)

| 依赖 | 现状 | 替代 | 难度 | blocker |
|---|---|---|---|---|
| **rkbin**(loader/DDR/tee/spl/usbplug) | `vendor-sdk/rkbin` | `rockchip-linux/rkbin` 公开仓 submodule(**已验版本对**:rk3506b_ddr_750MHz_v1.06 / rk3506_tee_v2.10 都在) | 低 | 拉下比对 tee sha256 = `93603ca22c...` |
| **toolchain**(gcc-arm-10.3) | `vendor-sdk/prebuilts/gcc` | bootlin `arm-linux-gnueabihf` 预编译 / buildroot 内置 / 发行版包 | 低 | 同 ABI,换 `CROSS_COMPILE` 重编 + 上板验 |
| **busybox 源**(1.36.1) | `vendor-sdk/buildroot/dl` | upstream busybox.net 同版 / buildroot | 极低 | 换 tarball 源 |
| **vendor mkimage 2017.09** | `vendor-sdk/u-boot/tools`(打 uboot FIT) | 干净 FIT 打包器产出 vendor 兼容 `-E` 布局;或接受(rkbin SPL 税) | 中-难 | rkbin SPL 不换,布局就得对它 |
| **afptool + rkImageMaker** | `vendor-sdk/tools/linux/...`(打 update.img) | `rkdeveloptool`(开源)按分区直烧 `db`+`wl`;或干净重写 RKAF/RKFW(~200 行) | 中 | rkdeveloptool 的 SPI-NAND 写在 RK3506 板验 pending(notes/09 §七) |

> kernel FIT 已经用主线 mkimage(explore/uboot/tools/mkimage 2026.07);只有 **uboot FIT** 需要 vendor 2017.09(rkbin SPL 读它的 -E 布局)。

## 角色 2:参考来源(vendor 内核 DT / 外设 config —— 要对齐的部分)

sdk-diff(document/sdk-diff.md)列的差距:**主线驱动都在,差 DT 节点 + config + bringup = 接线活,非写驱动**:

| 外设 | 主线驱动 | 缺什么 | bringup 要点 |
|---|---|---|---|
| MMC/SD(dw_mmc) | ✅ | DT `&sdmmc`/`&sdhci` 节点 + config | +io-domain |
| Ethernet(stmmac/dwmac) | ✅ | DT `&gmac` + phy + config | phy/时钟 |
| USB(dwc2 host/otg) | ✅ | DT `&usb` + config | — |
| Display(DRM rockchip) | ✅ | DT + config | 非必需 |
| CAN | ✅ | DT + config | — |
| WiFi/BT | — | 产品特性 | 后置 |

→ 删 vendor_sdk 前,把**产品要用的外设**从 vendor DT 移植进 forge 主线 DT(vendor 当参考)+ 逐个板验。移完 forge DT 自足,vendor 不再是参考 → 这块就能删。这就是"功能和设备树节点要对齐"。

## 架构一刀:buildroot(upstream)

一次覆盖角色 1 的 toolchain + busybox + rootfs:buildroot 内置工具链 + 自建 rootfs(busybox + 完整用户态),干掉 vendor toolchain + vendor busybox,还把手搓 rootfs 换成正经 buildroot rootfs(记忆 `next-phase-nand-packaging-and-buildroot` 的"清爽 buildroot"阶段)。配一份 rk3506 buildroot defconfig。

## 未解之谜(点名要查):为什么 loader 写"我们这份"rootfs 弱

- 事实:同一个 loader(4762d6,解包 vendor 镜像 = 我们的)写 **vendor rootfs 稳**、写**我们 rootfs(4MB)PEB 3/4 弱**。我们**绕过了**(ubiprog 首启 Linux 重写 + 页级恢复),但**没根因**。
- 待查方向:
  1. loader(rkbin)的 SFC **写侧**配置:速度 / DLL / 驱动强度 / io-domain —— 读侧我们移植了 DLL+powergood+WPEN 修好,**写侧** vendor/loader 是否另有配置我们没对齐?
  2. 我们的 rootfs **内容/大小**为何触发弱写:4MB 小 image 的尾部?UBIFS master 节点的 bit 模式 program-disturb?PEB 3/4 物理块恰好在 loader 写弱的区?
  3. vendor 的**完整 flash 流程** vs 我们的有何不同(mk-updateimg 参数、parameter、写顺序)。
- 深查 = 拆 rkbin loader(反汇编 SFC 写初始化)或对照 vendor 工具链全流程。**纯求知 + 彻底性,不挡 RW**(RW 已通)。

## 分期路线(下一轮冲刺候选)

- **P0(先做,整理)**:收敛仓库文档 + 出**多份 markdown 的完整《踩坑日记》**(不是单文件)。当前文档散(document/notes/05-12、sdk-diff、bringup/nand-rootfs/{README,PROGRESS,HANDOFF-LOADER-MARGINAL-WRITE,SFC-WRITE-CORRUPTION-POSTMORTEM,RW-WRITE-FIX-powergood-wpen,BOARD-VALIDATION}、notes/nand-ecc-debug-handoff),有重叠 + 已被推翻的(HANDOFF/POSTMORTEM 是 saga 旧错结论、RW-WRITE-FIX 是早期 powergood-only 误判 —— 都已被 [[sfc-dll-saga]] 顶部 RW-SOLVED 段取代)。**收敛** = 去重 + 标记 superseded/归档错结论 + 保留 canonical。**踩坑日记** = 以现有 notes/logs 的**现场**(`third_party/logs/boot-sdl-*.txt` 实测日志 + 各过程笔记)为素材,**还原真实完整的时间线** —— 含走过的弯路(如 saga"rkbin 通病不可解"误判)+ 被推翻的结论 + 每步板上证据(log 行),如实叙事;按阶段或每坑分篇,引对应 log 佐证。

  **踩坑日记骨架 / scope**(供执行 AI,逐条核实后分篇落成 `document/pitfalls/` 系列):
  1. **chip tag = RK350F**(从 loader offset 21 读 4B 反转),非硬编 RK3506 → 否则 RKDevTool「校验芯片失败」。
  2. **tee 必 v2.10**(vendor SPL verified-boot 验 optee hash),非 v2.40 → 否则 optee Bad hash。
  3. **uboot FIT 必 vendor mkimage 2017.09**(`-E` external-data 布局),非主线 mkimage → 否则 vendor SPL 读 optee 错位。
  4. **inittab 只一行 `ttyS0::respawn:/bin/sh`**(console=ttyS0 下两行抢同一 tty 劈字符)。
  5. **SFC**:DLL 调谐(写 SFC_DLL_CTRL0)+ **50MHz 非 80MHz**(80 下 DLL 窗口仅 ~70 cell)+ powergood 门(GRF_PMU+0x100)+ WPEN(BIT29)—— 读侧+写侧都要。
  6. **loader 写我们 rootfs 弱**(PEB 3/4)→ 绕过:ubiprog 首启用 Linux 重写 + 页级恢复;根因未明(见"未解之谜")。
  7. **bootm**:FIT 暂存 `0x04000000`(避 kernel load 0x02080000 撞);`mtd read boot` 长度要覆盖 FIT(7MB 内核 → `0x800000`,别用旧的 `0x600000` 截断)。
  8. **内核 XZ 压缩**(multi_v7→7.1MB)避出厂坏块(boot-relative 0x920000=9.125MB);不砍代码,只换压缩。
  9. **syncconfig 报错 = CROSS_COMPILE 用了相对路径**(kconfig 找不到 gcc → 挡增量重编)。**必绝对路径**。
  10. **验 PROBE 去留用未压缩 `.o`**(`strings` zImage 看不到内核文本,zImage 是 XZ 压缩)。
  11. **initramfs switch_root 前挂 `devtmpfs` 到 `/mnt/dev`**(CONFIG_DEVTMPFS_MOUNT 只盖 initramfs 的 /dev),否则 busybox init `can't open /dev/ttyS0`。
  12. **ubiprog**:全块读不可纠 = **页级恢复**(保 PEB 头部 master 节点页 + 不可纠尾页填 0xFF → 擦+Linux 重写),非"跳过+判败"。

- **P1(快、低风险)**:rkbin→公开仓 submodule + toolchain→bootlin + busybox→upstream → **源码层零 vendor_sdk**(只剩打包工具)。
- **P2**:buildroot 接入(toolchain+rootfs 一次清)+ afptool/rkImageMaker → rkdeveloptool(先板验 SPI-NAND 写)或干净重写。
- **P3(你说的对齐)**:外设 DT 移植(MMC/ETH/USB/DISPLAY/CAN 从 vendor DT 进 forge DT)+ 逐个板验。
- **P4**:vendor mkimage 干净替代(或接受 rkbin-SPL 税)。
- **P5(深查、可选)**:loader 弱写根因。

## 删除 vendor_sdk 的判据

**角色 1 全部替代**(rkbin/toolchain/busybox/mkimage/打包工具都有干净源)+ **角色 2 forge DT 自足**(产品要用的外设都从 vendor DT 移植 + 板验过)= vendor_sdk 可删。

## 相关
- sdk-diff:`document/sdk-diff.md`;记忆 `vendor-build-pipeline-for-forge`(io-domains 是真贡献点)、`vendor-sdk-atk-bsp`、`next-phase-nand-packaging-and-buildroot`。
- loader 弱写 saga:记忆 `sfc-dll-saga-and-writepath`(顶部 RW-SOLVED 段)、`bringup/nand-rootfs/RW-WRITE-FIX-powergood-wpen.md`。
