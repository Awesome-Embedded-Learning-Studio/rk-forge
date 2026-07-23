# document/notes — dated bringup log

This tier holds **honest, dated bringup notes** — what worked, what didn't, the exact
UART output, the brick scares. It's the project's honesty substrate (on-brand:
rk-forge's identity is "report the gap truthfully").

> 在 [document/](../) 四层结构里,这里是 **raw 过程笔记**层(取证源)。踩坑日记在
> [pitfalls/](../pitfalls/)(回溯提炼的完整叙事 + canonical 结论),被推翻的旧结论在
> `archive/`,板上日志在 [logs/](../logs/)。本目录不删、不去重 —— 它是按天的
> 流水,和 pitfalls 重叠是正常的,一个记现场、一个讲结论。

## 命名约定

`NN-YYYY-MM-DD-<slug>.md` — **序号 + 日期 + slug**:

- **序号 `NN`** = 推荐阅读顺序(理解项目的递进阶段),主导排序。
- **日期 `YYYY-MM-DD`** = 笔记对应的工作日期。
- **slug** = 内容一句话描述。

跨阶段持续更新的"活文档"用其主工作日期。Don't sanitize failures — they're the
most useful part.

## 阅读顺序(按阶段递进)

| 序号 | 文件 | 阶段 |
|---|---|---|
| 01 | [01-…-vendor-uboot-build-flow](01-2026-06-14-vendor-uboot-build-flow.md) | 先懂 vendor 怎么编 U-Boot(主线迁移的参照基准) |
| 02 | [02-…-mainline-bringup-handoff](02-2026-06-14-mainline-bringup-handoff.md) | 主线 U-Boot bring-up 状态总览(活文档,跨阶段) |
| 03 | [03-…-maskrom-brick-recovery](03-2026-06-14-maskrom-brick-recovery.md) | 救砖插曲:固件写坏 → MaskROM 恢复 |
| 04 | [04-…-mainline-uboot-via-vendor-spl](04-2026-06-14-mainline-uboot-via-vendor-spl.md) | 方案 B:借 vendor SPL 跑主线 U-Boot,真板进提示符(里程碑) |
| 05 | [05-…-nand-boot-bbm-ecc-debug](05-2026-06-15-nand-boot-bbm-ecc-debug.md) | NAND boot 的 BBM/ECC 调试(SFC 读 corrupt 起点,saga 段一误判) |
| 06 | [06-…-nand-recovery-vendor-sfc-bbt](06-2026-06-15-nand-recovery-vendor-sfc-bbt.md) | 借 vendor SFC bbt 恢复 NAND(saga 段二,DLL 初判) |
| 07 | [07-…-milestone-mainline-linux-boots](07-2026-06-15-milestone-mainline-linux-boots.md) | 主线 Linux boot 到 `~ #` 里程碑(定型日志在此) |
| 08 | [08-…-replace-sdk-nand-packaging](08-2026-06-15-replace-sdk-nand-packaging.md) | 取代 SDK 的 NAND 打包(chip tag / parameter / 分区) |
| 09 | [09-…-vendor-nand-packaging-forensics](09-2026-06-15-vendor-nand-packaging-forensics.md) | vendor NAND 打包取证(update.img 结构 / mk-updateimg) |
| 10 | [10-…-dt-migration-sfc-spi-nand-partitions](10-2026-06-15-dt-migration-sfc-spi-nand-partitions.md) | DT 迁移:SFC + SPI-NAND 分区,板门验证通过 |
| 11 | [11-…-patch-verification-rw-rootfs](11-2026-06-16-patch-verification-rw-rootfs.md) | patch 验证:RW rootfs patch 在干净上游逐字节相同 |
| 12 | [12-…-kill-vendor-sdk-assessment](12-2026-06-17-kill-vendor-sdk-assessment.md) | 彻底干掉 vendor_sdk:评估 + P0–P5 路线图(本 P0 的源头) |
| 13 | [13-…-p1-rkbin-public-loader-conquest](13-2026-06-17-p1-rkbin-public-loader-conquest.md) | P1 第一刀 rkbin:全公开 loader 攻克 + 纠正"公开仓有 v2.10"前提(toolchain/busybox deferred) |
| 14 | [14-…-rootfs-peb34-readpath-bug](14-2026-06-18-rootfs-peb34-readpath-bug.md) | rootfs PEB3/4 弱写读路径排查(最终定 loader 弱写) |
| 15 | [15-…-sfc-nand-saga-finale-memo](15-2026-06-18-sfc-nand-saga-finale-memo.md) | SFC/NAND saga 终章备忘(rootfs loader 弱写确认 + 80MHz 定型) |
| 16 | [16-…-spinand-ecc-diagnosis-playbook](16-2026-06-18-spinand-ecc-diagnosis-playbook.md) | SPI-NAND ECC 诊断 playbook |
| 17 | [17-…-patch-solidification-sop](17-2026-06-18-patch-solidification-sop.md) | patch 固化 SOP |
| 18 | [18-…-board-verification-playbook](18-2026-06-18-board-verification-playbook.md) | 上板验证 playbook |
| 19 | [19-…-buildroot-minimal-rootfs-first-build](19-2026-06-18-buildroot-minimal-rootfs-first-build.md) | buildroot 最小 rootfs 首次构建成功(/opt Arm GNU 15.2 外部工具链,3 连坑:PATH/语言 check/RPC) |
| 20 | [20-…-mkimage-saga-handoff](20-2026-06-19-mkimage-saga-handoff.md) | mkimage saga:fit-pack.py 纯 Python FIT packer 替 vendor mkimage(P4 收官) |
| 21 | [21-…-peripheral-bringup-a1-eth-mmc-spi](21-2026-06-19-peripheral-bringup-a1-eth-mmc-spi.md) | 外设 A1:Ethernet 双口 + SPI + MMC/SD 全板验跑通(Role 2 自足第一刀;方法论:vendor 同板 log 证硬件) |
| 22 | [22-…-mmc-sd-error110-investigation](22-2026-06-19-mmc-sd-error110-investigation.md) | MMC -110 排查:两次误判(物理→驱动回归),真因卡接触;逐项排除 DT/clk/pinctrl 等价 vendor 的方法论 |
| 23 | [23-…-peripheral-bringup-a2-rmio-i2c-uart2](23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md) | 外设 A2:RMIO 交叉开关(0007)+ I2C×3 + UART2 + GT911 触摸,pinctrl-rockchip RMIO 移植 |
| 24 | [24-…-sfc-abort-rootcause-reserved-memory-trust](24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md) | **RW/abort saga 真根因**:DT 缺 reserved-memory → OP-TEE/trust 物理页分给用户态 → external abort;tmpfs 判别 + patch 0012 + 板验 50/50 过 |
| 25 | [25-…-sfc-abort-misdiagnosis-ddr-sfc-pitfalls](25-2026-06-19-sfc-abort-misdiagnosis-ddr-sfc-pitfalls.md) | abort saga 两轮误诊复盘(DDR 头号嫌疑 / SFC PIO-DMA)+ 方法论(imprecise FAR 不可信、tmpfs 判别器、vendor 对齐) |
| 26 | [26-…-ubiprog-loader-weakwrite-status-and-rkbin-lead](26-2026-06-19-ubiprog-loader-weakwrite-status-and-rkbin-lead.md) | ubiprog/loader 弱写现状(独立于 abort,recovery 非 cure)+ 下一步 rkbin 配置对齐线索 |
| 27 | [27-…-loader-weakwrite-overturned-linux-sfc-read-bug-dma](27-2026-06-20-loader-weakwrite-overturned-linux-sfc-read-bug-dma.md) | **"loader 弱写"第三次翻案**:U-Boot/Linux 同 flash 对比坐实 Linux SFC 读 bug(B);DLL/频率否、PIO/DMA 头号;DMA 实验(update-rwfix-dma.img) |
| 28 | [28-…-usb-bringup-usb2phy-dwc2](28-2026-06-20-usb-bringup-usb2phy-dwc2.md) | 外设 B-USB:USB2PHY(inno-usb2 RK3506 phy_base 调谐)+ DWC2 双口 host,USB hub/U 盘枚举(让板上 RTL8733BU 枚举为 0bda:b733) |
| 29 | [29-…-wifi-rtl8733bu-driver-port-roadmap](29-2026-06-20-wifi-rtl8733bu-driver-port-roadmap.md) | WiFi RTL8733BU 移植 **roadmap**(研究结论 + 5 阶段计划;主线无驱动→out-of-tree 移植,mainline-only 为此松绑) |
| 30 | [30-…-wifi-rtl8733bu-port-complete](30-2026-06-20-wifi-rtl8733bu-port-complete.md) | **WiFi 移植完成 + 板上联网验证**:Phase 1-5 全 done(187 文件 Kbuild 重写 + cfg80211 wdev wrapper),8733bu.ko 板上 insmod→probe→fw→wlan0→wpa 连网通 |
| 31 | [31-…-mk-rootfs-patch-maker-removal](31-2026-06-20-mk-rootfs-patch-maker-removal.md) | mk-rootfs / patch-maker 残留清理(P2.5) |
| 32 | [32-…-sd-card-image-sd1](32-2026-06-21-sd-card-image-sd1.md) | SD-1:RKFW SD-card boot 实装+板验(纯 ext4 root,boot-sdl-202606211028 收官) |
| 33 | [33-…-sd-card-autoboot-sd2](33-2026-06-21-sd-card-autoboot-sd2.md) | **SD-2 autoboot**:第二份 uboot defconfig(mmc read bootcmd)+build/pack/assemble --variant sd,git worktree 隔离编译零触碰 nand。实装+host 验证 done,板验待做 |
| 34 | [34-…-openwrt-integration](34-2026-07-11-openwrt-integration.md) | OpenWrt 集成日记(profile 架构 + Device/aes overlay + 分阶段 build 解竞态) |
| 35 | [35-…-openwrt-rootfs-flow](35-2026-07-12-openwrt-rootfs-flow.md) | OpenWrt rootfs 从源码到上板的七步链路(NAND UBIFS ubiprog + SD ext4) |
| 36 | [36-…-rk3568-multiboard-and-mainline-build](36-2026-07-22-rk3568-multiboard-and-mainline-build.md) | **RK3568 上板奠基**:多板框架(board 注册表 + 8 脚本参数化) + 主线 kernel/uboot 编通 + binman 自产 loader/uboot(零 vendor 工具)。主线优先,NPU 为唯一例外 |

另有 [nand-ecc-debug-handoff.md](nand-ecc-debug-handoff.md)(早期 NAND ECC 调试交接,部分结论已被后续 saga 取代,以 [pitfalls/04](../pitfalls/04-sfc-nand-saga.md) 为准)。

## 与 pitfalls 的关系

本目录是按天记的 raw 现场(含失败、噪音、半成品、当时的错判);[pitfalls/](../pitfalls/) 是事后回溯、把 12 条坑按故障域重新组织成的完整叙事 + canonical 结论。要快速理解"踩了哪些坑、怎么解的",直接读 pitfalls;要还原某一天的原始折腾,翻这里。saga 那段被推翻的旧结论(HANDOFF/POSTMORTEM/RW-WRITE-FIX)已移入 `archive/`。

## 待补

- `NN-2026-06-13-restructure.md` — repo 重构 + 前提验证(对应 commit `325a3bf`,目前无独立笔记)。
- vendor-sdk 总体调研(当前散在 01 里,可抽独立笔记)。
