---
title: "卷五：DMA 与高速接口"
---

# 卷五：DMA 与高速接口

> RK3568 线 · 卷五 · 第 14–17 章 · [返回线总览](index.md)

### 第 14 章：DMAengine 与 cache 一致性

一句话：基础驱动到中高级的分界章——三种地址 + cache 一致性，后面 USB/PCIe/网络都建在它之上。

要点：

- **三种地址必须分清**：CPU 虚拟 / 物理 / DMA 总线地址；IOMMU 存在时设备地址 ≠ CPU 物理地址；**把 DMA 地址当物理地址用是入门级 bug**
- coherent（常驻 buffer，免 flush）vs streaming（一次性传输，显式 sync）；选错就漏 flush 或白 flush
- scatter-gather 是大块传输正确姿势
- 非一致域必须显式 sync；错误同步的现象：读到旧数据 / 写丢失
- DMAengine 客户端接口：prep → issue_pending → 回调；cyclic 用于音频

实践：
- 完成 DMA 传输，对比 PIO/DMA 的 CPU 占用与吞吐
- 制造错误映射/同步，分析现象；trace/perf 记录数据通路

### 第 15 章：USB（硬件确认门内）

一句话：host/device/OTG 三种角色与 DWC3 框架——**具体实验须等 USB2/USB3、Type-C 与角色确认**。

要点：

- host/device/OTG 角色与 Type-C 的 DRP/方向
- DWC3 双模控制器 + dwc3-of-simple 平台层；PHY 初始化时序是起来的前提
- 枚举流程与四种传输类型（control/bulk/interrupt/isochronous）
- gadget：configfs 动态组装（mass_storage/ncm/acm）
- usbmon + Wireshark 是协议问题终极手段

实践候选：host 枚举与压力测试、gadget 网络/存储、热插拔与错误恢复。

### 第 16 章：PCIe 与 NVMe（硬件确认门内）

一句话：高速串行总线框架——**仅在有可用 PCIe 接口与配套设备时进入主线**。

要点：

- Root Complex / Endpoint 与 bus/device/function 三级寻址
- 配置空间、BAR、**MSI/MSI-X**（高速设备必须用）
- vendor/device id 匹配；链路训练失败 = 探测不到或降速
- NVMe 的 submission/completion queue 让吞吐远超 SATA/USB

实践候选：枚举设备查 BAR/IRQ、跑存储/网络吞吐、分析链路降速。

### 第 17 章：GMAC、PHY 与网络性能

一句话：以太网是嵌入式命脉——MAC/PHY/MDIO、NAPI、性能调优；双 GMAC 已板验。

要点：

- 四件套 MAC/PHY/中间接口/MDIO；**PHY 自协商失败落低速半双工**是「link up 却很慢」真因
- descriptor ring + **NAPI（中断+轮询混合）**是高负载吞吐关键
- ethtool/phylib 管链路
- 吞吐/丢包/IRQ 分布三件套：iperf3、`ethtool -S`、`smp_affinity` 绑核

实践：
- 链路配置与恢复、TCP/UDP 吞吐测试
- CPU 占用、IRQ 分布、丢包分析；长时间网络稳定性

## 素材与取证

| 资产 | 用途 |
|---|---|
| [notes/27（SFC 读 bug：DMA 与 cache）](../../notes/27-2026-06-20-loader-weakwrite-overturned-linux-sfc-read-bug-dma.md) | 第 14 章真实案例 |
| [tutorial/rk3568/02_peripherals](../../tutorial/rk3568/02_peripherals.md) | 双 GMAC 已板验的网络素材 |
| [boards/rk3568-atk/patches/linux/](../../../boards/rk3568-atk/patches/linux/) | rtl8852bs WiFi 接线补丁（0001 wire + 0002 forge-adapt），真机验证待做 |
| 协议仓互指 | 第 15 章与协议仓 U5（USB）互指 |
| books 的 RK3568 用户手册 | 高速接口资源核对 |
