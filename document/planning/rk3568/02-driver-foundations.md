---
title: "卷二：Linux 驱动地基"
---

# 卷二：Linux 驱动地基

> RK3568 线 · 卷二 · 第 5–7 章 · [返回线总览](index.md)

### 第 5 章：字符设备与内核接口

一句话：驱动第一课——file_operations、用户态/内核态边界、并发同步；**字符设备只是训练场，不是真实驱动的最终形态**。

要点：

- 模块生命周期：init/exit、module_param、EXPORT_SYMBOL；modprobe 处理依赖而 insmod 不能；vermagic 绑死内核版本
- 主次设备号申请与 cdev 注册；`file_operations` 是灵魂，`copy_to/from_user` 是数据边界（直接 deref 用户指针 = 漏洞 + oops）
- 设备节点：class_create/device_create + devtmpfs 自动建，取代手动 mknod
- 同步原语按上下文选：中断上下文只能自旋锁，进程上下文才能互斥；wait_queue/completion 处理等事件
- ioctl 命令编号约定、poll/select、fasync 异步通知——用户态控制驱动三件套
- **错误路径与资源管理是驱动质量的分水岭**：`devm_*` 自动释放、goto 链回滚、后申请先释放

实践：
- 写支持阻塞/非阻塞 + poll 的字符设备，加并发压力测试
- 故意制造 probe 中段失败，验证资源零泄漏

### 第 6 章：设备模型与 platform driver

一句话：从「自己注册自己管」到设备模型——bus/device/driver/class 框架，SoC 内部外设都挂 platform bus。

要点：

- 设备模型积木与引用计数（kobject 基类）；sysfs 是对用户态的投影
- platform bus 是「非枚举式总线」的统一抽象；probe/remove 是核心，`compatible` 匹配
- `platform_get_resource`/`platform_get_irq` 取资源；`devm_*` 系列是资源管理正确姿势
- **`-EPROBE_DEFER` 的语义**：依赖未就绪等会儿再试；remove 与 probe 对称
- 设备模型支撑 udev、电源管理、runtime PM——后面都建在它之上

实践：
- 把第 5 章字符设备改造成 platform driver，从 platform resource 取寄存器与 IRQ
- 验证 probe 失败/defer/remove；画设备模型对象关系图

### 第 7 章：设备树绑定与资源建模

一句话：设备树怎么写、驱动怎么从 DT 读资源、binding 文档为什么必须上游化。

要点：

- `compatible` 两段式匹配 + `of_match_table`；标准五件套 reg/interrupts/clocks/resets/supplies，phandle 是 DT 的「指针」
- `.dtsi`（SoC 固有）与 `.dts`（板级）分工；板级可覆盖 `.dtsi`（status/pinctrl-0/bus-width）
- `of_property_read_*`/`of_iomap`/`of_irq_get`/`of_clk_get`——DT 数据到 probe 的数据流
- YAML binding + `dtbs_check` 校验；**没有 binding 文档的驱动进不了主线**

实践：
- 为实验设备写/整理 binding 节点并从 DT 读属性
- 故意缺 clock/irq 分析 probe 结果；跑静态 DT 校验

阶段产出：结构规范的 platform driver + DT 节点 + 用户态验证工具与测试记录。

## 素材与取证

| 资产 | 用途 |
|---|---|
| PenguinLab layer-0 内核模块入门两篇（QEMU + 9p 共享） | 先行教材：机制学习不占板（近邻仓互指） |
| PenguinLab document/guides/04 模块构建指南 | 配套 |
| [tutorial/rk3568/02_peripherals](../../tutorial/rk3568/02_peripherals.md) | 板级八子系统真板素材（DT 待 P4 patch 化） |
| devtree-journey | 设备树机制纵深专题互指（近邻仓互指） |
| books 的 RK3568 用户手册 | 外设资源核对 |
