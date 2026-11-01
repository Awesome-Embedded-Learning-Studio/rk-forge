---
title: "卷七：驱动质量与交付"
---

# 卷七：驱动质量与交付

> RK3568 线 · 卷七 · 第 19–20 章 · [返回线总览](index.md)
>
> 第 19、20 章是质量交付内容，对应能力成长地图的「掌握质量」阶段，单独立卷，不随卷六的选修性质裁掉。

### 第 19 章：驱动调试工具

一句话：驱动写完不等于对——dynamic debug、ftrace、perf、oops 分析这套定位工具。

要点：

- dynamic debug 动态开关打印；过早打印要用 earlycon
- debugfs（clk_summary/regulator_summary/gpio）与 sysfs 的分工
- ftrace + trace-cmd/KernelShark 抓内核行为时间线，定位延迟尖峰的标准流程
- perf stat/record/report 区分算力/内存/调度瓶颈
- oops 栈回溯（addr2line/objdump）、kdump、KGDB、KASAN/lockdep

实践：
- 定位一次空指针/泄漏/竞态/死锁
- 记录 probe/IRQ/DMA 延迟，对比修复前后证据

### 第 20 章：把驱动做成可维护交付物

一句话：能跑只是第一步——Kconfig、binding、ABI、测试、patch series 做到可维护、可上游、可交付。

要点：

- Kconfig tristate 与 `obj-$(CONFIG_*)`；依赖与 select 关系理清
- YAML binding + `dtbs_check`；**没有 binding 的驱动进不了主线**
- ABI 一旦暴露就难改，慎重设计并文档化
- 错误路径完备性 + 用户态测试程序 + kselftest 形成回归
- patch series：一个逻辑一个补丁、checkpatch、Signed-off-by、社区流程
- host/构建/真板三道验证分层（同 RK3506B 卷七的制度）
- **NPU 驱动移植练习**：本线唯一的 out-of-tree NPU 例外项——rknpu2 + librknnrt 移植与版本配对（与 rtl8852bs 同为「接 out-of-tree 驱动 = 接受长期维护成本」的交付案例；AI 应用课归 RK3588，这里只做驱动侧）

最终产出：驱动源码与配置、DT/binding、用户态测试程序、性能与稳定性报告、真板日志、已知限制清单。

## 素材与取证

| 资产 | 用途 |
|---|---|
| 内部写作账本（老规划写作队列，不入站） | 第 19、20 章的验收要点底账（ftrace 定位真实问题、patch series 过 checkpatch） |
| [tutorial/forge/](../../tutorial/forge/) | 三道检查与可复现构建 |
| [pitfalls/03（构建验证）](../../pitfalls/03-build-verification.md) | 验证纪律的跨板案例 |
| [RK3506B 线卷七](../rk3506b/07-delivery-evidence.md) | 证据制度对照，两线共用方法论 |
