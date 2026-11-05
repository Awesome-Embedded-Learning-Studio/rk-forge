---
title: "卷四：SPI-NAND 与可靠存储"
---

# 卷四：SPI-NAND 与可靠存储

> RK3506B 线 · 卷四 · 第 7–10 章 · [返回线总览](index.md)
>
> 这是 RK3506B 路线的核心差异化课程。

### 第 7 章：SPI-NAND 不是普通块设备

一句话：NAND 不是 SD 卡那种「写进去就稳」的东西——**读取稳定 ≠ 写入可靠**，「烧录工具说成功」在这颗料上一钱不值。

要点：

- 读写单位是 page（2048B+128B OOB），擦除只能按 erase block；OOB 归 ECC 与文件系统元数据，不碰
- 出厂就允许有坏块、还会长新的：SD 靠 FTL 藏一切，NAND 你直接在前线 → 跳坏块 + 磨损均衡是必修
- on-die ECC 能纠 1–8 bit；**EUCLEAN = 老化信号要画曲线，EBADMSG = 数据没了**，两个返回码分清
- 软件链：`spi-mem` → MTD → UBI/UBIFS，rk-forge 主线真板基线（不是从厂商 BSP 挖的）
- 写入的四个威胁：断电窗口、program disturb、read disturb、retention；「可靠」只能由 Linux 自己下结论（readback + ECC + 扫坏块）
- SFC 时钟与 DLL 调谐随电气边界收缩，验收别只在室温跑一遍

实践：
- `mtd_debug`/`nanddump` 读 ID 与几何，与 `/proc/mtd`、DT 分区三方对账
- 长跑板上认出 ECC/EBADMSG/EUCLEAN/bad block 各行长什么样
- 抓一次真实读写错误的最小证据集（数据 + OOB + status + 内核日志）

### 第 8 章：从 MTD 到 UBI/UBIFS

一句话：裸 NAND 上不能直接跑 ext4——必须经 UBI 上 UBIFS；这条链在板上已验证。

要点：

- PEB/LEB 两层抽象：EC header（磨损均衡）+ VID header（volume 归属），坏块重映射对上层透明
- `ubiattach` 扫描建表、隔离坏块；磨损均衡防「热点块擦死、冷块从未被擦」的致命偏斜
- UBIFS 日志式是扛断电的关键（journal recovery）；`autoresize` 配「rootfs 占固定 volume、容量首启再定」的设计
- UBIFS（裸 NAND 经 UBI）与 ext4（FTL 块设备）是两个世界，别混用；本板分工：NAND 走 UBIFS，SD 走 ext4
- 真板结论已说死：多轮冷重启/断电/长期写入稳定，证据在 tutorial/rootfs 与 logs

实践：
- `ubinize` 生成镜像并检查 PEB/LEB/EC/VID header
- 真板 `ubiattach` → 挂载，观察 attach 与 recovery
- 制造一次 journal recovery（写过程中硬重启）并分析 dmesg

### 第 9 章：首启置备、可靠烧录与救援

一句话：本卷最硬的一课——烧录工具的「成功」证明不了数据落稳，替代方案是首启置备（initramfs provisioning）。

要点：

- 为什么用 Linux 写而不用烧录工具写：Linux 下 UBI 做坏块管理/ECC/磨损均衡，裸写概率远低于烧录器（loader 弱写 saga 的教训）
- 置备流程：最小 initramfs 起 → 写产品镜像 → readback 验证 → 置位 marker → `switch_root`；**幂等性必须验证**
- `switch_root` 是交接点；分区变化是最大风险（UBI volume 表、`root=`、`ubi.mtd=` 连锁改）
- 三种镜像各管各的：正常 / 置备 / 救援；**救援必须能独立启动**；本板 ROM 只认 RK-tool 烧写卡
- 交付前必须演练「故意改坏 → 救援 → 恢复」，不能等上线才发现救不回来

实践：
- 跑一次完整置备并验证幂等
- 模拟 rootfs 损坏（`dd` 写坏一个 page），从救援镜像修复且不伤无关分区

### 第 10 章：断电、冷重启与长期可靠性

一句话：能起来 ≠ 能交付——验收 NAND 可靠性唯一靠故障注入 + 多轮次重复。

要点：

- 循环：写满 → 冷重启 → 读验证 → 断电 → 再启，每轮记 ECC/坏块/重映射/recovery 次数；**弱点藏在第 100 次冷重启里**
- 冷重启后 dmesg 应见 UBIFS journal recovery；见 `read-only remount`/`mount failed` 即不达标
- 写放大是寿命隐形杀手；三招：可写数据集中独立 volume、系统分区只读、日志限频或转网络
- 工业标准布局：只读根 + 可写数据区 + A/B 升级，是毕业项目一、三的交付形态
- 故障注入手段与「X 轮冷重启 + Y 轮断电 + Z 小时连续写」的验收指标提前定死

实践：
- 跑多轮「写满 → 冷重启 → 读验证」循环并输出统计
- 写过程中硬断电，验证 recovery 与一致性
- 输出存储可靠性报告（坏块增长曲线、ECC 分布、recovery 命中次数）

阶段产出：可恢复的 SPI-NAND 系统、NAND/UBIFS 验证规范、故障注入与恢复日志集合（喂给 [logs/](../../logs/)）。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [pitfalls/04（SPI-NAND saga）](../../pitfalls/04-sfc-nand-saga.md) | 全仓最重的一篇复盘，本卷叙事主线 |
| NAND 九篇流水：[05](../../notes/05-2026-06-15-nand-boot-bbm-ecc-debug.md)、[06](../../notes/06-2026-06-15-nand-recovery-vendor-sfc-bbt.md)、[14](../../notes/14-2026-06-18-rootfs-peb34-readpath-bug.md)、[15](../../notes/15-2026-06-18-sfc-nand-saga-finale-memo.md)、[16](../../notes/16-2026-06-18-spinand-ecc-diagnosis-playbook.md)、[24](../../notes/24-2026-06-19-sfc-abort-rootcause-reserved-memory-trust.md)、[25](../../notes/25-2026-06-19-sfc-abort-misdiagnosis-ddr-sfc-pitfalls.md)、[26](../../notes/26-2026-06-19-ubiprog-loader-weakwrite-status-and-rkbin-lead.md)、[27](../../notes/27-2026-06-20-loader-weakwrite-overturned-linux-sfc-read-bug-dma.md) | 逐案取证 |
| [notes/11（断电与冷重启验证）](../../notes/11-2026-06-16-patch-verification-rw-rootfs.md) | 第 10 章验证记录 |
| [tutorial/rootfs/00、03](../../tutorial/rootfs/) | 第 7–10 章正文主体已兑现于 rootfs 卷（initramfs vs UBIFS 两路、ubiprog 置备 saga、三轮冷重启证据） |
| [tutorial/sd-boot/](../../tutorial/sd-boot/) | 第 9 章「SD 适合置备/救援」的正文承接：RKFW 容器与置备/试验两条路 |
| [pitfalls/05（reserved-memory 与 external abort）](../../pitfalls/05-secure-mem-reservation-imprecise-abort.md) | 存储与内存边界交叉案例 |
| [logs/](../../logs/) 的 boot-sdl 长跑系列 | 多轮冷重启证据 |

## 缺口（待写）

- 第 7 章：page/OOB/坏块物理、EUCLEAN vs EBADMSG、写入四威胁（断电窗口/program disturb/read disturb/retention）、`mtd_debug`/`nanddump` 实验课未写。素材：[notes/16（ECC 诊断 playbook）](../../notes/16-2026-06-18-spinand-ecc-diagnosis-playbook.md)、[notes/05](../../notes/05-2026-06-15-nand-boot-bbm-ecc-debug.md)、[06](../../notes/06-2026-06-15-nand-recovery-vendor-sfc-bbt.md)。
- 第 8 章：PEB/LEB/EC/VID header 理论章、`ubinize` 实验、人为制造 journal recovery 实验未写。素材：[notes/14（PEB34 读路径 bug）](../../notes/14-2026-06-18-rootfs-peb34-readpath-bug.md)、[notes/15（saga 终章备忘）](../../notes/15-2026-06-18-sfc-nand-saga-finale-memo.md)。
- 第 9 章：救援镜像独立启动、「故意改坏 → 救援 → 恢复」演练、正常/置备/救援三镜像分工课未写。素材：[rootfs/03](../../tutorial/rootfs/03_ubifs_loader_weakwrite.md)（read-modify-write + marker + switch_root）、[forge/00](../../tutorial/forge/00_forge.md)（`--provision/--rescue`）、[sd-boot 卷](../../tutorial/sd-boot/)。
- 第 10 章：故障注入循环、「X 轮冷重启 + Y 轮断电 + Z 小时连续写」验收指标、写放大三招专讲、存储可靠性报告课未写（证据已在，课未写）。素材：[notes/11（断电与冷重启验证）](../../notes/11-2026-06-16-patch-verification-rw-rootfs.md)、[logs/](../../logs/) 的 boot-sdl 长跑系列。
