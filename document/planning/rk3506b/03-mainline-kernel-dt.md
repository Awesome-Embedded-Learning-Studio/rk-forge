---
title: "卷三：主线内核、设备树与补丁"
---

# 卷三：主线内核、设备树与补丁

> RK3506B 线 · 卷三 · 第 5–6 章 · [返回线总览](index.md)

### 第 5 章：从 SoC 支持到一块具体板

一句话：主线有 SoC 支持不等于你的板能起来——中间差一块板级设备树；拿到 `probe failed` 先分层再动手。

要点：

- `.dtsi`（SoC 固有，主线维护）与 `.dts`（板级接线，rk-forge 写、目标推上游）分工；RK3506 SoC 级支持已进主线（pinctrl/clk 从 6.19 起），RK-SDK 坍缩成就两样绕不开的：rkbin + 板级 DT
- 外设节点五件套 `compatible`/`reg`/`interrupts`/`clocks`/`resets`，缺一不可（缺 clock → probe defer）
- RK3506 特色 **RMIO 交叉开关**：比 pinmux 多一层「控制器信号 → pad」路由，布线受限时可挪功能到空闲 pad；按原理图核对，别抄参考板
- 从厂商 DTS 提取硬件事实的分类纪律：事实采纳、厂商做法丢弃、**绝不照抄**
- probe 失败四层定位顺序：SoC 支持 → 板级 DT → kernel config → 最后才怀疑驱动

实践：
- 跟踪一个真实外设从 DT 节点到 probe 的完整路径
- `status = "disabled"` 一个外设观察 probe 进出；拿一条真实失败日志判层
- 画一个外设的「DT → clock/reset/regulator → 寄存器 → IRQ」依赖图

### 第 6 章：有序补丁与主线差距

一句话：主线优先落地成一个具体的东西——按顺序排好的补丁库，加一份不合成不夸大的差距报告。

要点：

- quilt 风格 series，`git am` 落成真实 commit，可 bisect 可原子回滚；**顺序错了 bisect 会得出错误结论**
- 必修的老毛病：只打最后一个补丁、坏了静默跳过（`|| true`）；`forge apply`（内部 `git am`）要么全打上要么全不打
- 三类补丁命运不同：板级/驱动补丁目标上游化，临时诊断补丁（WIP:/HACK: 标记）不进主线、用完清掉
- 验证纪律：全新 clone → `git am` 全 series → 干净构建 → 干净跑 → 干净烧板，不依赖本地未提交改动
- [sdk-diff.md](../../sdk-diff.md) 是「主线走不走得通」的依据：逐子系统差距，verified/blocked 按证据标；补丁库天然是上游化预热池

实践：
- 全新主线源码上完整 `git am` 一遍 series；故意打乱顺序观察失败与回滚
- 选一个外设做「厂商 BSP → 主线现状 → rk-forge 补丁」三段对比写进 sdk-diff
- 整理 series 依赖图，标上游化候选与临时诊断

## 素材与取证

| 资产 | 用途 |
|---|---|
| [sdk-diff.md](../../sdk-diff.md) | 第 6 章活教材：BSP 与主线逐子系统差距 |
| [boards/aes/patches/](../../../boards/aes/patches/) | 三组补丁系列（linux/uboot/openwrt，`0001-` 起编号）讲补丁秩序 |
| [tutorial/boot/03](../../tutorial/boot/03_kernel.md) + [peripherals](../../tutorial/peripherals/) 各章 + [forge/00](../../tutorial/forge/00_forge.md) | 第 5 章正文已兑现于 boot/03 与 peripherals 各章 DT 实战；第 6 章纪律散见 boot/00、forge/00 与各章 patch 编号引用 |
| [notes/02](../../notes/02-2026-06-14-mainline-bringup-handoff.md)、[04](../../notes/04-2026-06-14-mainline-uboot-via-vendor-spl.md)、[10](../../notes/10-2026-06-15-dt-migration-sfc-spi-nand-partitions.md)、[12](../../notes/12-2026-06-17-kill-vendor-sdk-assessment.md)、[17](../../notes/17-2026-06-18-patch-solidification-sop.md) | 取证链 |
| [notes/23（RMIO 交叉开关）](../../notes/23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md) | 第 5 章 RMIO 素材 |
| books 的 ARMv7 编程手册与 Cortex-A7 TRM | 架构参考（`.claude/books/`，本地资料） |

## 缺口（待写）

- 第 5 章：「外设节点五件套 / probe 失败四层定位」方法论散在正文，未显式成节（小节级，可接受）。素材：[boot/03](../../tutorial/boot/03_kernel.md)、[peripherals/00 路线图](../../tutorial/peripherals/00_roadmap.md)。
- 第 6 章：series 纪律专节、全新 clone `git am` 全 series 演练、补丁三命运、sdk-diff 维护方法、上游化预热池未写。素材：[boards/aes/patches/](../../../boards/aes/patches/)、[sdk-diff.md](../../sdk-diff.md)、[notes/17（补丁固化 SOP）](../../notes/17-2026-06-18-patch-solidification-sop.md)；Git 通论由 [host 总纲](../../tutorial/host/00_roadmap.md)第 3 章规划承接（未写）。
