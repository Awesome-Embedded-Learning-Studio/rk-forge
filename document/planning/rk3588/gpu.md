---
title: "GPU 高级选修（RK3588 线）"
---

# GPU 高级选修

> RK3588 线 · GPU 高级选修 · 选修第 1–3 章 · [返回线总览](index.md)
>
> GPU 不作为所有学习者的必修，也不在软件栈版本未确认时承诺具体开源驱动状态。

### 第 1 章：Mali-G610 软件栈边界

一句话：先建「GPU 软件栈四层」通用模型，再讲 Mali-G610 的关键判断——**开源栈成熟度以实施时主线/Mesa 为准，不预设**。

要点：

- 四层：应用 API / 用户态驱动（Mesa 或闭源）/ 内核 DRM 驱动 / GPU 固件（签名 blob）
- 主线与厂商两条内核驱动路线（kbase vs Panfrost/Panthor）
- 固件是 blob：版本必须与内核驱动匹配；rk-forge 最小化 blob 策略见 blobs.md
- Mesa 开源栈与厂商闭源栈的取舍（可调试可同步 vs 性能与版本绑定）
- OpenGL ES（简单跨平台）vs Vulkan（低开销显式同步）的选择
- **Panthor/Panfrost/PanVK 适用关系**：Panfrost 不支持 Valhall；Panthor 针对 Valhall（含 G610）；mainline-first 选 Panthor+PanVK，产品级可能需 fallback Arm 官方栈

实践：
- 查板上 GPU 栈出「身份卡」（驱动/Mesa/固件/用户态库）
- 开源栈 vs 厂商栈同测对比；跑公开 benchmark 建性能基线；评估是否满足产品需求

### 第 2 章：渲染、同步与显示

一句话：GPU 渲染怎么输出到屏幕——swapchain、显式同步、渲染到 DRM 的零拷贝衔接。

要点：

- EGL 是 OpenGL ES 与窗口系统的桥；导入 dma-buf 作 EGLImage 是零拷贝渲染关键
- Vulkan swapchain 显式管理 buffer；FIFO/MAILBOX/IMMEDIATE 三模式
- **显式同步是 Vulkan 核心**：semaphore（GPU 内）/ fence（GPU→CPU），底层映射 drm_syncobj/dma_fence
- 渲染输出 dma-buf 直设 DRM plane framebuffer，atomic 提交零拷贝；modifier 不匹配要 RGA 转 linear
- 异步执行的代价：CPU 不能假设提交完就是渲染完；**不等 fence 复用 buffer = 数据竞争**

实践：
- 最小 OpenGL ES（EGL+dma-buf）与最小 Vulkan 程序各一，对比 CPU/FPS/延迟
- 故意错误时机读 buffer 观察竞争；dma-buf import 渲染摄像头帧验证零拷贝链

### 第 3 章：GPU compute 与 profiling

一句话：GPU 也是通用并行计算引擎——适合什么任务、与 CPU/NPU 怎么分工、**瓶颈要量出来不是猜出来**。

要点：

- 适合 GPU：数据并行/计算密集/访存规律；不适合：控制流密集/小数据/强串行
- CPU vs GPU vs NPU 三方分工：NPU 单位功耗最优、GPU 最灵活、CPU 小任务最快；典型组合 NPU 主网络 + GPU 后处理
- profiling 工具：Mesa（GALLIUM_HUD）、Arm Mobile Studio、perf/ftrace
- 四类瓶颈（吞吐/延迟/同步/内存）对应完全不同的优化方向；**盲优化往往无效甚至反向**
- 综合优化看全局：瓶颈可能是 GPU、带宽或 CPU 提交开销，不能孤立看 GPU

实践：
- 与 CPU 对照的 compute 任务（矩阵乘/高斯模糊），多维度指标对比
- 用 profiler 定位瓶颈并实施针对性优化
- NPU+GPU 组合用 dma-buf 共享验证零拷贝；写「CPU vs GPU vs NPU 任务选择决策表」

### 选修附录：仿真方法论

- QEMU lite 机器的研究边界声明：仿真证明软件控制流与指令集执行，**不证明时钟/电源/PHY/DDR/显示时序**——结论标明「仿真取证」，升真板证据才改 verified；
- 方法论要点：同一 DTB 宪法（仿真与真机逐字节一致）、snapshot 投票、扫描输出/AFBC 读侧这类可仿真验证的子问题优先在 sim 里打样，再到板上闭环；
- 素材已在表（sim 研究线），本附录只立方法边界，不立章。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [tutorial/rk3588/03_gpu](../../tutorial/rk3588/03_gpu.md) | Panthor 板验强锚点（固件内嵌、GNOME 桌面） |
| panthor 笔记 82–116（M0→M2n 全链战役：[110 真壁纸全屏](../../notes/110-2026-09-11-panthor-m2n-true-wallpaper-fullscreen.md)、[116 收官](../../notes/116-2026-09-12-panthor-m2n-wallpaper-visible-achieved.md) 等） | 第 2 章渲染/同步的完整实战现场，含被推翻的判断 |
| [notes/48（GPU 固件内嵌与 GNOME 桌面）](../../notes/48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md) | 第 1 章固件边界素材 |
| sim 研究线（[boards/rk3588-topeet/sim/](../../../boards/rk3588-topeet/sim/)） | GPU 仿真取证（M2n 扫描输出/AFBC 读侧等） |
| eai 仓互指 | Panthor 与 Mesa 开源栈调研在 eai A5.3，板侧验证在此 |
| books/RK3588 的多屏显示目录 | 显示通路参考（`.claude/books/`，本地资料） |
