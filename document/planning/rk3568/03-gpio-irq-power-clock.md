---
title: "卷三：GPIO、中断、电源与时钟"
---

# 卷三：GPIO、中断、电源与时钟

> RK3568 线 · 卷三 · 第 8–10 章 · [返回线总览](index.md)

### 第 8 章：pinctrl、GPIO 与 input

一句话：怎么管引脚——pinctrl 复用、GPIO 输入输出、input 子系统把按键触摸接到用户态。

要点：

- pinctrl 管 pad 复用；DT 里 `pinctrl-0`/`pinctrl-names` 声明 pin 组；**引脚复用冲突是常见坑**（后 probe 的失败）
- gpiod descriptor API（取代编号 API）：`GPIO_ACTIVE_LOW` 的电平反转由 gpiod 自动处理
- input 子系统是按键触摸的标准入口（EV_KEY/EV_ABS/EV_REL）；**接 input 而不是私有 ioctl**，evtest/libinput 才能用

实践：
- 真实按键/告警输入做 GPIO 中断或轮询，并接入 input 子系统
- 故意声明冲突 pad，验证复用冲突报错

### 第 9 章：GIC 与中断处理

一句话：GIC 架构与 Linux 中断处理——top half / bottom half 分工、threaded IRQ、中断风暴实战。

要点：

- GIC v2/v3 差异（v3 引入 redistributor/LPI）；中断号、触发类型、`smp_affinity` 亲和性
- top half 必须快不能睡眠；耗时处理推迟到 threaded IRQ / workqueue（tasklet 逐步淘汰）；**处理需要睡眠（如 I²C 读寄存器）必须线程化**
- 中断风暴 / 共享中断（IRQF_SHARED）/ 丢中断三类实战问题；`/proc/interrupts`、`/proc/softirqs` 是诊断工具
- 中断响应延迟用 tracepoint / `irqsoff` 量；延迟大的常见原因

实践：
- 外部 GPIO 中断计数与时间戳；调触发类型分析错误现象
- 用 tracing 测响应延迟

### 第 10 章：clock、reset、regulator 与 runtime PM

一句话：驱动资源三件套（时钟/复位/供电）加 runtime PM 省电。

要点：

- CCF：时钟父子关系与类型（mux/divider/gate）；**漏开时钟是经典 bug**（寄存器全 0 或 hang）
- reset：`assert`/`deassert`；典型上电时序先 deassert → enable clk → 才能碰寄存器
- regulator：`xxx-supply` 声明；**多路供电顺序错可能损坏硬件**
- runtime PM：引用计数 + autosuspend_delay；漏关诊断靠 debugfs 的 `clk_summary`/`regulator_summary`

实践：
- 真实设备管理 clock/reset/supply；模拟 probe 中段失败验证资源回收
- 验证 suspend/resume 或 runtime suspend；分析一次漏关时钟

## 素材与取证

| 资产 | 用途 |
|---|---|
| books 的 GIC v2/v3/v4 控制器手册 | 第 9 章主参考（`.claude/books/`，本地资料） |
| [notes/63（PMU 状态机与 I²C NACK）](../../notes/63-2026-08-25-rk3568-pmu-state-machine-i2c-nack-3s8-boot.md) | regulator/I²C 真实案例 |
| [notes/23（RMIO 交叉开关）](../../notes/23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md) | pinctrl 移植思路的 32 位对照 |
| [tutorial/rk3568/02_peripherals](../../tutorial/rk3568/02_peripherals.md) | Goodix 触摸、RTC、CAN 板验素材 |
