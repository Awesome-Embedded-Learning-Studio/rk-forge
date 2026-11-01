---
title: "RK3588 教学路线：异构计算、媒体与产品工程"
---

# RK3588 教学路线：异构计算、媒体与产品工程

> 状态：**partial**。RK3588（迅为 iTOP-RK3588 EVB，eMMC）已真机 boot 到 Ubuntu 26.04 GNOME 桌面：主线 kernel 7.1 + 主线 U-Boot 2026.07 + 主线 SPL（规避 vendor SPL/BL31 基址错配 bootloop），Panthor Mali-G610 GPU（固件内嵌）、LCD DSI→LVDS 1024×600（TC358775）出图、GT911 触摸轴映射已修、eMMC HS400、PMIC rk806 均板上验证。课程化仍在进行；LCD 的 VOP2 hard-lock 修复当前为候选镜像，连续冷/热启动稳定性验证未闭环，故不写成稳定支持；WiFi（rtw88_8723du，主线 rtw88）已板验——关联+DHCP 通、2.4G 单频；BT、NPU（主线 Rocket）、VPU、摄像头仍属 roadmap。

## 1. 路线承诺

RK3588 路线不以“运行厂商 demo”为终点，也不要求所有学习者同时掌握 NPU、GPU、媒体和 Android。

它先用一组公共必修课建立复杂 SoC 所需的共同基础：

- big.LITTLE 和持续性能；
- ATF、OP-TEE 与复杂启动链；
- 64 位内存、CMA、IOMMU/SMMU；
- dma-buf、同步和跨设备数据共享；
- DRM/KMS、V4L2、MPP、RGA 的数据流水；
- 功耗、温控、性能和长期稳定性。

随后只选择一个方向深入：

- AI/NPU；
- 媒体；
- Android；
- GPU 作为高级选修。

完成本路线后，学习者应从“会调用一个加速器”提升为“能够设计、测量和交付异构数据流水的系统/产品工程师”。

## 2. 平台角色与边界

| 项目 | 本路线定义 |
|---|---|
| 目标 SoC | Rockchip RK3588，ARMv8-A / AArch64 |
| 具体开发板 | 迅为 iTOP-RK3588 EVB（eMMC） |
| CPU | Cortex-A76/A55 big.LITTLE，具体拓扑以真板和官方资料确认 |
| 主角色 | 高性能 Linux、媒体、AI、Android 和产品化 |
| 公共重点 | ATF/OP-TEE、内存、SMMU、dma-buf、性能、功耗、DRM/V4L2/MPP/RGA |
| 方向重点 | AI、媒体、Android 三选一；GPU 高级选修 |
| 不承担 | 通用字符设备和基础驱动的完整入门；RK3506B 存储可靠性主课 |

RK3588 与 RK3568 可以共享 AArch64 和 Linux 驱动方法，但不得默认共享工具链配置之外的任何固件、设备树、模块、镜像或真板结论。

## 3. 适合谁学习

建议已经具备：

- AArch64、Linux 启动链和设备树基础；
- Linux 驱动模型；
- 中断、DMA 和 cache 一致性概念；
- C/C++ 用户态系统编程；
- 能使用 Git、构建系统和日志工具；
- 至少完成过一个真实外设或 BSP 项目。

如果直接进入 RK3588，必须先通过以下自测：

1. 能解释 EL1/EL3、ATF 和 PSCI；
2. 能区分虚拟地址、物理地址和 DMA 地址；
3. 能读懂设备树中的 clock/reset/interrupt/iommu；
4. 能独立分析一次 driver probe 失败；
5. 能使用 ftrace 或 perf 获取基本性能证据；
6. 能严格隔离 AArch64 的 sysroot、rootfs、模块和应用产物。

未通过者应先完成 RK3568 对应章节或共享前置课。

## 4. 课程结构

```text
卷一 平台与启动
  ↓
卷二 内存、SMMU 与 dma-buf
  ↓
卷三 调度、功耗与持续性能
  ↓
卷四 DRM/V4L2/MPP/RGA 公共媒体地基
  ↓
选择一个主方向（方向内章节独立编号）
  ├─ AI/NPU 方向
  ├─ 媒体方向
  └─ Android 方向

GPU 高级选修为独立卷，可与主方向组合，但不是结课必需。
```

公共必修解决“多个处理单元如何共享内存和协作”；方向课程解决“如何形成一项完整产品能力”。

| 卷 | 章 | 主题 | 状态 |
|---|---|---|---|
| [卷一：平台、启动与安全边界](01-platform-boot.md) | 第 1–2 章 | 异构 SoC 全景、启动链/ATF/OP-TEE 与分区 | 🟡 partial — 真机 boot 已验 |
| [卷二：内存、IOMMU 与跨设备共享](02-memory-iommu.md) | 第 3–5 章 | 64 位内存/CMA、SMMU、dma-buf/fence/零拷贝 | ⚪ planned |
| [卷三：big.LITTLE、功耗与持续性能](03-biglittle-power.md) | 第 6–8 章 | 调度/DVFS、thermal、性能取证 | ⚪ planned — DVFS/稳定性有真板素材 |
| [卷四：显示、摄像头与媒体公共地基](04-media-foundation.md) | 第 9–13 章 | DRM/KMS、V4L2/ISP、MPP、RGA、端到端流水线 | 🟡 partial — LCD/GPU 板验；VOP2 hardlock 未闭环，摄像头未接 |
| [AI/NPU 方向](ai-npu.md) | 方向第 1–5 章 | RKNN 工具链、量化校准、推理后处理、实时流水线、AI 服务 | ⚪ planned — NPU 未板验 |
| [媒体方向](media.md) | 方向第 1–5 章 | 编解码与数据格式、MPP—RGA—DRM、采集编码、多流背压、媒体服务 | ⚪ planned — VPU/摄像头未接 |
| [Android 方向](android.md) | 方向第 1–6 章 | AOSP 与分区、init/SELinux、HAL、人机交互、Camera/MediaCodec、产品化 | ⚪ planned — SDK 版本未定 |
| [GPU 高级选修](gpu.md) | 选修第 1–3 章 | Mali-G610 软件栈、渲染同步、compute 与 profiling | 🟡 partial — Panthor 桌面板验通 |
| [毕业项目](capstone-projects.md) | — | RKNN 边缘 AI 盒、MPP/RGA/DRM 媒体设备、智能屏/Android 终端 | ⚪ planned |

> 状态按全仓四档口径标注（见[三板教学路线](../index.md)）。各方向章节独立编号，引用时带方向名，如「AI/NPU 方向 · 第 3 章」。

## 5. 结课标准

所有方向共同要求：

1. 解释 RK3588 启动链和固件边界；
2. 解释 CPU、DMA、IOMMU 和 dma-buf 地址/生命周期；
3. 完成一条至少跨两个硬件模块的数据流水；
4. 给出复制次数、帧率、端到端延迟、CPU、内存和温度证据；
5. 分析并修正一个真实瓶颈；
6. 验证错误输入、停止重启和资源回收；
7. 保存软件栈版本、配置、日志、测试方法和限制；
8. 完成 AI、媒体或 Android 中一个毕业项目最小版本。

方向附加要求：

- AI：同时提交精度和性能报告；
- 媒体：同时提交格式、同步、掉帧和长期运行报告；
- Android：提交 kernel—HAL—Framework—App 证据和升级/回滚方案；
- GPU 选修：提交厂商/开源栈边界和 CPU/GPU 对照数据。

## 6. 硬件和方向确认门

以下事项中，开发板（iTOP-RK3588）、DRAM、eMMC、调试串口、以太网、显示（DSI→LVDS）、GPU（Panthor）和触摸已在真板确认；其余仍待确认的，相应内容保持 `planned` 或 `blocked`：

- 具体 RK3588 开发板和 PCB 版本；
- DRAM、eMMC、SD、NVMe 等存储配置；
- 调试、烧录和恢复方式；
- 显示接口和具体显示设备；
- 摄像头 sensor、模组、镜头、连接方式和 IQ 文件；
- Android/Rockchip SDK 版本；
- Linux、U-Boot、ATF、OP-TEE、MPP、RGA、RKNN、GPU 栈版本；
- 可使用的散热方案和电源；
- 主攻 AI、媒体或 Android 中哪一条；
- 真板数量和长期稳定性测试条件。

## 7. 明确不讲或推迟

- 不把 RK3588 写成稳定/完整支持——当前是 `partial`（真机 boot 到 GNOME 桌面 + GPU/LCD/触摸板验，WiFi 已板验），但 VOP2 hard-lock 修复仍是候选镜像、BT、NPU/VPU、摄像头未接，连续冷/热启动稳定性验证未完；
- eMMC 烧录与量产链深讲不入本线——工具操作按仓库 QUICK_START，量产课题暂缓（与 RK3568 同口径）；
- 开发板和主要配套硬件已确认（iTOP-RK3588 + LCD/触摸），DTS/镜像布局见 [boards/rk3588-topeet/](../../../boards/rk3588-topeet/)，但摄像头、Android 等未确认方向不写结论；
- 不把运行厂商 demo 计为课程完成；
- 不要求同时推进 Linux、Android、GPU、NPU、媒体和摄像头；
- 不默认把所有 RK3588 硬件能力纳入课程；
- 不重复 RK3568 的完整字符设备和通用驱动基础；
- 不承诺未核实的 codec、GPU、NPU 或摄像头能力；
- 不把峰值跑分当作产品性能；
- 不执行缺少恢复和密钥治理的不可逆 secure boot 操作；
- 不把 CFDesktop 界面完成等同于底层产品闭环。
