---
title: "卷二：内存、IOMMU 与跨设备共享"
---

# 卷二：内存、IOMMU 与跨设备共享

> RK3588 线 · 卷二 · 第 3–5 章 · [返回线总览](index.md)

### 第 3 章：64 位内存、CMA 与高带宽 buffer

一句话：异构 SoC 上内存是所有 IP 共抢的资源——三种地址、CMA、一致性映射、**带宽账本永远先于跑分**。

要点：

- 三种地址分清（用户 VA / 内核 VA / 物理），靠页表与 `__pa`/`__va` 转换；「用户态拿物理地址直接 deref」是经典 bug
- CMA 的理由：DMA 要物理连续而 kmalloc 会碎片化；VPU/RGA 大量用 CMA
- coherent（常驻 buffer 免 flush）vs streaming（显式 sync）；选择标准一句话：长期被设备持有 → coherent，寿命短方向交替 → streaming
- 高分辨率内存体积：多路 4K + 三缓冲 → 数百 MiB buffer 池；**少一次拷贝就少几十 MiB/s 带宽**
- stride/alignment/cache 行细节：不按 stride 算就画面斜掉（新手花屏真因）
- 带宽账本：分辨率×帧率×字节数×拷贝次数加总超出 DDR 持续带宽就掉帧

实践：
- 读 `CmaTotal/CmaFree` 与 `dma_buf/bufinfo` 统计
- 算 4K 全链路不同拷贝次数的带宽对照表
- 制造大块连续分配失败观察报错；实测 memcpy vs 设备直访的吞吐与 CPU 占用

### 第 4 章：IOMMU/SMMU 与设备隔离

一句话：设备怎么访问内存——隔一层 SMMU 翻译；**理解它是写 RK3588 驱动和定位 DMA bug 的分水岭**。

要点：

- 为什么需要 IOMMU：无它则 DMA 能读写任意物理内存；有它则越界访问变明确 fault 而不是幽灵 bug
- stream ID 区分设备；设备树 `iommus` 绑 SID 与 SMMU 实例——「VPU 好好的 ISP 一上就 fault」= SID 绑错/漏绑
- SMMU 页表独立于 CPU 页表；TLB 与 use-after-free（刚 unmap 设备还在写）
- IOMMU group 与 vfio 隔离；漏配 `iommus` 的典型表现 = probe 过但 DMA 全 fault
- 三类 fault 对应三类代码 bug；`dmesg | grep -i smmu` 是金矿
- **设备看到的地址 ≠ CPU 物理地址**；绕过 DMA API 直接写物理地址几乎必然 fault

实践：
- 枚举 iommu_groups 画拓扑图
- 跟踪一次 buffer 的 IOMMU 绑定全链
- 故意制造一次 fault 并解析类型与地址；画地址翻译路径图

### 第 5 章：dma-buf、fence 与零拷贝

一句话：让多个 IP **不拷贝地共享同一块 buffer**——RK3588 平台工程的核心，「4K 多路跑得动」的底层答案。

要点：

- dma-buf：exporter 管物理页，importer 经 fd 引用，物理页从头到尾一份
- mmap 前后必须包 `begin/end_cpu_access` 同步——最常见使用 bug
- fence 两种语义：implicit（驱动自动，简单）vs explicit（sync_file，表达力强）；Vulkan/DRM atomic 走 explicit
- 五个 IP 的共享入口要记住（DRM PRIME / V4L2 EXPBUF / MPP / RGA / NPU）——fd 全程流转就是实时流水线骨架
- **零拷贝的真与伪**：三种常见伪装（驱动内部拷、用户态 memcpy、cache flush 等效搬运）；用 bufinfo/perf/CPU 占用验证，不验证别信

实践：
- 跟踪一帧经过 ≥2 个硬件模块，bufinfo 确认同页共享
- 记录 buffer 完整生命周期与同步点
- 实测拷贝 vs 共享四列对比（延迟/CPU/带宽）；找一个伪零拷贝案例三方取证

阶段产出：跨设备 buffer 生命周期图、零拷贝对照实验报告。

## 素材与取证

| 资产 | 用途 |
|---|---|
| [notes/27（SFC 读 bug：DMA 与 cache）](../../notes/27-2026-06-20-loader-weakwrite-overturned-linux-sfc-read-bug-dma.md) | 第 3 章 cache 一致性的跨板真实案例 |
| [RK3568 线 · 卷五](../rk3568/05-dma-highspeed.md) | DMA 基础课对照，本卷叠加 IOMMU 与 dma-buf |
| [sdk-diff-rk3588.md](../../sdk-diff-rk3588.md) | SMMU/dma-buf 相关的 vendor 与主线差距 |
| books/RK3588 的原厂文档 | SMMU/IOMMU 硬件事实（`.claude/books/`，本地资料） |
