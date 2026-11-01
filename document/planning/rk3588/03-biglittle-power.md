---
title: "卷三：big.LITTLE、功耗与持续性能"
---

# 卷三：big.LITTLE、功耗与持续性能

> RK3588 线 · 卷三 · 第 6–8 章 · [返回线总览](index.md)

### 第 6 章：调度、CPU affinity 与 DVFS

一句话：big.LITTLE 把「任务放哪个核」变成有正确答案的工程问题——**全钉大核是新手最容易犯的错**。

要点：

- 本质：同 ISA 不同能效曲线；EAS 用能量模型选核；任务分两类——latency-sensitive 上大核、throughput 放小核
- capacity/util_avg 是调度器决策依据；`sched_setaffinity` 绕过 EAS，滥用反而劣化
- DVFS：governor（performance/powersave/schedutil/userspace）各自场景；**频繁跳频自己就耗电**
- 钉核的艺术：小核给控制流后台、大核给延迟敏感主线程；**与 IRQ affinity 配合**避免跨核 wake
- 滥用后果很具体：全钉大核→过热降频比小核还慢；全钉小核→性能天花板塌陷
- governor 还是固定频率是产品策略，**要用第 8 章工具验证，凭感觉调等于盲调**

实践：
- 同一 CPU 密集任务分别钉 A55/A76，对比吞吐/占用/温升
- ftrace `sched_switch` 观察迁移轨迹 + perf 统计迁移代价
- 三种 governor 切换对比延迟与温升；设计一个不合理绑核反例再恢复对照

### 第 7 章：thermal、降频与长期稳定性

一句话：热量会吃掉你的性能——thermal 不是可选项，是产品能不能持续工作的硬约束。

要点：

- thermal framework 三件套：zone / cooling / governor；trip point 触发降频——**thermal 本质是用降频换温度**
- SoC 一块硅共享热源：热点会漂移，trip 要看稳态；最坏场景 = 四 IP 同拉满立刻降频（TOPS 跑不满一分钟的物理原因）
- **峰值 vs 持续**：典型差 20-50%，产品指标永远是稳态值（持续 30 分钟后）
- 散热被动/主动是产品定义的一部分；软件策略只能在硬件上限内做
- 三类 trip（passive/active/hot）与产品取向；**hysteresis 漏配 = 频率在边界疯狂跳**

实践：
- 30 分钟满载记录温度/频率/吞吐三曲线，找首次降频点
- 被动 vs 主动散热对比；改一个 trip point 观察稳态变化
- 验证恢复行为（有没有「卡在低频不回来」）

### 第 8 章：系统性能取证

一句话：给「应该怎样」配上「怎么量出来」——**性能问题从来不靠想清楚，只靠测清楚**。

要点：

- perf 主力：stat/record/report/top/sched；常用指标区分算力/内存/调度三类瓶颈
- ftrace + trace-cmd/KernelShark 是内核行为时间线；回答「这 16ms 里每个核在干什么」
- **吞吐与端到端延迟是独立指标**：pipeline 深冲吞吐但延后单帧；同步开销也是延迟
- **平均值会撒谎，尾延迟才是用户体感**（p99 可能是均值 5-10 倍）
- 可重复 benchmark 三要求：同输入、同初始状态、够长时间；分 warm-up/稳态/降频三段；「证据包」模板是卷四与各方向统一要求

实践：
- 建统一性能记录模板
- 对真实 pipeline 做单帧延迟分解（16ms 时间线）
- 10 分钟满载采样分三段；100 次跑画 p50/p90/p99 直方图找尾延迟来源

## 素材与取证

| 资产 | 用途 |
|---|---|
| [notes/57（vendor cpufreq/DVFS 移植）](../../notes/57-2026-08-12-rk3588-vendor-cpufreq-dvfs-port.md) | 第 6 章 DVFS 真板素材 |
| [notes/53（hard-lockup 与 ramoops/watchdog）](../../notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)、[tutorial/rk3588/05_stability](../../tutorial/rk3588/05_stability.md) | 第 7 章长期稳定性取证 |
| [tutorial/rk3588/04_rootfs](../../tutorial/rk3588/04_rootfs.md) | 满载基线的系统侧上下文 |
| [logs/](../../logs/) 的 3588 系列 | 基线日志 |
