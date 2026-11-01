---
title: "卷一：RK3588 平台、启动与安全边界"
---

# 卷一：RK3588 平台、启动与安全边界

> RK3588 线 · 卷一 · 第 1–2 章 · [返回线总览](index.md)

### 第 1 章：RK3588 异构 SoC 全景

一句话：「很多 IP 挤在一块硅上」的异构 SoC——每个 IP 干什么、怎么共享内存、**为什么峰值跑分在这颗芯片上特别骗人**。

要点：

- big.LITTLE（A76+A55）是异构起点：不是核多，是核不一样；大小核迁移的 cache 抖动能让延迟尖峰翻倍（卷三展开）
- 五个加速器分工（GPU/NPU/VPU/RGA/ISP）；平台工程师的核心判断 = 哪个任务送哪个 IP；**小数据量、控制流密集的留在 CPU 更省**
- cache 与一致性域决定要不要显式 flush：一致域免 flush，非一致域必须显式 sync，搞错就漏 flush 或白 flush
- 数据格式/stride/alignment 细节：同一帧 CPU→GPU→NPU 是几次带宽消耗——零拷贝问题的起点（卷二第 5 章展开）
- **带宽比算力先饱和**：持续性能受热（卷三）、带宽（本章）、同步开销（卷四）三重钳制；永远先量持续性能（稳态 30 分钟+）再谈峰值

实践：
- 建 CPU 拓扑表（capacity/频率/cluster）
- 画 SoC 数据流图（哪些直连、哪些经 DRAM 中转）
- 列每个加速器的驱动/固件/用户态栈清单并标 target 状态

保存证据：硬件与软件栈清单、数据流图、真板基线日志（完整启动 + 空载 + 满载一段）。

### 第 2 章：启动链、ATF、OP-TEE 与系统分区

一句话：三块板里最复杂的启动链——信任边界在哪、**secure boot 的不可逆风险**、Linux 与 Android 两条启动路径的差异。

要点：

- 链：`BootROM → loader → ATF → OP-TEE → U-Boot → Linux`；闭源/开源分界画在 rkbin 之后；画「信任链移交图」
- **secure boot 红线**：efuse 烧成强制验签+关 JTAG 后丢私钥的板永远救不回来；缺密钥治理+恢复方案+双套密钥三项时绝不烧 efuse，教学只到原理与日志分析
- 分区三角色（boot/rootfs/vendor）为什么分开：升级粒度、签名主体、回滚策略都不同；A/B 双分区是产品级标配
- Linux 与 Android 启动链差异巨大（init/Zygote/SELinux/分区模型），**别把 Linux 假设照搬到 Android**（Android 方向第 1、2 章展开）
- 三板对照：与 RK3568 同为 AArch64 但不共用任何产物；RK3506B 是 ARMv7 无 ATF

实践：
- 完整启动日志逐行标注、版本号映射回 pin
- 画分区表并与 bootcmd 对应；验证恢复入口（**只读不改，不碰 efuse**）
- 分析一次启动失败案例，形成「日志→原因→恢复」对照表

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rk3588/01_boot](../../tutorial/rk3588/01_boot.md) | 真机 boot 强锚点（主线 v7.1 + U-Boot 2026.07 + 主线 SPL） |
| [notes/49](../../notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)、[50](../../notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md)、[43](../../notes/43-2026-07-31-rk3588-autoboot-baud-bootcmd.md) | 启动链取证 |
| [boot-rk3588.txt](../../../boot-rk3588.txt) | 串口抓取原件 |
| [boards/rk3588-topeet/](../../../boards/rk3588-topeet/) | 板级 pinout、分区表、补丁 |
| [blobs.md](../../blobs.md) 与 [sdk-diff-rk3588.md](../../sdk-diff-rk3588.md) | 闭源边界与差距口径 |
| books/RK3588 的 Linux 系统开发、原厂文档、硬件开发目录 | 厂方参考（`.claude/books/`，本地资料） |
