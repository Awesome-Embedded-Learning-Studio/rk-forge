---
title: "RK3588 教学路线：异构计算、媒体与产品工程"
---

# RK3588 教学路线：异构计算、媒体与产品工程

> 状态：**partial**。RK3588（讯饶 iTOP-RK3588 EVB，eMMC）已真机 boot 到 Ubuntu 26.04 GNOME 桌面：主线 kernel 7.1 + 主线 U-Boot 2026.07 + 主线 SPL（规避 vendor SPL/BL31 基址错配 bootloop），Panthor Mali-G610 GPU（固件内嵌）、LCD DSI→LVDS 1024×600（TC358775）出图、GT911 触摸轴映射已修、eMMC HS400、PMIC rk806 均板上验证。课程化仍在进行；LCD 的 VOP2 hard-lock 修复当前为候选镜像，连续冷/热启动稳定性验证未闭环，故不写成稳定支持；WiFi/BT、NPU（主线 Rocket）、VPU、摄像头仍属 roadmap。

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
| 具体开发板 | 讯饶 iTOP-RK3588 EVB（eMMC） |
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
H0 平台与启动
  ↓
H1 内存、SMMU 与 dma-buf
  ↓
H2 调度、功耗与持续性能
  ↓
H3 DRM/V4L2/MPP/RGA 公共媒体地基
  ↓
选择一个主方向
  ├─ N：AI/NPU
  ├─ M：媒体
  └─ D：Android

G：GPU 为独立高级选修，可与主方向组合，但不是结课必需。
```

公共必修解决“多个处理单元如何共享内存和协作”；方向课程解决“如何形成一项完整产品能力”。

## 5. 公共必修

## H0：RK3588 平台、启动与安全边界

### 第 1 章：RK3588 异构 SoC 全景

RK3588 是一颗“很多 IP 挤在一块硅上”的异构 SoC——CPU 有 big.LITTLE 两簇，外加 GPU、NPU、VPU、RGA、ISP 五个加速器。这一章先建立整张图的直觉：每个 IP 干什么、它们怎么共享内存、为什么“峰值跑分”在这颗芯片上特别骗人。rk-forge 已在 iTOP-RK3588 上建起真板 target（主线 boot 到 GNOME 桌面 + GPU/LCD/触摸板验），核数、拓扑、加速器版本以真板和官方资料为准，具体 pinout 和镜像布局见 [board/rk3588-topeet/](../../board/rk3588-topeet/)。

**CPU 是 big.LITTLE，A76 加 A55，这是异构的起点。** 大核（A76）冲峰值 IPC、小核（A55）冲能效，同一份任务放在不同核上，功耗和延迟能差出几个量级。这就是"异构"的核心——不是"核多"，是"核不一样"。`capacity`、`freq-domain`、`cluster` 这些拓扑事实能从 `/sys/devices/system/cpu/` 读出来，要和调度器口径对齐。**同一份 AArch64 ISA、不同微架构、不同私有 cache 和共享 LLCC**——这意味着"代码能跑"和"代码能跑得稳"是两件事：大小核之间迁移时的 cache 抖动，能让延迟尖峰翻几倍（H2 会展开）。

**五个加速器各管一摊，理解分工是平台工程的起点。** GPU（Mali-G610）= 可编程并行，3D/Compute/通用 GPGPU；NPU = 固定结构 CNN 加速；VPU/MPP = 视频 codec；RGA = 2D 几何与色彩；ISP = sensor RAW → YUV。**SoC 把它们做成独立 IP，不是炫技**——每个 IP 的访存模式、数据格式、带宽需求都不一样，复用 CPU 反而劣化。平台工程师的核心判断就是"哪个任务该往哪个 IP 送"。但反过来也要知道**哪些任务不该送加速器**：小数据量、控制流密集、API 调用开销大于计算本身的，留在 CPU 反而更省——把一个 1ms 的逻辑判断丢给 NPU，光 ioctl 和 fence 等待就比算本身还久。

**cache 和一致性域，决定你写驱动要不要显式 flush。** L1/L2 是每个核/IP 私有的，LLCC（Last-Level Cache）是共享的；DMA 走不走 LLCC 直接影响带宽可用量。更关键的是系统级一致性：CPU cluster、GPU、NPU 之间是不是经过同一套 cache/coherent fabric。**"coherent" 和 "not coherent" 对驱动写法是两码事**——一致域里的设备，`dma_alloc_coherent` 给的 buffer 不用显式 flush；非一致域（RGA/VPU/ISP 这类 IP 经常位于此，看主桥设计）就必须显式 `sync_to_device`/`sync_to_cpu`。搞不清设备在哪个域，要么漏 flush（数据脏）要么白 flush（带宽浪费）。

**数据格式、stride、alignment，是这章最容易栽的细节。** 一帧 4K NV12 不是 `4096×2160×1.5 = 12.6 MiB` 这么简单——硬件要求 stride 按 16/32/64 字节对齐，一行末尾有 padding；tile/linear modifier 一变，实际占用和访问模式全变。**同一帧从 CPU 拷到 GPU 再拷到 NPU，是几次带宽消耗**——这是"零拷贝"问题的起点（H1 第 5 章展开）。在 RK3588 这种多 IP 抢同一根 DDR 的平台上，内存带宽是有限物理资源：4K@60 解码 + ISP 输入 + DRM 显示 + NPU 推理叠加时，**先饱和的往往是带宽而非算力**。

**最后一句反直觉的：峰值算力 ≠ 应用性能。** TOPS、GFLOPS、pixels-per-second 这些厂商标称值，口径都是"峰值、持续不到、单一 IP 满载、其它 IP 闲置"——你能跑出这个数的条件，真实产品里几乎不存在。持续性能受三件事钳制：热（H2 第 7 章）、内存带宽（本章）、跨 IP 同步开销（H3 第 13 章），**任何一项先饱和，峰值跑分就掉下来**。工程上的规矩：永远先量持续性能（稳态 30 分钟以上）再谈峰值；产品指标是"用户体感"，不是跑分单点。把跑分当产品性能汇报，是新手最容易犯的错。

实践：
- 用 `lscpu`、`/sys/devices/system/cpu/cpu*/cpufreq/`、`/sys/devices/system/cpu/cpu*/topology/` 建一张完整 CPU 拓扑表，标每个核的 capacity、最高频、所属 cluster。
- 画一张 RK3588 的"数据流图"：CPU↔GPU↔NPU↔VPU↔RGA↔ISP↔DRAM 的连接，标出哪些真直连、哪些要经 DRAM 中转。
- 列出 SoC 上每个加速器的"内核驱动名 / 固件来源 / 用户态栈名 / 版本"，每行标 rk-forge 是否已建 target——这是后续所有章节的参照原点。

保存证据：
- 硬件与软件栈清单（CPU/加速器拓扑 + 各驱动/固件版本）；
- SoC 数据流图；
- 真板基线日志（一次完整启动 + 一段空载 + 一段满载）——RK3588 待建 target 后补。

### 第 2 章：启动链、ATF、OP-TEE 与系统分区

RK3588 的启动链比 RK3506B/RK3568 都复杂——多核异构、OP-TEE 默认在线、加速器固件要加载。这一章把整条链拆开，重点讲信任边界在哪里、secure boot 的不可逆风险、以及 Linux 和 Android 两条启动路径的差异。

**链结构：BootROM → loader → ATF → OP-TEE → U-Boot → Linux。** 每段职责：BootROM 点活最小存储、loader（DDR init/SPL）训练 DDR、ATF（BL31）做 runtime secure monitor、OP-TEE 提供 TA 运行环境、U-Boot 做通用 bootloader、Linux 进入 EL1。**闭源段（BootROM、`rkbin` 的 DDR init/loader blob）和开源段（ATF、U-Boot、Linux）的分界**，RK3588 和 RK3506B 一样画在 rkbin 之后（详见 [blobs.md](../blobs.md)）——rk-forge 用最小化 blob + 主线 ATF/U-Boot。要画出"信任链移交图"：哪一步切异常级、哪一步开始有 console、哪一步把控制权完全交给开源代码。

**secure boot 的不可逆风险，这一节是整章最该敬畏的。** 信任根是 BootROM（不可改），每段固件被上一段验证；ATF 管 ROTPK/RoT、U-Boot 验 boot image 签名、Linux 可选 module signature。但**一旦把 efuse 烧成"强制验签 + 关闭 JTAG"，丢失私钥的板子永远救不回来**——这是物理上不可逆的操作。rk-forge 的态度很硬：**在缺少完整密钥治理 + 恢复方案 + 双套密钥（dev/prod）这三项时，绝不执行 secure boot 烧 efuse**。教学范围只到"理解原理、读 ATF 验签代码、分析失败日志"，绝不在真板上做不可逆操作。这一条不是建议，是红线。

**分区三角色 + A/B 升级，是现代嵌入式/Android 设备的标准布局。** boot（kernel+dtb+ramdisk）、rootfs（系统）、vendor（厂商二进制/固件）这三个角色为什么分开？因为**升级粒度、签名主体、回滚策略都不同**——boot 升级只换内核，vendor 升级只换厂商 blob，rootfs 升级换系统；签名上 boot 可能签名、rootfs 不签名，各管各。A/B 双分区（boot_a/boot_b）的意义：升级写另一槽、重启切换、失败自动回滚——这是 Android / IOTA / Mender 的共同模式，也是 RK3588 这种"要长期维护的产品级板"该走的路。recovery 分区/模式是兜底入口：正常启动走不通时，要有"正常 / 恢复 / 升级"三条路径，对应不同 bootcmd 和按键组合。

**Linux 和 Android 在同一块板上，启动链差异巨大。** Linux：U-Boot → Linux → init（systemd/busybox）→ 用户态，bootargs 在 `/chosen`。Android：bootloader → kernel（GKI）+ ramdisk（vendor_boot）→ init → Zygote → System Server → Launcher，分区模型、init 行为、SELinux 强制模式都和 Linux 发行版不同（D 方向 D1/D2 展开）。**同一块板、同一份 ATF，但 Linux 路径和 Android 路径的 U-Boot bootcmd、kernel config、分区布局差异巨大**——理解这条差异，才能避免"在 Linux 上跑通的假设照搬到 Android"这种常见翻车。

**和另两块板的对照：同样 AArch64，但不共用任何产物。** RK3568 的启动链（见 [RK3568_ROADMAP](RK3568_ROADMAP) §A0）是理解 RK3588 的基线，RK3588 多了 OP-TEE 默认在线、加速器固件加载、多核更复杂。RK3506B 是 ARMv7-A 32 位（无 ATF），和 RK3588 的 ARMv8-A EL0-EL3 模型不同。**三者不得共用 U-Boot/ATF/DT/镜像**（回到 [planning 总纲](./) 的硬边界）——主线源码 + 补丁库 + `forge` 编排器是三块板共用的实现路径（见 [tutorial/](../tutorial/)），但 SoC-specific 部分（DT、DDR、blob）各板独立。

实践：
- 拿一份完整启动日志（BootROM → ATF → U-Boot → Linux earlycon → 用户态）逐行标注阶段，把版本号映射回源码 pin（ATF/U-Boot/Linux commit + `rkbin` blob 版本）。
- 画一张分区表：每个分区的角色、大小、文件系统、是否 A/B、谁签名、升级粒度；和 U-Boot `bootcmd` 一一对应。
- 验证恢复入口：U-Boot 下中断、用环境变量切到 recovery/upgrade 路径，确认能进能回；**只读不改，不碰 efuse**。
- 分析一次启动失败案例（ATF 验签失败、kernel panic、rootfs 找不到），形成"日志 → 原因 → 恢复步骤"对照表。

本课程不在缺少密钥治理和恢复方案时执行任何不可逆 secure boot 操作（烧 efuse、关闭 JTAG、关闭回滚）。

## H1：内存、IOMMU 与跨设备共享

### 第 3 章：64 位内存、CMA 与高带宽 buffer

异构 SoC 上，内存是所有 IP 共抢的资源，理解它比理解任何一个加速器都重要。这一章讲清三种地址、为什么 DMA 老要"连续内存"、coherent 和 streaming 的差别、以及为什么 RK3588 上"带宽比算力先饱和"。

**先把三种地址分清，这是入门最该花的一节课。** 用户进程看到的是 `mmap` 返回的虚拟地址；内核 `kmalloc`/`vmalloc` 返回内核虚拟地址；物理地址只在 `/proc/iomem`、`/proc/physmem` 层面有意义。三者靠页表（CPU 看到的）、`__pa`/`__va`（内核内部）、IOMMU 页表（设备看到的，第 4 章展开）转换。**混用就会写出"在用户态拿到物理地址就直接 deref"这种经典 bug**——内核地址和用户地址不是同一个空间，物理地址更不是你想 deref 就能 deref 的。64 位下地址空间"宽到不真实"：用户态 48 或 52 位 VA、内核线性映射覆盖全部物理内存，大块 buffer 不再像 32 位那样挤——这也是 RK3588 能玩 4K 多路 pipeline 的前提。

**DMA 老要"物理连续"，而 kmalloc 给不出来——这就是 CMA 存在的理由。** 页是 4 KiB（或大页 2 MiB/1 GiB）；DMA 经常要求**物理连续**，但普通 `kmalloc` 在系统跑久后会碎片化、分配大块失败。CMA（Contiguous Memory Allocator）在 boot 时预留一块大连续区，运行时可作为 movable 页给普通分配用，**一旦 DMA 需要就收回**——这就是 VPU/GPU/ISP 能稳定拿到几十 MiB 连续 buffer 的原因。`dma_alloc_coherent` vs `alloc_pages`：前者保证连续 + 给出 DMA 地址 + 处理一致性；后者要自己管 mapping。RK3588 的 VPU/RGA 大量用 CMA。

**coherent 和 streaming mapping，选错就漏 flush 或白 flush。** `dma_alloc_coherent`：硬件保证 CPU 和设备看到同一份 cache 一致的数据，不需要显式 flush——常驻型 buffer（如 VPU 的码流 buffer）用这个。`dma_map_single`/`dma_map_sg`：streaming，CPU 写完要 `sync_to_device`、设备写完要 `sync_to_cpu`——一次性传输的临时 buffer 用这个。**选择标准一句话**：buffer 长期被设备持有 → coherent；buffer 寿命短、方向交替 → streaming。乱用要么漏 flush（数据脏）要么白 flush（带宽浪费），两边都是坑。

**高分辨率下的内存体积，会颠覆你对"嵌入式"的认知。** 一帧 1080p NV12 ≈ 3 MiB，4K NV12 ≈ 12 MiB，4K P010 ≈ 24 MiB；pipeline 里同一个画面经常有 3-4 份副本（采集、预处理、处理、显示）。**多路 4K + 三缓冲 + 前后处理 → 几百 MiB 的 buffer 池**，这超过普通嵌入式但对 RK3588 是日常。这就是为什么第 5 章 dma-buf 跨设备共享是平台工程的核心——**少一次拷贝就少几十 MiB/s 带宽**，比堆算力更值钱。

**stride、alignment、cache 行，是这章最容易栽的细节。** stride（行跨度）经常 ≠ `width × bytes_per_pixel`：硬件要求按 16/32/64 字节对齐，一行末尾有 padding——**写代码不按 stride 算就会画面斜掉**，这是新手最常见的"花屏"真因。cache 行（通常 64 字节）是非一致域的最小同步单位：哪怕改一个像素，flush/invalid 都是一整行，所以"按 cache 行对齐 + 不要写跨行的零碎字段"。modifier（H3 第 9 章展开）决定同一帧在内存里的实际布局：GPU/VPU 可能要求 tile，CPU 直访要求 linear，转换有成本。

**最后，带宽账本永远先于跑分。** RK3588 的 DDR 带宽是有限物理资源；4K@60 解码 + ISP 输入 + RGA 缩放 + DRM 输出 + NPU 推理叠加时，每个 IP 都在抢同一根 DDR。**把每个 IP 的"分辨率×帧率×字节数×拷贝次数"加起来，超出 DDR 持续带宽就要掉帧**——账本比 TOPS/GFLOPS 跑分先到天花板。工程手段：零拷贝（第 5 章）、缩小中间格式、降帧率、用 RGA 代替 CPU 软处理（H3 第 12 章）；任何一招都要在带宽账本上算得出效果，凭感觉优化等于没优化。

实践：
- 看 `/proc/meminfo` 的 `CmaTotal`/`CmaFree`、`/sys/kernel/debug/dma_buf/bufinfo`，统计当前 dma-buf 的数量、大小、exporter。
- 用 4K NV12 一帧为基准，算"采集→预处理→推理→显示"全链路在不同拷贝次数下的带宽消耗，画成对照表。
- 故意制造大块连续分配失败（先用 userptr 占满内存，再请求 CMA），观察 dmesg 和 VPU/RGA 的报错模式。
- 对比 `memcpy`（CPU 软拷贝）和 `dma_alloc_coherent + 设备直访`的吞吐和 CPU 占用，得到一份"为什么要零拷贝"的实证。

### 第 4 章：IOMMU/SMMU 与设备隔离

如果说第 3 章讲的是"内存长什么样"，这一章讲的就是"设备怎么访问内存"——中间隔了一层叫 SMMU 的翻译。理解 SMMU，是写 RK3588 驱动和定位 DMA bug 的分水岭。

**先回答最根本的问题：为什么需要 IOMMU？** DMA 设备自己生成地址、直接打到物理总线上；**没有 IOMMU，一个有 bug 或恶意的设备能读写任意物理内存**——这是不可接受的安全和稳定性风险。IOMMU（ARM 叫 SMMU、x86 叫 VT-d）给设备加一层翻译：设备看到的是 IO 虚拟地址（IOVA），经 SMMU 页表翻译才到物理地址。**副作用是个大好事**：设备只能访问被显式 map 的内存，越界访问触发 IOMMU fault（context fault）被拦截，**而不是踩到别人内存里造成"幽灵 bug"**——这是把"随机崩溃"变成"明确错误"的关键一跃。

**stream ID 是 SMMU 区分设备的钥匙。** SoC 上每个 DMA 主端口有一个 stream ID（ARM 叫 SID）；SMMU 用 SID 区分"这次访问来自哪个设备"。一个 IP（如 VPU）可能有多个 SID（解码器、编码器、各路 input/output 通道），每个 SID 能映射到不同或相同的地址空间。**设备树里 `iommus`、`power-domains`、`dma-ranges` 把 SID 和 SMMU 实例绑起来**——理解这层绑定，才能解释"为什么 VPU 跑得好好的、ISP 一上就 fault"：SID 绑错或漏绑，fault 就来了。

**SMMU 有自己的页表，和 CPU 页表是分开的。** stage 1 是 OS 管理（IOVA→IPA）、stage 2 是 hypervisor 管理（IPA→PA），裸 Linux 用 stage 1 就够。TLB 缓存最近翻译；mapping 频繁变动时要 `tlb_flush`，**否则设备会用旧地址访问——这是经典的"刚 unmap 完设备还在写"的 use-after-free**，难调得很。大量 buffer 的 mapping 成本也不小：一次性 map 几千个 4K 页会拖慢启动，用 huge page（2M block）或 scatter-gather + `iommu_dma_alloc` 能大幅减少 mapping 数量。

**IOMMU group 和设备隔离。** group = 共享同一套翻译/隔离边界的设备集合；同一 group 内的设备互相不可隔离（典型：缺 ACS 的 PCIe bridge）。`vfio` 把整个 group 绑到用户态驱动，是虚拟化/直通的基础——RK3588 上做容器隔离、安全容器时会用到。**一个常见坑**：漏配 `iommus` 的设备会落到 default domain 或直接被拒绝 DMA，表现是"驱动 probe 通过但 DMA 全 fault"——你以为驱动坏了，真因是设备树少写了一行 iommus。

**fault 类型分三种，每种对应一类代码 bug。** translation fault（地址没 map）、permission fault（写只读区）、上下文 fault（SID 未绑定）。`/sys/kernel/debug/arm-smmu*` 或 `dmesg | grep -i smmu` 能看到 fault 详情（SID、fault 地址、读写方向），**这是定位设备 DMA bug 的金矿**。换个角度理解 IOMMU 的价值：**没有 IOMMU 的板子，同样的 bug 表现为"随机内存损坏"**，难调试几个数量级——你花一周找不到的崩溃，有了 SMMU 一行 fault 日志就定位了。这就是为什么写 RK3588 驱动要热爱 IOMMU，而不是嫌它碍事。

**这一章最该记住的一句话：设备看到的地址 ≠ CPU 物理地址。** DMA 设备的地址空间**经 IOMMU 翻译后才到物理地址**；"CPU 看到的物理地址 0x40000000"和"设备写 0x40000000"经常不是同一块物理内存。驱动用 `dma_map_*`/`dma_alloc_*` 拿到的是 **DMA 地址（= IOVA）**，这是要写给设备寄存器的地址；**把它当物理地址用是入门级 bug**。在 RK3588 这种全 IP 都过 SMMU 的平台上，任何"绕过 DMA API、直接给设备写物理地址"的代码几乎必然 fault——第 5 章 dma-buf 就是为封装这套规则而生的。

实践：
- 枚举 `/sys/kernel/iommu_groups/`：列出每个 group 含哪些设备，画一张 SoC IOMMU 拓扑图（哪几个 IP 共用哪个 SMMU 实例）。
- 选一个真实设备（VPU 或 RGA），跟踪一次 buffer 的 IOMMU 绑定：设备树 `iommus` → SMMU 实例 → SID → IOVA → 物理页。
- 故意制造一次 IOMMU fault（给设备一个未 map 的地址，或 unmap 后立刻让设备访问），从 dmesg 解析 fault 类型与地址。
- 画一张"地址翻译路径图"：CPU VA → CPU PA → DMA API → IOVA → SMMU 页表 → 物理 PA，标出每段由谁负责。

### 第 5 章：dma-buf、fence 与零拷贝

H1 的前两章讲了内存和 SMMU，这一章讲怎么让多个 IP **不拷贝地共享同一块 buffer**——这是 RK3588 平台工程的核心，也是"为什么 4K 多路 pipeline 跑得动"的底层答案。

**dma-buf 是内核里"跨设备共享 buffer"的标准对象。** 一个 exporter（如 DRM、V4L2、CMA heap）创建并管理 buffer 的物理页；多个 importer（其它驱动）通过 fd 拿到 buffer 引用，**不需要拷贝**。fd 是 dma-buf 的用户态句柄：用户态把 DRM 的 buffer fd 传给 V4L2 ioctl、再把同一个 fd 传给 NPU runtime，**物理页从头到尾只有一份**。exporter 的职责是实现 `attach`/`detach`/`map`/`begin_cpu_access`/`end_cpu_access` 等回调，决定 buffer 的物理布局和 cache 同步策略；importer 只调用不实现。

**fd 在进程间传递，mmap 让 CPU 访问——但 cache 同步不能漏。** fd 通过 Unix socket 的 `SCM_RIGHTS`、binder（Android）、或 fork/exec 在进程间传递，同一 fd 在不同进程指向同一份 buffer。`mmap` dma-buf fd 才能让 CPU 访问，但 **mmap 前后必须包 `begin_cpu_access`/`end_cpu_access`（或用户态 `DMA_BUF_SYNC_START/END` ioctl）**，否则 cache 和设备看到的可能不一致。"为什么 mmap 完不 sync 就出错"：CPU 写到 cache、设备读到 DDR 的旧数据——**这是 dma-buf 最常见的使用 bug**，也是第 3 章 cache 一致性的具体落地。

**fence 是"这块 buffer 当前的生产者/消费者是否完成"的内核对象，分两种语义。** Implicit fence 由驱动自动管（attach 时挂 fence、读取时等 fence），简单但有死锁和串行化风险。Explicit fence（sync_file/sync_obj）让用户态拿到 fence fd，能组合"等 A 完成再提交 B"的依赖图，表达力强但需要应用主动管理——**Vulkan/DRM atomic 走 explicit，传统 V4L2/DRM 走 implicit**。这条分界决定了你写应用时该用哪种同步模型。

**五个 IP 共享 buffer 的入口要记住。** DRM：`DRM_IOCTL_PRIME_HANDLE_TO_FD` 把 GEM buffer 转 dma-buf fd，反之 `FD_TO_HANDLE` 导入（Mesa/Vulkan 全走这条）；V4L2：`VIDIOC_EXPBUF` 把队列里的 buffer 导出 dma-buf fd（**ISP→下游零拷贝的入口**）；MPP：用户态把 dma-buf fd 直接作为输入/输出 buffer 传给 MPP API，VPU 内部不再拷贝；RGA / NPU runtime：同样接受 dma-buf fd。**这条 fd 全程流转，就是"V4L2 → RGA → dma-buf → NPU → DRM"实时流水线的骨架**（N 方向 17N、M 方向 15M 会拼起来）。

**最后说清"零拷贝"的真与伪，这是这章最值钱的一节。** 真零拷贝：buffer 的物理页从 exporter 到最后一个 importer 都不变，没有任何 `memcpy`——这是 dma-buf 的设计目标。但**伪零拷贝有三种常见伪装**：(1) 用了 dma-buf fd，但驱动内部拷了一份（兼容性 fallback）；(2) 用户态用 `mmap + memcpy` 自己拷一遍；(3) cache 同步触发了 cache flush，等效于把数据搬了一遍。验证手段：`/sys/kernel/debug/dma_buf/bufinfo` 看 buffer 的 size/attach 数；perf 抓 `memcpy` 调用量；对比"fd 传递"和"用户态 memcpy"的 CPU 占用——**数据不会撒谎**。即使真零拷贝也可能有 cost：cache 同步、TLB 维护、fence 等待，这些"非拷贝 cost"在高帧率下同样能吃满 CPU/带宽。"我用了 dma-buf 所以是零拷贝"这种话，不验证就别信。

实践：
- 跟踪一帧数据经过至少两个硬件模块（如 V4L2 采集 → RGA 处理 → DRM 显示），用 `bufinfo` 确认三个 IP 共享同一物理页。
- 记录 buffer 的完整生命周期：谁分配、谁导出、几个 importer、何时 unmap、何时释放；标出每步是否有 cache 同步。
- 实测拷贝 vs 共享：同一帧"用户态 memcpy 一次" vs "全程 dma-buf"，对比延迟、CPU 占用、DDR 带宽（用 perf 或硬件计数器）。
- 找一个"伪零拷贝"案例（如某驱动因格式不兼容内部 fallback 拷了一份），从代码/dmesg/perf 三方证据识别它。

阶段产出：
- 一张跨设备 buffer 生命周期图（producer → consumer × N → release，标注 cache 同步点）；
- 一份零拷贝对照实验报告（拷贝次数 / CPU / 带宽 / 延迟四列对比）。

## H2：big.LITTLE、功耗与持续性能

### 第 6 章：调度、CPU affinity 与 DVFS

big.LITTLE 不只是"有大小核"，它把"任务放哪个核"变成了一个有正确答案的工程问题。这一章讲调度器怎么选核、你怎么用 affinity 和 governor 影响它、以及为什么"全钉大核"是新手最容易犯的错。

**big.LITTLE 的本质：不同微架构的核同 ISA、不同能效曲线。** A76 大核冲峰值 IPC、A55 小核冲能效，调度器的任务是把任务放到"性价比最高的核"上。**EAS（Energy Aware Scheduling）用能量模型加任务预测**做这件事——把任务放在最省电还能跑得动的核上；老的 HMP 只看 capacity。任务要分类：**latency-sensitive**（响应用户输入、低延迟）应该上大核；**throughput**（后台转码、批量推理）应该放小核多核。分类错了，要么卡顿要么浪费功耗。

**capacity 和 utilization 是调度器的决策依据。** `cpu_scale` 是每个核的 capacity（A76 大、A55 小），调度器用它判断"任务能不能跑得动"；`util_avg` 是任务过去一段时间的平均占用，调度器用它选核——**持续高 util 的任务会被迁到大核，迁的过程中可能掉帧**（这就是为什么"大小核迁移"要测）。`/sys/devices/system/cpu/cpu*/cpu_capacity` 能读到。`sched_setaffinity` 让用户态可以钉死任务在某核，绕过 EAS——这是产品调优常用手段，但**滥用（钉错核、忽略热效应）反而劣化**。

**DVFS：频率越高性能越强，功耗近似平方增长。** governor 决定什么时候升降频：`performance`（永远最高频）、`powersave`（最低）、`schedutil`（跟随 EAS 的 util）、`userspace`（用户态直接写频率）。**切换频率本身有成本**：PLL 锁定、稳定性约束、热跟随，频繁抖动频率自己就耗电。产品上经常选 `schedutil` 或固定一个折中频率，而不是让频率疯狂跳。

**钉核是一门艺术，钉错了比不钉还糟。** 钉小核：适合稳定低延迟后台任务、控制流密集的（input、网络、调度线程）；钉大核：适合单线程峰值任务、推理主线程、显示合成（latency-critical）。**和 IRQ affinity 配合**：把某个设备的中断钉到和处理线程同一个核，避免跨核 wake 和 cache 迁移，这是 NPU/VPU/网卡调优的标准动作。**滥用后果很具体**：所有任务钉大核 → 大核过热 → 热到降频后比小核还慢；所有任务钉小核 → 大核闲置、性能天花板被压低。两条都是产品翻车的常见路径。

**governor 还是固定频率？这是产品策略选择，没有标准答案。** 固定频率可预测但浪费功耗；governor 省电但延迟抖动。嵌入式产品常见模式：(1) 启动和界面交互时 `performance`、空闲后台时 `schedutil`；(2) 视频回放时按分辨率和帧率固定频率；(3) NPU 推理时大核全开、推理结束立刻回低频。**这些是策略，要靠第 8 章的性能取证工具验证是否真有效**——凭感觉调 governor 等于盲调。

实践：
- 把同一个 CPU 密集任务（如软件 H.264 解码一段素材）分别固定在 A55 和 A76 上，对比吞吐、CPU 占用、温度上升速率。
- 观察不钉核时任务在大小核间迁移的轨迹（ftrace 的 `sched_switch`），统计迁移频率和单次迁移的 cache miss（perf）。
- 把 governor 在 `performance`/`schedutil`/`powersave` 间切换，跑相同负载，对比端到端延迟和温度稳态。
- 设计一个"不合理绑核"反例（如所有任务钉小核），观察大核闲置、整体性能塌陷；恢复合理绑核后对比。

### 第 7 章：thermal、降频与长期稳定性

第 6 章讲的是"理想情况下的性能"，这一章讲"热量会怎么把你的性能吃掉"。在 RK3588 这种高算力 SoC 上，thermal 不是可选项，是产品能不能持续工作的硬约束。

**Linux thermal framework 三件套：zone、cooling、governor。** thermal zone（温度传感器：CPU/GPU/SoC）报温度；cooling device（CPU/GPU/NPU 降频、风扇）执行降温；governor（step-wise、power_allocator）决定怎么降。`/sys/class/thermal/thermal_zone*` 里每个 zone 有 trip point（warning/critical），到点触发对应 cooling 动作。cooling device 把"温度过高"翻译成"降低最高频率上限"——所以 thermal 本质上就是"用降频换温度"。

**SoC 是一块硅，所有 IP 共享热源——不能孤立看某个 IP 的温度。** CPU 满载时 GPU 温度也升、NPU 满载时 CPU 也受影响。**"热点漂移"**：满载前几秒热点在大小核 cluster，几分钟后漂到 VPU/NPU 区域；trip point 设在哪要看稳态热点，不是瞬时。**最坏场景**：CPU+GPU+NPU+VPU 同时拉满，热密度瞬时冲到峰值、立刻降频——这就是"峰值性能跑不到一分钟"的物理原因，也是厂商 TOPS 标称值在真实产品里达不到的根。

**峰值 vs 持续性能：产品指标永远是后者。** 厂商标称的 TOPS/GFLOPS 是"散热无限好时的瞬时峰值"；实际产品受热限制，**持续性能远低于峰值（典型差 20-50%）**。持续性能曲线长这样：负载开始跑峰值 → 几十秒到几分钟温度达 trip → 降频 → 进入热平衡的稳态。**这条曲线的稳态值才是产品指标**。工程态度：产品永远标"持续 30 分钟后的性能"，不标"冷启动峰值"——后者是营销，不是工程。

**散热方案是被动的还是主动的，这是产品定义的一部分。** 被动散热（金属外壳、散热片）靠热传导和自然对流，持续性能受机箱和环境温度限制；主动散热（风扇）强制对流，能显著拉高持续性能，但风扇本身有寿命、噪音、积尘问题，产品级要算 MTBF。**散热能力是硬件团队给的，软件团队的 governor 和 cooling 策略在这个上限内才有意义**——缺一项谈另一项都是空谈。

**温控策略和产品指标挂钩。** 三类 trip：`passive`（轻度降频保命）、`active`（重度降频 + 风扇满速）、`hot`（紧急降频到最低）。策略选择：消费电子倾向"温度优先"（保持低表面温度）；工业/AI 设备倾向"性能优先"（顶到 critical 才退）。**hysteresis（迟滞）很关键**：温度过了 trip 再升一点才降频、降一点才恢复，避免在 trip 边界来回抖——漏配 hysteresis 是常见 bug，表现为频率在边界疯狂跳。

实践：
- 执行持续负载（多核 stress + NPU 推理 + GPU 渲染同时跑 30 分钟），每秒记录每个 thermal zone 温度、每个核当前频率、风扇转速、负载吞吐；画"温度-频率-性能"三条曲线。
- 找到首次降频点（哪个 zone 先到 trip、降到多少 MHz）；对比产品标称的"持续性能"和实测稳态值。
- 被动 vs 主动散热两种条件下跑同一负载，对比持续性能差异；评估当前散热方案够不够。
- 改一个 trip point 或 governor 策略（如把 `passive` trip 从 75℃ 改到 85℃），观察性能/温度稳态的变化——这是产品调优的实操。
- 验证恢复行为：负载结束后温度是否回落、频率是否回升、有没有"卡在低频不回来"的 bug。

### 第 8 章：系统性能取证

前两章讲了调度和 thermal 的"应该怎样"，这一章给的是"怎么量出来"。没有这章的工具，前面所有的策略都只是猜测——**性能问题从来不靠想清楚，只靠测清楚**。

**perf 是 Linux 性能分析的主力。** `perf stat`（计数器汇总）、`perf record/report`（采样热点函数）、`perf top`（实时）、`perf sched`（调度）。常用指标：cycles、instructions（算 IPC）、cache-misses、branch-misses、context-switches、cpu-migrations——**这些能区分"算力瓶颈"还是"内存瓶颈"还是"调度开销"**，而这三者对应的优化方向完全不同。perf on arm64 的 PMU 是平台相关的，确认 SoC 暴露的事件列表（`perf list`）；RK3588 的 PMU 事件覆盖率以真板和内核版本为准。

**ftrace + trace-cmd 是内核行为的时间线。** ftrace 抓 tracepoint：`sched_switch`（任务切换）、`sched_wakeup`（唤醒）、`irq_handler_entry/exit`（中断）、`dma_fence_signaled`（同步）等。**trace-cmd（封装 ftrace）+ KernelShark（GUI）让 ftrace 可用性大幅提升**——记录一段 trace 然后可视化，是定位延迟尖峰的标准流程。用途：回答"为什么这一帧慢了 16ms"——展开这 16ms 里每个核在干什么、谁被调度、谁在等 fence、谁在等中断。

**吞吐和端到端延迟是两个独立指标，别混。** 吞吐（FPS、推理/秒）和端到端延迟（采集到显示、输入到响应）——**高吞吐不等于低延迟**：pipeline 深可以冲吞吐但延后单帧（流媒体常见）。pipeline 各级延迟分解：采集 → 预处理 → 推理/编解码 → 合成 → 显示，每段单独测；总延迟不是简单相加（有并行/重叠）。**同步开销也是延迟**：fence 等待、ioctl 系统调用、唤醒延迟（几十微秒到几十毫秒），这些"非计算开销"在小数据高帧率场景可能占主导。

**平均值会撒谎，尾延迟才是用户体感。** 1% 帧延迟可能是平均的 5-10 倍；**用户对"卡顿感"主要来自尾延迟而非平均**。测量指标：p50/p90/p99/p99.9，同时画直方图和时间序列——只看平均的产品定义必然翻车。抖动来源：调度迁移、IRQ 抢占、cache miss、内存带宽竞争、热降频，逐项排除才能找到真凶。

**可重复 benchmark 三大要求，缺一不可。** (1) 同样的输入（固定素材/随机种子）、(2) 同样的初始状态（温度、频率、后台负载）、(3) 足够长的时间（覆盖 warm-up + 稳态 + 可能的降频）。**区分三段**：warm-up（前几秒，cache 冷、PLL 升频）、稳态（中间长段）、降频段（热触发后）——只看稳态会高估，看全程平均会模糊。记录模板：每次跑完保存（输入指纹 + 环境 + perf ftrace + 温度曲线 + 输出指标），这是 H3、N、M、D 各方向统一要求的"证据包"。

实践：
- 建一份统一性能记录模板（Markdown 表格 + 附 ftrace/perf 原始文件 + 温度日志 + 截图），后续每个方向都套用。
- 对一个真实 pipeline（如 RGA 缩放 → DRM 显示）做单帧延迟分解：用 ftrace 抓 ioctl + fence + vsync，画 16ms 时间线。
- 跑高负载 10 分钟，用脚本每秒采 perf stat + 温度 + 频率，事后画图区分 warm-up/稳态/降频三段。
- 给同一 benchmark 跑 100 次，画 p50/p90/p99 直方图，识别尾延迟来源（调度？IRQ？热？）。

## H3：显示、摄像头与媒体公共地基

### 第 9 章：DRM/KMS 与显示管线

显示接口（HDMI/DP/DSI/eDP 哪些在线、屏幕型号、转换芯片）必须等开发板和配套硬件确认；本章先建立 DRM/KMS 的通用模型——这套模型在所有 Linux SoC 上都一样，RK3588 只是具体的 VOP 和 encoder 不同。

**DRM 的对象模型是这章的骨架：plane、CRTC、encoder、connector。** plane（图层）是一块可独立位置/缩放/混合的内容（鼠标光标、OSD、视频层），SoC 的 VOP 通常有多 plane（primary + overlay + cursor）；CRTC（扫描器）按 pixel clock 从 framebuffer/plane 里读像素、逐行扫出，送进 encoder——它是时序的发生者；encoder 把 CRTC 输出编码成物理链路协议（HDMI/DP/DSI/eDP/LVDS）；connector 是物理接口（含 EDID、HPD 热插拔）。**拓扑记牢：`plane → CRTC → encoder → connector`**，一个 CRTC 可绑多 plane，但只能绑一个 active encoder/connector。

**四条物理链路各有脾气。** HDMI/DP：长距离、热插拔、EDID 协商分辨率，适合外接显示器（DP 多流是进阶）；DSI（MIPI Display Serial Interface）：串行显示协议，常见于直连 LCD 面板，分命令模式（DBI）和视频模式；eDP（嵌入式 DP）：内部 DP，常用于笔记本/平板级面板——DSI 和 eDP 在产品里二选一，看面板接口。物理层：D-PHY（DSI/CSI 共用）、Lane 配置、symbol clock；HDMI/DP 有 link training 协商通道。

**mode、pixel clock、同步时序，写错就是花屏或无信号。** mode（分辨率+刷新率，如 1920x1080@60、3840x2160@60）对应一组 hsync/vsync/blanking 参数。**pixel clock = 总像素数（含 blanking）× 帧率**——4K@60 的 pixel clock 约 594 MHz，对链路和 SoC 输出能力都是硬约束。mode 来源：EDID（HDMI/DP 自动协商）、DT（DSI/eDP 面板写在设备树）、固定 mode（嵌入式面板）。

**pixel format、modifier、stride，这套和第 3 章是一回事，落到显示上。** DRM 用 FOURCC 标识 pixel format（`XR24`、`NV12`、`NV16`、`P010`），CRTC 和 plane 各支持一个子集，要提前查询。**modifier 是这章容易栽的点**：tiled/super-tiled/linear 等 memory layout，GPU/VPU 输出的可能是 tiled，CRTC 必须支持同 modifier 才能直采，否则要 RGA 转 linear（第 12 章）。stride（行跨度，`fb->pitches[0..3]`）对多 plane 格式有多个。

**atomic modesetting 和 page flip 是现代显示的核心 API。** atomic 把"这组 plane 配置 + CRTC 状态 + connector"打包一次性提交，**要么全成功要么全回滚**——旧版分步 API（SET_PLANE/PAGE_FLIP）已淘汰。page flip 在 vsync 边界切换 framebuffer，避免撕裂。**多 plane 合成**：CRTC 把 N 个 plane 按 z-order 混合后输出，硬件能合成时省掉 GPU 合成开销，这是 Android Hardware Composer 的核心思想（D 方向 17D 展开）。fence 同步：atomic 提交可以带 in-fence（等渲染完再显示）、返回 out-fence（显示完通知），这是 explicit 同步模型（第 5 章）。

实践：
- `modetest -M <module> -V` 枚举 DRM 模块、connectors、encoders、CRTCs、planes；画一张"硬件对象拓扑图"。
- `modetest -s` 点亮显示器（前提：屏幕和接口已确认）；`modetest -P` 测试多 plane。
- 编一段最小 libdrm 程序做 atomic page flip，用 ftrace 抓 vsync + flip 提交时间，测"提交到显示"的端到端延迟。
- 故意提交一个不支持的组合（如 CRTC 接 modifier 不匹配的 plane），从 atomic 返回值分析错误类型。

### 第 10 章：V4L2、Media Controller 与 ISP

摄像头（sensor 型号、镜头、连接方式、ISP 软件栈）必须等真板确认后才能进受控实验；本章先建立 sensor → CSI → ISP → V4L2 的通用模型。RK3588 ISP（rkisp）的版本和能力以真板和主线驱动版本为准。

**一条摄像头链：sensor → MIPI CSI → D-PHY → ISP → V4L2。** sensor 输出 RAW（Bayer）或 YUV；MIPI CSI-2 是 sensor 到 SoC 的串行接口，走 D-PHY 物理层（clock lane + 1~4 data lane）；CSI 接收端 → ISP 做 demosaic、白平衡、曝光反馈、降噪、镜头阴影校正、CSC。ISP 输出 YUV（NV12/NV16）或 RGB 给后续 IP，同一帧的元数据（曝光、增益、时间戳）单独走一个 V4L2 metadata 节点。

**Media Controller 是把这条链可视化的关键。** 每个 IP 块（sensor、CSI receiver、ISP、resizer、各 video node）是一个 entity，entity 之间用 pad + link 连接。**`media-ctl -p` 打印整张图**；配置 pipeline 就是"先 link、再 set_format、再开始 streaming"——错了就出现"格式协商失败"。多路输出：一个 ISP 经常同时输出"全分辨率 main stream"和"小尺寸 self stream"，这是双路采集的基础。

**V4L2 buffer queue 三步：REQBUFS、QBUF、DQBUF。** REQBUFS 申请一组 buffer（MMAP、USERPTR、DMABUF）；QBUF 把空 buffer 入队给驱动填；DQBUF 取出填好的 buffer。**三种内存模式里，现代零拷贝 pipeline 用 DMABUF**——这是和第 5 章 dma-buf 接上的入口。streaming 状态机：REQBUFS → STREAMON → 循环 QBUF/DQBUF → STREAMOFF；丢帧、抖动、queue 深度不足都在这个循环里暴露。

**RAW、YUV、颜色空间、stride，这套概念第 3、9 章讲过，这里落到摄像头。** RAW（Bayer）每像素 10/12 bit packed，是 sensor 原始数据，体积小但需 ISP 处理；YUV 的 4:2:0（NV12）/4:2:2（NV16）是视频常用；颜色空间 BT.601（SD）/BT.709（HD）/BT.2020（UHD）标记错导致颜色偏差（"看上去发灰/发紫"）。stride（`bytesperline`）必须和下游（RGA/MPP/DRM）协商一致。

**曝光、增益、帧率、3A。** 曝光时间 + 模拟增益 + 数字增益 = 一帧亮度；过曝丢高光、欠曝噪点。3A（AE/AWB/AF）可在用户态（如 libcamera）或 ISP 固件内做。**rkisp 在主线提供 hook，IQ 调参是厂商专属领域，rk-forge 不深入**——但要求学习者能识别"IQ 文件是否加载、ISP 是否真在处理、3A 是否在工作"。时间戳：V4L2 buffer 带 timestamp（boot time/monotonic），和 audio、IMU、显示时间戳对齐是多传感器融合的基础。

实践：
- `media-ctl -p` 打印整张 media graph，画 sensor/CSI/ISP/video node 拓扑图，标每个 pad 的 supported format。
- 配置 link + set_format（一条 main stream），用 DMABUF 模式采集 100 帧落文件，用 `ffprobe` 或自写检查确认格式、stride、颜色空间正确。
- 检查丢帧和时间戳分布：统计 100 帧的实际到达间隔 vs sensor 名义帧率；抖动大就分析 queue depth、CPU 调度、IRQ。
- 在不同光照下抓几帧，观察 AE/AWB 行为；记录"调到稳定亮度的帧数"作为 3A 性能指标。
- 保存摄像头硬件清单（sensor 型号、镜头、连接方式）和 IQ 文件版本（如适用）。

### 第 11 章：MPP 硬件编解码

MPP 是 Rockchip 的硬件编解码用户态库，封装了 VPU。这一章讲 codec 的基本概念、MPP 的 buffer 模型、以及用户态 MPP 和内核 VPU 驱动的边界——这条边界是定位编解码问题时该看哪层日志的关键。具体 codec/profile/level 支持矩阵**以真板和当前栈版本为准，不预设**。

**codec、profile、level 三件套。** codec（H.264/H.265/AV1/VP9）是压缩标准；profile（Baseline/Main/High）是标准内的功能子集（High 支持 8-bit 4:2:2、Main 不支持）；level 是分辨率/帧率/码率上限档位。**解码器必须支持某个 profile+level 才能解**，写代码前要查 SoC VPU 的支持矩阵。兼容性陷阱：同是 H.265，Main 和 Main10 不能用同一解码器实例；AV1 在不同 SoC 版本支持度差异大。

**packet、frame、buffer 三层抽象。** packet（压缩域）是一个 NAL（H.264/H.265）或 OBU（AV1），含 slice 头 + 数据；解码器吃 packet、产 frame；frame（图像域）是一帧解码后的 YUV/RGB；encoder 吃 frame、产 packet；buffer（载体）是承载 packet 或 frame 的 dma-buf，MPP 维护 buffer pool 避免每次分配。**关系**：1 packet → 1+ frame（B 帧重排）；1 frame → N packet（多 slice）；buffer 复用是性能和内存占用的关键。

**解码/编码流程和码率控制。** 解码：demux → packet 入队 → decoder 产 frame → 取 frame；**硬解的关键是把 dma-buf 直接给下游（RGA/DRM），不要拷**。编码：采集/生成 frame → encoder 产 packet → mux；码率控制（CBR/VBR/CQP）决定质量和体积的折中——target bitrate、max bitrate、QP 范围、GOP 长度、关键帧间隔，调错导致码率爆炸或质量塌陷（M 方向 16M 展开）。error resilience：错误帧恢复、关键帧请求（IDR request），网络丢包/存储错误时的鲁棒性靠它。

**用户态 MPP 和内核 VPU 驱动的边界，这条线决定你 debug 时看哪层。** 内核 VPU 驱动（如 rkvdec/rkvenc）暴露 V4L2 interface（M2M device），分配 buffer、管硬件、跑 firmware；用户态 MPP 库在 V4L2 之上封装更易用的 API（`mpi_dec_/mpi_enc_*`），处理格式协商、buffer pool、解码器状态机。**边界**：debug 硬件层面问题（中断、firmware、IOMMU fault）看内核驱动；debug 应用层面（packet 顺序、格式、码率）看 MPP；**混淆会导致定位方向错**。固件：VPU 跑需要 firmware blob（见 [blobs.md](../blobs.md)），**用户态 MPP 版本、内核驱动版本、firmware 版本三者必须配对**，错版本通常直接 hang 或报错。

实践：
- 硬件解码一段受控测试素材（标准测试流如 Sintel/Big Buck Bunny 的 H.264 片段），记录输出格式、帧率、CPU 占用、内存占用、码流统计。
- 编码一段输入（摄像头 V4L2 输出或文件 YUV），用 CBR/VBR 两种码率控制跑同样输入，对比输出体积/质量/编码延迟。
- 故意给一个错误流（截断的 packet、错误 NAL），观察 decoder 的错误恢复行为和日志；测试 IDR request。
- 把 decoder 输出的 dma-buf 直接喂给 DRM 显示（不经任何 CPU 拷贝），用第 5 章的方法验证零拷贝；和"用户态拷一遍再显示"对比 CPU/带宽。
- 记录 MPP 版本 / VPU 驱动版本 / firmware 版本三元组，作为可复现基线。

### 第 12 章：RGA 图像处理

RGA 是 Rockchip 的 2D 图形加速器，干的是缩放、裁剪、旋转、颜色转换这些"看起来简单但 CPU 做很亏"的活。这一章讲它擅长什么、什么时候该用它代替 CPU。

**RGA 的职责：缩放、裁剪、旋转、CSC。** 缩放（硬件 bilinear/bicubic），实时处理的分辨率变化几乎都靠它；裁剪和 blit（区域拷贝）；旋转 90/180/270 加镜像，屏幕旋转和前置摄像头镜像的硬件加速；CSC（RGB↔YUV、不同 YUV 子采样互转）——**这一步经常被忽视但每秒消耗几 MiB 带宽**。

**支持的格式和限制，以真板 RGA 版本为准。** RGA 有 RGA1/RGA2/RGA3 多代，能力不同；RGB（RGBA8888、RGB888、RGB565）、YUV（NV12、NV16、YUYV）。**stride 和 alignment 限制**：行跨度按 4/16/64 字节对齐、起始地址按页对齐，写错就报"format not support"或画面错位。性能上限固定，**4K@60 多路 CSC 可能超过单 RGA 上限**，需要调度多 RGA 实例或换路径。不支持的格式（某些 RGB 变种、10-bit YUV）会 fallback 到 CPU 软处理，性能急剧下降——写代码前查支持表。

**RGA 和 CPU 软处理的差别，决定了什么时候用它。** CPU 软处理（libyuv、OpenCV）灵活但占 CPU、cache miss 大，高分辨率高帧率撑不住；RGA 固定功能，CPU 几乎零占用，单次延迟几微秒到几十微秒，适合实时 pipeline。**CPU 的优势是能做任意算法**（非线性映射、自定义卷积核），RGA 只能做固定几种几何和 CSC。工程选择：**能换 RGA 就换**，RGA 不支持的算法重新设计（如分段线性表 + RGA LUT）而不是直接堆 CPU。

**dma-buf 输入输出是 RGA 的正确用法。** RGA 接受 dma-buf fd 作 src 和 dst：从 V4L2 拿的采集帧、从 MPP 拿的解码帧、从 GPU 拿的渲染结果，都能不拷贝直接进 RGA。RGA 输出同样是 dma-buf，能直送下游（DRM 显示、MPP 编码、NPU 推理）——**这是"V4L2 → RGA → NPU/DRM"流水线的关键一环**。实操注意：RGA 要求输入输出的 stride/format/rect 都满足硬件约束，否则 ioctl 失败；写好协商代码（query support → set format → submit）比硬填参数更重要。

实践：
- 用 RGA 完成"NV12 → RGBA8888 + 缩放 1080p→720p + 旋转 90 度"组合操作，对比单次 RGA 调用 vs 三次串行调用的延迟。
- 对比 CPU（libyuv）vs RGA 在同一 CSC + 缩放任务下的吞吐、CPU 占用、DDR 带宽；用第 5 章和第 8 章的取证工具统一记录。
- 把 RGA 输出的 dma-buf 直送 DRM 显示（第 9 章）和 MPP 编码（第 11 章），完整跑一遍"输入→RGA→两路输出"。
- 故意提交一个不支持的组合（如 10-bit YUV 或某 RGB 变种），从 ioctl 返回值和 dmesg 分析原因；写一份"格式支持矩阵"模板供后续章节复用。

### 第 13 章：第一条端到端硬件流水线

H0-H2 加本章前四节，凑齐了所有零件；这一章把它们拼成一条最小可跑的硬件流水线。建议基础骨架（具体输入源以真板配置为准）：`文件或摄像头 → MPP/V4L2 → RGA → DRM`。

**buffer ownership：每个 buffer 在任一时刻只能有一个 owner。** 采集端产生 → 交给 RGA → 交给显示端 → 显示完归还采集端。用 dma-buf fd 的引用计数管理 ownership：fd 在哪个进程/线程手里就是 owner，release 时 close fd。**经典 bug**：buffer 还在硬件 pipeline 里就被释放（fd close 太早）→ 内核可能 fault 或数据损坏；**用 fence（第 5 章）显式同步才能安全释放**。

**backpressure：下游满了，上游必须停。** pipeline 是流：上游产 buffer → 下游消费；如果下游（显示）慢于上游（采集），buffer 会在中间堆积。**backpressure 机制**：下游 queue 满时上游必须停下等（block 或 EAGAIN），不能丢数据也不能无限堆积。实现方式：有限 queue 深度（3-5 个 buffer）+ 同步 QBUF/DQBUF；queue 满则阻塞或丢帧（按策略）。

**queue 深度是个 trade-off，没有通用最优值。** 深队列：吸收抖动、吞吐高，但延迟大（一个 buffer 在 queue 排了 100ms 才显示）；浅队列：延迟低，但抗抖动差、易丢帧。**选择**：交互式应用浅（1-2）、流媒体深（3-5+）；要按场景测，不能拍脑袋。

**时间戳同步是多传感器融合的基础。** 每一级用同一时钟基准（boot time 或 monotonic）；V4L2 timestamp、MPP PTS、audio clock、display vsync 必须可换算。**音视频同步（M 方向 15M 进阶）**：audio clock 是主时钟、video PTS 追随，漂移超阈值丢帧或重复帧。多传感器融合：camera + IMU + audio + NPU 推理结果的时间戳必须对齐，任何一级时钟漂移都导致融合错误。

**错误传播和资源回收，是 pipeline 健壮性的硬指标。** 错误类型：采集设备拔出、解码错误帧、显示断开、内存分配失败、IOMMU fault——每种在 pipeline 里的传播路径不同。**健壮性要求**：(1) 单帧错误不杀整个 pipeline（丢一帧继续）；(2) 设备错误能优雅停止（释放所有 buffer、关闭 fd）；(3) 重启后能干净恢复（不残留 dma-buf、不漏内存）。资源回收清单：dma-buf fd 全 close、V4L2 STREAMOFF、MPP deinit、DRM atomic 回滚、内存 free——这是"pipeline 不漏资源"的验证目标。

实践：
- 运行端到端 pipeline（建议"摄像头 V4L2 → RGA 缩放 → DRM 显示"作最小版），稳定运行 30 分钟以上；每秒记录 FPS、单帧端到端延迟、CPU 占用、内存占用、温度、复制次数。
- 模拟输入中断：拔摄像头/截断输入文件/kill 上游进程，观察 pipeline 是否优雅停止；重启后能否干净恢复（用 `/sys/kernel/debug/dma_buf/bufinfo` 验证无残留 buffer）。
- 调整 queue 深度（1 到 8），测延迟 vs 吞吐 vs 丢帧率的 trade-off 曲线；找当前 pipeline 的最优深度。
- 写一份"错误传播矩阵"：行=错误源、列=受影响组件，每格写"如何检测 + 如何恢复"；这是产品级健壮性的设计文档。

完成 H0–H3 后才能进入专业方向。

## 6. AI/NPU 方向

## N1：RKNN 工具链和版本边界

### 第 14N 章：从训练模型到 RKNN

这一章讲一个训练好的模型怎么变成 NPU 能跑的东西。核心是三层翻译：PyTorch → ONNX → RKNN，每一层都有版本配对的坑。**NPU 固件、runtime、toolkit、内核驱动的版本必须配套，这是 N 方向最常见的"代码没动就跑不了"的根因**。

**PyTorch、ONNX、RKNN 三层关系，先理清。** PyTorch（或 TensorFlow）是训练框架，在 host 上训练得到 `.pt`/`.pth`，这是带梯度信息的训练态模型；ONNX 是交换格式，把训练态模型导出成前向推理的中性图（节点=算子，边=tensor），让训练框架和推理后端解耦；**RKNN 是 NPU 专属格式**，ONNX 还不能直接在 NPU 跑，需要 host 端转换工具把 ONNX 翻译成 NPU 能直接执行的指令序列（权重量化、算子映射、内存布局重排）。这套分层不是 NPU 独有：TensorRT（NVIDIA）、OpenVINO（Intel）、CoreML（Apple）走完全一样的"训练框架→中性图→硬件专属"路径。

**host 转换工具和板端 runtime 分工，版本必须严格匹配。** host 工具（如 `rknn-toolkit2`）在开发机跑，输入 ONNX + 校准数据，输出 `.rknn` 文件（量化权重 + 算子调度 + 内存布局）；板端 runtime（如 `librknnrt`）在 RK3588 跑，加载 `.rknn`、绑定输入输出 tensor、提交推理、取回结果。**转换工具产物的版本必须和 runtime 版本严格匹配**——错版本报"unsupported op"或"layout mismatch"或干脆 hang，这是 N 方向最常见的"我代码没变就跑不了"的真因。

**模型输入输出的 layout 和数据类型，写代码前要查清。** 输入 tensor 典型 NCHW 或 NHWC，模型转换时已固定，runtime 必须按这个 layout 准备 buffer，否则结果错乱。数据类型：FP32（高精度但慢）、INT8（量化后主流）、FP16（折中），**不同类型对 NPU 性能差一个量级**。输出 tensor：分类任务是 `[N, classes]`；检测任务是 `[N, boxes, 5+classes]`（每个 box 是 x,y,w,h,score,cls_scores...），输出 shape 决定后处理代码写法。

**算子支持是 NPU 最该提前查的事。** NPU 是固定结构加速器，只支持与训练时使用的算子对应的硬件实现；遇到不支持的算子，转换工具可能：(1) 拒绝转换、(2) 回退到 CPU（性能塌陷）、(3) 用近似实现（精度变化）。**常见不支持/性能差的算子**：自定义层、动态 shape、复杂 reshape、某些 attention 变种。选模型前先看 NPU 的算子支持表，别等转换失败才发现。工程手段：替换等价算子（如 `sigmoid` 用 `1/(1+exp(-x))`）、改写模型结构（把后处理从模型剥出来放 CPU）、用官方"参考模型"作起点。

**版本配对是 N 方向的命门。** 四层依赖：toolkit（host 转换）→ `.rknn` 文件格式 → runtime（板端库）→ 内核 NPU 驱动 → NPU 固件（blob）。任何一层升级都可能要求其它层跟着升级。**工程纪律**：固定一组配对版本作基线（toolkit 1.x + runtime 1.x + 驱动 commit Y + 固件 Z），任何升级都做"前后精度 + 性能对比"再决定是否合并。NPU 固件 blob 和 `rkbin` 的关系见 [blobs.md](../blobs.md)；主线驱动 vs 厂商 BSP 驱动的差异见 [sdk-diff.md](../sdk-diff.md)。

实践：
- 选一个小型公开模型（MobileNetV2 分类或 YOLOv5nano 检测），从 PyTorch 训练/加载 → 导出 ONNX → 转 `.rknn`；每步保存中间产物和转换日志。
- 板端用 runtime 加载 `.rknn`，跑同一组输入，把板端输出和 ONNX 在 host 的输出对比（cosine similarity / 最大绝对误差）；输出一致性达标才算"转换成功"。
- 记录完整版本三元组：toolkit / runtime / 驱动 commit / 固件版本；这份基线是后续所有 N 章节的参照原点。
- 故意制造一次版本错配（如换一个旧版 runtime），观察并记录报错模式；建立"版本错配症状库"。

### 第 15N 章：FP16/INT8 与校准

模型从 FP32 量化到 INT8，体积缩 4 倍、推理快几倍，但精度会掉——这一章讲怎么把精度损失控制住，以及怎么判断"量化后还能不能用"。

**为什么 8 bit 够用？因为神经网络的权重和激活大多是"钟形分布"。** 多数值集中在均值附近，有效信息远少于 FP32 的 32 bit；用 8 bit 整数表示通常精度损失小于 1%。量化映射：把 FP32 范围 `[min, max]` 线性映射到 INT8 `[-128, 127]`，scale = `(max-min)/255`、zero-point 偏移。**对称 vs 非对称**：权重通常对称（scale = max(|w|)/127），激活通常非对称（带 zero-point）；混合精度策略由 toolkit 决定。局限：极端值（outlier）会拉大 range 损失精度，某些层（如 attention softmax）对量化敏感，需要更高精度或特殊处理。

**校准数据集决定量化质量，选错精度暴跌。** 量化需要"代表性数据"统计每层激活的分布；**校准集选错，激活范围估错、精度暴跌**。校准集要求：覆盖真实推理时的输入分布（场景、光照、目标大小），不能只用训练集的"干净样本"。校准方法：min-max（最简单）、percentile（去 outlier）、KL 散度（信息论最优）、ACIQ（自适应），toolkit 通常提供多种，对比选最优。数量典型 100-1000 张，多了不更准（边际效益递减）、少了代表性差。

**精度损失的测量和判定，要有量化标准。** 测量指标：top-1/top-5 accuracy（分类）、mAP（检测）、mIoU（分割）、cosine similarity（特征对比），按任务选对。**损失阈值**：分类任务 INT8 vs FP32 通常掉 0.5%-2%；检测任务 mAP 掉 1-3 个点常见；超过阈值要回查校准或换层精度。**关键层保精度**：把量化敏感的层（attention、最后分类头）保持 FP16/FP32，其它层 INT8——这就是"混合精度量化"。精度回归测试：模型升级、toolkit 升级、量化策略改动都要重跑完整验证集，不能只看几条样例。

**量化收益是全方位的：大小、带宽、延迟、功耗。** 模型大小 INT8 比 FP32 缩约 4x，NPU 加载更快、占内存更少；**权重读取是推理的主要带宽消耗，INT8 让带宽降 4x**，在带宽受限平台（如 RK3588 多 IP 共享 DDR）直接提速；延迟单次推理 INT8 比 FP32 快 2-10x；功耗约为 FP32 的 1/2-1/3。这些收益叠加，就是为什么产品级 NPU 推理几乎都走 INT8。

**不支持的算子的工程处理，有决策树。** 策略一：模型重写，用 NPU 支持的等价算子替换（如 `swish` 拆成 `x * sigmoid(x)`）；策略二：CPU fallback，把不支持的算子交给 CPU，其余在 NPU（性能下降但能用）；策略三：模型重构，把不支持的算子挪到能批处理的位置或合并到相邻支持算子；策略四：换模型，某些 SOTA 模型（带动态 shape 的 transformer）天然不适合固定 NPU，换等价的 NPU-friendly 模型。**决策树**：先查支持矩阵 → 算子替换 → CPU fallback（性能测过可接受）→ 模型重构 → 换模型。

实践：
- 同一模型分别用 FP16 / INT8（min-max）/ INT8（KL 散度）三种量化，在相同验证集对比精度（mAP 或 accuracy）、模型大小、单次推理延迟、功耗/温度稳态。
- 故意改坏校准集（只用纯黑图或单一场景），对比精度损失；用真实校准集回归，对比修复幅度。
- 找一个量化敏感层（如某层激活分布严重偏斜），单独保留 FP16，对比"全 INT8"vs"该层 FP16"的精度 vs 性能 trade-off。
- 选一个 NPU 不支持的算子，分别用"CPU fallback"和"等价算子替换"，对比延迟、CPU 占用、精度。

### 第 16N 章：输入、推理与后处理

模型转好了、runtime 配好了，这一章讲怎么真正跑一次推理——从预处理到后处理，以及同步异步的选择。

**预处理：resize、letterbox、normalization，三个坑。** resize 把输入缩放到模型尺寸（640×640、224×224），用 RGA（第 12 章）零拷贝完成，避免 CPU 拷；letterbox 保持长宽比缩放加 padding，YOLO 系列常用，padding 值要和训练一致（通常 114 灰）；normalization 减均值除方差，**很多 INT8 模型把 normalization 折进量化参数，输入直接喂 0-255 像素，写代码前查清**。BGR vs RGB：OpenCV 默认 BGR、PIL 默认 RGB，**模型训练时用哪种推理必须一致，错了精度掉得很明显**。

**tensor layout：NCHW vs NHWC。** NCHW（PyTorch 默认）和 NHWC（TensorFlow 默认）是两种内存布局；NPU 偏好哪个由转换工具决定，runtime 接受的输入 layout 必须匹配，否则报错或结果错。**转换 nchw↔nhwc 是 transpose，CPU 上有开销**，最好从一开始让采集/RGA 输出直接是目标 layout。

**同步推理 vs 异步推理，选错 NPU 利用率低。** 同步：提交一次推理 → 阻塞等结果 → 再提交下一次，写起来简单但 **NPU 利用率低（等待时 NPU 闲置）**；异步：提交多次推理（每提交立刻返回），结果回调或 future，NPU 可并发处理多帧，吞吐高但代码复杂。NPU 并发上限取决于核心数（多 NPU core 在 18N 展开）。**工程建议**：原型期同步（验证正确性），优化期异步（榨吞吐）；永远先测同步基准再切异步。

**多输入多输出，要同步对齐。** 多输入：模型接受多个 tensor（RGB + 深度、或两帧做光流），每个都要按 layout/normalization/尺寸准备，常出错；多输出：模型一次输出多个 tensor（检测任务同时输出 boxes + classes + masks），按 shape 解析。**输入输出对齐**：多输入要求所有输入同步到达，异步场景用同步原语（fence/future）等齐再提交。输出 zero-copy：输出 tensor 经常直接落在 dma-buf 上，下游（后处理、显示）可以零拷贝消费——**不要养成"取回 CPU buffer 再处理"的默认习惯**。

**检测后处理：NMS、坐标变换、过滤，这一段 CPU 任务写好坏差很多。** 检测模型原始输出是密集 box 候选；后处理做 score 阈值过滤、NMS（非极大值抑制）去重、坐标从模型空间映射回原图。**NMS 是 CPU 任务（NPU 一般不做），写得好坏直接吃延迟**；坐标变换（letterbox 反变换 + resize 反变换）写错会出现"box 不跟着目标"的视觉 bug。后处理可以并行化（OpenMP、NEON、多核），**后处理慢于 NPU 推理本身时，CPU 成了瓶颈**——这是优化时最该先看的一处。

**资源生命周期，长跑稳定性的关键。** runtime context / model handle / tensor buffer 启动时一次创建、长期复用，**不要每帧创建销毁**；输入输出 buffer 用 pool（3-5 个轮流用），和 dma-buf 共享对齐（第 5 章）。销毁顺序：先停推理 → 释放 tensor → 释放 model → 释放 context，乱序 use-after-free 或 hang。**长跑测试**：连续推理几小时，监控内存（runtime 是否泄漏）、NPU 占用率、温度稳态；任何"运行越久越慢"都暗示生命周期 bug。

实践：
- 编写一个**不依赖厂商 demo 外壳**的独立推理程序（自己写 main、自己管 buffer），避免"换了 demo 就不会改"的陷阱。
- 同一组输入跑 100 次推理，输出每帧总延迟、预处理耗时、NPU 推理耗时、后处理耗时；找主瓶颈。
- 故意制造错误输入（错误尺寸、错误 layout、错误 normalization），对比输出和正确版本的差异；建"输入错误症状库"。
- 长跑测试：连续推理 1 小时，每分钟记内存占用（看泄漏）、温度稳态、NPU 占用率；产出"长跑稳定性报告"。

### 第 17N 章：实时 AI 流水线

前面讲了单次推理，这一章把采集、预处理、推理、后处理、显示拼成一条实时 pipeline——这就是"摄像头 → 检测 → 画框 → 显示"的完整链。

**V4L2/ISP 输入端：采集线程只管搬 dma-buf，别做像素处理。** 摄像头经 V4L2（第 10 章）输出 YUV（通常 NV12），用 DMABUF 模式采集得到 dma-buf fd；采集线程职责是 QBUF/DQBUF 循环 + 把 fd 转交下游，**自己不要做任何像素处理**。帧率和抖动：sensor 名义 30/60 FPS，实际抖动受 ISP/V4L2 queue 深度/调度影响；采集端是 pipeline 的源，源抖动会传到全链路。

**RGA 预处理：resize + CSC + letterbox 一次做完。** RGA（第 12 章）从 V4L2 拿 dma-buf fd，做 resize + CSC（NV12→RGB）+ letterbox padding，输出符合模型输入尺寸/格式的新 dma-buf fd。**零拷贝**：V4L2 buffer 和 RGA 输入是同一块物理内存；RGA 输出是另一块 dma-buf，可以直接喂给 NPU。性能要点：单次 RGA 调用做组合操作比串行多次调用快；选 RGA 支持的格式组合避免 fallback。

**dma-buf 共享是整条 pipeline 的核心。** 从摄像头到 NPU 输入，dma-buf fd 全程流转，**物理内存拷贝次数 = 0（理想情况）**。NPU runtime 接受 dma-buf fd 作输入 tensor，用"import external memory"接口让 NPU 直接读 RGA 输出的物理页。**警惕伪零拷贝**：runtime 内部如果不真正支持 dma-buf import（或版本旧），会 fallback 到 memcpy；用第 5 章的取证方法验证。输出端同理：NPU 输出 tensor 可以落到 dma-buf，下游后处理或显示直接消费——**但后处理（NMS 等）通常必须回 CPU**。

**RKNN 推理和模型实例管理。** 推理线程：从 RGA 输出队列取 dma-buf → 准备 tensor → 提交推理 → 取输出 → 触发后处理。**模型实例启动时加载一次 `.rknn`、创建 context、长期复用，不要每帧加载模型**。并发：单 context 同步推理吞吐有限，可创建多 context（或用 NPU 的 async API）提高吞吐；多 NPU core 调度见 18N。错误恢复：单帧推理失败（IOMMU fault、模型 OOM）不应杀进程，记录错误、丢帧、继续。

**DRM 或产品界面显示。** 输出端：原始摄像头帧 + 检测结果框 + 标签，合成一帧送 DRM（第 9 章）显示。**合成策略**：(1) CPU 画框（简单但占 CPU）、(2) DRM overlay plane 叠加（零 CPU）、(3) GPU 合成（适合复杂 UI）。DRM plane 和 dma-buf：把摄像头 dma-buf 设为 primary plane、检测结果作 overlay plane，硬件合成零开销。**时间戳同步**：检测框必须画在对应原始帧上（不是延迟一帧的框），用 V4L2 timestamp 关联推理结果和帧。

**pipeline backpressure 和整体延迟分解。** backpressure（第 13 章）：NPU 推理慢于采集时，采集线程必须等；策略是丢老帧（实时性优先）还是排队（吞吐优先）。queue 深度：采集→RGA→NPU→显示每段都有 queue，深度大延迟大、深度小易抖动，典型 AI pipeline 选 2-3 缓冲。**端到端延迟分解**：采集（5-15ms）+ RGA（1-3ms）+ NPU（10-50ms，取决于模型）+ 后处理（2-10ms）+ 显示（16ms 一帧 vsync），总延迟典型 30-80ms。**优化目标**：先量出主瓶颈（多数情况是 NPU 推理本身），针对性优化（量化、模型裁剪、多核调度）；不要无脑优化每一段。

实践：
- 建立端到端实时检测：摄像头 → RGA 预处理 → NPU 推理 → CPU 后处理 → DRM 显示，稳定运行 30 分钟以上。
- 用 ftrace/perf 分解每帧延迟：采集、RGA、NPU、后处理、显示各级各占多少 ms；画直方图和时间序列。
- 优化至少一个真实瓶颈（如后处理用 NEON 加速、letterbox 改 RGA 做、或多 context 并发）；提交前后做 A/B 对比，证据可复现。
- 故意制造负载压力（采集 60 FPS 但 NPU 只能跑 30 FPS），测试 backpressure 策略：丢老帧 vs 排队，对比延迟和丢帧率。

### 第 18N 章：从 demo 到 AI 服务

跑通一条实时 pipeline 是 demo，把它做成"能长期跑、能被多个客户端调用、温度高时还能用"的服务是另一回事。这一章讲多模型调度、服务化、thermal 降级、异常恢复。

**多模型调度：一个产品经常同时跑多个模型。** 比如人脸检测 + 人脸识别 + 表情分类，每个模型有独立的 `.rknn`、独立的 context。调度策略：(1) 串行（一个跑完再跑下一个，简单但总延迟大）、(2) 并行（多 context 同时提交，NPU 内部排队）、(3) 流水（模型 A 输出喂模型 B 输入）。**资源约束**：NPU 内存有限，多模型同时加载的权重大小总和不能超；权重大时需要"按需加载/卸载"。优先级：交互式任务（用户在等）高，后台任务（统计、日志）低。

**多 NPU core 的使用，能成倍提吞吐。** RK3588 NPU 是多核结构（具体核数和拓扑以真板确认为准），每个核能独立执行一个推理任务。runtime 提供多核调度接口（指定 core mask、或让 runtime 自动调度）。**单大模型 vs 多小模型**：单大模型用满多核（core 联合执行），多小模型分散到不同 core 并发。core 亲和性：同一模型的多次推理钉到同一 core（warm cache）或分散到不同 core（避免单 core 过载）——产品级要测。

**任务队列和远程调用，把"板上的 NPU"变成"局域网内的 AI 服务"。** 任务队列：推理请求入队、worker 线程取任务执行，典型 producer-consumer，请求和执行解耦。**远程调用形态**：本地 HTTP/gRPC 服务，其它进程/设备发请求得推理结果。协议选择：HTTP/JSON（易调试）、gRPC/Protobuf（高效）、自定义二进制（最低开销）。并发模型：单 worker 串行 vs 多 worker 并发，并发数受 NPU 容量和内存限制，要测出最优并发度。

**状态监控和指标暴露，运维的命脉。** 服务级指标：QPS、p50/p99 延迟、错误率、队列长度，暴露给 Prometheus/StatsD；NPU 级指标：占用率、内存使用、温度、降频事件，用于关联"延迟尖峰"和"NPU 降频"；业务级指标：单类目准确率（线上分布 vs 训练分布）、误报/漏报率。**监控必须可视化**（Grafana 之类），运维依赖这些数据。

**thermal throttling 和降级策略：温度高时还能用，只是变慢，而不是 crash。** 推理任务持续高负载会触发 thermal throttling（第 7 章）；NPU 频率下降 → 推理延迟增大 → 服务延迟尖峰。**降级策略**：(1) 检测到降频时降低推理频率（如 30→15 FPS）、(2) 切换到更小模型（精度换性能）、(3) 部分请求路由到备用节点。**优雅降级 vs 服务中断**：产品要求"温度高时还能用，只是变慢"，而不是"温度高就 crash"；前者是工程态度，后者是 demo。恢复：温度回落后自动升级回原性能，**不要因为短时高温永久降级**（"卡死在低性能"是 bug）。

**异常恢复：模型错误、进程崩溃、设备故障。** 模型错误（单次推理 OOM、IOMMU fault）应记日志、丢帧、继续，不让整个服务挂掉；进程崩溃用 systemd/supervisor/k8s 守护，崩溃自动重启，重启后恢复推理能力（model 自动重新加载）；设备故障（NPU 硬件问题，罕见但发生）应能检测（health check 推理）、报警、降级到 CPU 推理（性能差但服务不中断）。**长稳测试**：连续 7x24 跑一周，统计 crash 次数、内存泄漏、温度稳态、累积延迟分布——任何"运行越久越慢"都暗示生命周期 bug。

方向产出：
- 一条真实输入到推理结果的完整流水线（输入源 + 预处理 + 推理 + 后处理 + 输出）；
- 精度报告（验证集 mAP/accuracy、量化前后对比）；
- 性能报告（延迟 p50/p99、吞吐、CPU/内存/温度稳态、长跑稳定性）；
- 服务化形态（HTTP/gRPC 接口 + 监控指标 + 异常恢复策略）。

## 7. 媒体方向

## M1：编解码与数据格式

### 第 14M 章：视频压缩和 MPP 接口

这一章讲视频压缩的基本概念落到 MPP 上。核心是理解 I/P/B 帧和 GOP——它们决定了压缩率、延迟、随机访问能力的取舍。

**帧内压缩 vs 帧间压缩，先分清。** 帧内（intra）只用本帧内的空间冗余（相邻像素相似），如 JPEG，每帧独立可解但压缩率低；帧间（inter）用相邻帧的时间冗余（前后帧大部分像素不变），如 P/B 帧，压缩率高但需要参考帧、解码有依赖。**现代视频 codec（H.264/H.265/AV1）混合使用**：I 帧（帧内，定期刷新）+ P 帧（前向预测）+ B 帧（双向预测）；理解 I/P/B 才能理解延迟和压缩率的来源。

**GOP、I/P/B 帧与随机访问。** GOP（Group Of Pictures）是一个 I 帧到下一个 I 帧之间的序列；**GOP 长度决定压缩率（长 GOP 压缩率高）与随机访问能力（短 GOP 易 seek）**。I 帧（关键帧）帧内编码，独立可解，占码率最大，但可随机访问——产品中需要定期 I 帧保证 seek、错误恢复、录像分段。P 帧（前向预测）依赖前面的 I/P 帧，压缩率高、码率低。B 帧（双向预测）依赖前后帧，压缩率最高，但**引入"重排延迟"**（B 帧要等后面的参考帧才能解），实时低延迟场景经常禁用 B 帧。

**码率与质量的权衡，CBR/VBR/CQP 各有场景。** 码率（bitrate）是每秒输出的压缩数据量（kbps/Mbps），码率越高画质越好但带宽/存储消耗大。**CBR（固定码率）**码率恒定，适合流媒体（带宽可预测），缺点是复杂场景画质塌、简单场景浪费；**VBR（可变码率）**按需分配，固定质量，缺点是码率峰值不可预测；**CQP/CRF（固定质量）**直接固定质量参数，现代流媒体常用"VBR + 码率上限"折中。质量 metric：PSNR（客观）、SSIM/VMAF（主观感受），**不能用"看起来还行"做产品指标**。

**codec profile 和产品选择。** profile（H.264 Baseline/Main/High、H.265 Main/Main10）是标准内的功能子集，选择决定支持的工具集（B 帧、10-bit、CABAC）；level 是分辨率/帧率/码率上限档位，选错会"能编但解码端不支持"。**产品决策**：消费级流媒体用 Main/High（兼容性好）；实时通信用 Baseline（无 B 帧、低延迟）；专业制作用 Main10（10-bit 高动态范围）。标准化 trade-off：选新 codec（H.265/AV1）省带宽但兼容性差；选旧 codec（H.264）兼容性最好但带宽大。

**packet、frame、buffer 的物理意义，和第 11 章一致。** packet（压缩域）是编码器输出的字节流，对应一个 NAL 或 access unit；frame（图像域）是解码器输出的图像（YUV/RGB）；buffer（载体）是 dma-buf，MPP 内部管理 pool 避免每帧分配。**流动**：encoder 吃 frame buffer 产 packet buffer；decoder 吃 packet buffer 产 frame buffer；**零拷贝 pipeline 要求这些 buffer 全程是 dma-buf fd**（第 5 章）。

实践：
- 用 MPP 编码一段固定 YUV 测试素材（标准 4K YUV 序列），分别用 CBR/VBR/CQP 三种码率控制，对比输出码率曲线、PSNR/SSIM、文件大小。
- 改 GOP 长度（30 vs 120 vs 300），对比压缩率和"随机 seek 后到下一个 I 帧的延迟"；建 GOP 决策表。
- 用 B 帧 vs 不用 B 帧，对比编码延迟（B 帧引入重排延迟）和压缩率；评估实时通信场景的 trade-off。
- 把 encoder 输出的 packet 落文件、再用 decoder 解回来，对比 YUV 像素差异，量化"压缩 → 解压"的精度损失。

### 第 15M 章：MPP—RGA—DRM

这一章把第 11 章的 MPP、第 12 章的 RGA、第 9 章的 DRM 拼成"硬件解码 → 处理 → 显示"的零拷贝链。音视频同步是进阶项。

**MPP 解码器的输出形态。** decoder 输出 YUV frame buffer（NV12/NV16/P010 等），通过 dma-buf fd 形式交出（第 11 章）；用户态拿到的是 fd 不是裸内存。**输出 layout** 可能是 tile 或 linear（取决于 VPU 实现），tile 的话下游必须支持同 modifier 或经 RGA 转 linear；输出尺寸可能含 stride padding，width 不是按像素数而是按硬件对齐后的字节数，**stride 必须传给下游，不能假设等于 `width × bpp`**。buffer pool：decoder 内部维护 N 个 buffer 轮转（典型 4-8 个），pool 大小影响抖动抗性。

**RGA 后处理：格式转换 + 缩放。** decoder 输出格式（如 NV12）经常和显示期望格式（如 XRGB8888）不一致，中间需要 CSC + 格式转换，用 RGA（第 12 章）完成。缩放：解码分辨率（如 1080p）和显示分辨率（如 4K）不同，用 RGA 缩放，RGA 支持单次组合操作（CSC + 缩放 + 旋转）。**dma-buf 链条**：decoder 输出 dma-buf fd → RGA 接受 dma-buf fd、输出新 dma-buf fd → DRM 接受 dma-buf fd 显示，**物理内存零拷贝（理想情况）**。警惕伪零拷贝：每段都查 dma-buf 共享是否真的成立（第 5 章），不要假设"MPP + RGA + DRM"就自动零拷贝。

**DRM 显示：plane 配置和 vsync 同步。** 把 RGA 输出的 dma-buf 作为 DRM plane 的 framebuffer，用 atomic modesetting（第 9 章）提交。**vsync 同步**：每个 atomic 提交在下一个 vsync 边界生效，提交太快会被阻塞或排队。多 plane：可以同时显示多个 framebuffer（视频 + OSD + 字幕），硬件合成零开销，比 GPU 合成省 CPU。page flip 切换 framebuffer 不撕裂。**延迟测量**：从 decoder DQBUF 到 DRM vsync 的时间，是"解码到显示"端到端延迟的核心部分。

**音视频同步（进阶），是媒体产品里最容易翻车的部分。** 主时钟选择：audio clock 是主（音频采样率精确），video PTS 追随；或反过来，典型选 audio。PTS（Presentation Time Stamp）：每帧带"应该在什么时刻显示"的时间戳，显示端按 PTS 排序、早到等、晚到丢。**同步策略**：视频 PTS 早于 audio → 等；视频 PTS 晚于 audio → 丢帧追；漂移过大 → 重同步。漂移测量：连续记 video PTS - audio PTS 差值画曲线，**漂移超过 50ms 用户能感知**。建议先做"无 audio 的视频 pipeline"，再加同步。

**端到端性能取证，必测六项。** (1) 复制次数（dma-buf bufinfo 验证）、(2) CPU 占用（perf）、(3) 解码延迟（DQBUF 时间戳）、(4) 显示延迟（vsync 时间）、(5) 丢帧率、(6) 同步误差（音视频 PTS 差）。**长跑测试**：连续播放 1 小时以上，监控温度、内存、CPU、丢帧率，任何"越跑越卡"都暗示生命周期 bug。对照基线：和"软解 + CPU 拷贝 + 普通 display"做 A/B 对比，量化"硬件零拷贝 pipeline"的收益。

实践：
- 建完整的"MPP 解码 → RGA → DRM"硬件 pipeline，硬件解码一段 4K 视频并稳定显示；记录每秒 FPS、CPU 占用、温度稳态。
- 用 dma-buf bufinfo 验证 buffer 共享：从 decoder 输出到 DRM 显示，物理内存拷贝次数应为 0；不是就找拷贝点并修复。
- 加 audio 输出（ALSA）和音视频同步，连续播放 1 小时；记录漂移曲线和丢帧率；评估同步质量。
- 和"软解 + CPU 拷贝 + 普通 display"做对照实验，量化 CPU 占用、带宽、延迟差异；形成"硬件 pipeline vs 软件 pipeline"对比报告。

必须记录：复制次数（dma-buf bufinfo 实证）、CPU 占用（perf stat）、解码延迟（DQBUF 时间戳）、显示延迟（vsync 时间）、丢帧率与同步误差。

### 第 16M 章：V4L2/ISP—MPP 编码

第 15M 是"解码到显示"，这一章反过来——"采集到编码"，把摄像头输入压成视频流或录像文件。

**摄像头格式协商和 ISP 输出。** sensor 输出 RAW（第 10 章），经 ISP 输出 YUV（NV12 最常见）；encoder 接受的输入通常是 YUV，所以 ISP→encoder 是天然搭档。**格式协商**：ISP 支持的输出格式 × encoder 支持的输入格式 × RGA 中间转换（如果需要）的交集，选错就协商失败。分辨率：sensor 原生（如 3840x2160）→ ISP 裁剪 → encoder 输入，encoder 通常支持任意尺寸但有对齐要求（如 16 的倍数）。帧率：sensor 30/60 FPS → ISP → encoder，encoder 必须跟上采集帧率，否则降帧（采集端丢帧或 encoder 跳帧）。

**编码输入格式和 stride 对齐。** encoder 输入 NV12 / NV16 / P010 等，选哪种取决于目标 codec profile（8-bit vs 10-bit）和下游播放兼容性。**stride 对齐**：encoder 要求 input stride 按 16/32/64 字节对齐，ISP/RGA 输出的 stride 必须匹配，否则 encoder 报错或画面错位。buffer 起始地址通常要求按页（4K）对齐，dma-buf 自动满足，userptr 模式要小心。多 plane：YUV 4:2:0 是两个 plane（Y 一个、UV 交错一个），encoder 接受多 plane 输入，每个 plane 独立 fd 或独立 offset。

**码率控制和产品策略，按场景选。** 实时直播：CBR 或 VBR+上限（带宽可预测），低延迟（无 B 帧、短 GOP）；录像存储：VBR（按需分配码率），中等延迟（可接受 B 帧、长 GOP 省空间）；监控：CBR + 低帧率（如 15 FPS）+ 关键帧间隔长（如 5 秒一个 I 帧），存储空间与画面质量的折中。**关键参数**：target bitrate、max bitrate、GOP 长度、I 帧间隔、QP 范围、码率控制模式，调参影响最终产品质量。

**关键帧管理。** 强制 I 帧：场景切换检测、用户请求、错误恢复时主动触发，MPP 提供 force-IDR 接口。**I 帧间隔**：固定（每秒一个）vs 自适应（场景变化时），产品通常选固定（可预测）+ 场景切换强制 I。关键帧质量：I 帧质量决定后续 P 帧的质量上限，I 帧 QP 通常比 P 帧低（更多 bit）。**录像分段**：每个分段开头必须是 I 帧，分段策略和 I 帧间隔要协调。

**文件输出和网络输出，产品经常双输出。** 文件输出：encoder 产 packet → muxer（封装成 MP4/MKV）→ 写文件，muxer 要处理 PTS、索引、元数据；网络输出（流媒体）：encoder 产 packet → RTP/RTSP/RTMP/SRT/WebRTC 封装 → 发包，实时性要求高、容错性要求高。**双输出**：同时录像 + 直播（同一 encoder 输出双路 packet 流），产品常见，但码率控制要协调两路需求。容器选择：MP4（兼容性最好）、MKV（开放、多音轨字幕）、FLV（直播老标准）、HLS/DASH（自适应流媒体）。

实践：
- 建立"摄像头 V4L2 → ISP → RGA → MPP 编码 → 文件"完整 pipeline；录制 1 分钟 1080p H.264 视频，验证画质（PSNR）、文件大小、编码延迟。
- 同一输入源同时输出"录像文件 + 网络流"两路；分别测两路的码率、延迟、丢帧率。
- 调整码率控制（CBR vs VBR vs CQP）和 GOP 长度，对比输出体积、画质、随机 seek 延迟；形成"码率控制决策表"。
- 测试错误恢复：故意制造输入中断（拔摄像头）或单帧损坏，观察 encoder 是否能恢复（下一个 I 帧重置）；记录恢复时间。

### 第 17M 章：多流、队列和背压

单路 pipeline 跑通后，这一章讲多路——同时解码/编码多路流，以及为什么"内存带宽"是多路场景的第一个天花板。

**多路解码和多路编码，资源是硬约束。** 多路解码场景：同时播放多个视频流（监控墙、多机位回放），每路一个 decoder 实例；多路编码场景：多个摄像头同时编码（多路监控录像），每路一个 encoder 实例。**硬件资源约束**：VPU 有路数上限（同时运行的 decoder/encoder 实例数），超限创建失败或性能塌陷。调度：多路之间共享 VPU 时间，runtime 内部调度；高优先级路（正在录像）应优先于低优先级路（预览）。

**buffer pool 和内存占用，多路叠加线性增长。** 每路 pipeline 维护自己的 buffer pool（采集 4-8 + 解码 4-8 + 显示 4-8），**多路叠加内存占用线性增长**。pool 共享：高负载场景可考虑共享 pool（多路 decoder 输出到同一组显示 buffer），但实现复杂、易出错。**内存预算**：4 路 4K 解码 + 8 buffer = 数百 MiB，产品级要预算总内存避免 OOM。**CMA 容量**（第 3 章）是上限，多路高负载要确认 CMA 够用。

**内存带宽是多路的最大瓶颈，不是算力。** 每路 pipeline 每秒消耗 DDR 带宽（输入 + 多次中间 buffer + 输出），**多路叠加，带宽经常先饱和**。带宽账本（第 3 章）：4 路 4K@60 NV12 解码 ≈ 4×60×12MB = 2.88 GB/s 单向，加上中间 buffer 和显示输出，轻松超过 DDR 持续带宽。优化：减少中间拷贝（零拷贝）、用更低带宽格式（NV12 vs P010）、降帧率、降分辨率——**带宽账本必须算清楚**。检测：DDR 带宽监控（如有硬件计数器）或通过性能塌陷反推；带宽饱和的表现是"加一路就全线掉帧"。

**queue 深度和背压，单路满不能拖累其它路。** 每路 pipeline 的 queue 深度独立；总 queue 深度 = 路数 × 每路深度，影响总延迟和总 buffer 占用。**背压**（第 13 章）：单路下游满了，单路上游停，**不能跨路影响**（一路慢不应该拖累其它路）。全局资源竞争：DDR 带宽或 VPU 时间成为瓶颈时，多路会互相影响，需要全局调度（按优先级分配资源）。优先级：录像 > 直播 > 预览，高优先级路保证质量，低优先级路可降级。

**丢帧策略和过载降级，主动降级比被动丢帧好。** 丢帧时机：采集端丢（丢老帧保实时）、解码端丢（输入 queue 满丢 packet）、显示端丢（vsync 慢丢旧 frame）。**丢帧策略**：(1) 丢老帧（保实时，适合直播）、(2) 丢新帧（保连续，适合录像）、(3) 丢 P 帧（保 I 帧，避免大块花屏）。**过载降级**：检测到持续过载时主动降级（降帧率、降分辨率、降码率、关停低优先级路），而不是被动丢帧导致质量塌陷。健康指标：每路 FPS、丢帧率、queue 长度、延迟、码率，连续监控并触发自动降级。

实践：
- 跑 4 路 1080p 同时解码 + 显示；测每路 FPS、总 CPU 占用、总内存占用、DDR 带宽、温度稳态。
- 逐步增加路数（4 → 6 → 8）直到出现掉帧或温度降频；记录"最大可持续路数"。
- 实现"过载降级"策略：检测到掉帧率超阈值时自动降帧或降分辨率；对比启用 vs 不启用降级的稳定性差异。
- 优先级测试：把其中一路设为高优先级（正在录像），其它为低优先级（预览），观察资源竞争时优先级是否生效。

### 第 18M 章：长期运行的媒体服务

把媒体 pipeline 做成"7x24 稳定跑、断流能重连、存储不爆、进程崩了能恢复"的产品级服务，这一章是 M 方向的收口。

**传输协议选择，按延迟和兼容性权衡。** RTSP：传统监控标准、低延迟、TCP/UDP 可选，适合 IP 摄像头、NVR；RTMP：直播老标准、CDN 广泛支持，逐渐被 SRT/WebRTC 替代；**SRT（Secure Reliable Transport）**：基于 UDP 的可靠传输、抗丢包、加密，现代直播新选择；**WebRTC**：超低延迟（<500ms）、浏览器原生支持，适合互动直播、远程控制；HLS/DASH：基于 HTTP 的自适应流媒体、高兼容性，延迟大（秒级），适合点播和非互动直播。**选择依据**：延迟需求、客户端兼容性、网络条件、CDN 支持，没有通用最优。

**断流重连和网络鲁棒性，真实网络的必修课。** 客户端断连：服务端应检测（keepalive/timeout）、保留上下文一段时间、自动重连尝试。**网络抖动**：用 jitter buffer（接收端缓冲）平滑，缓冲大延迟大、缓冲小易卡顿。错误恢复：丢包重传（NACK）、前向纠错（FEC）、关键帧请求（PLI），不同协议支持度不同。**网络质量自适应**：带宽估计（如 GCC 算法）→ 动态调整码率 → encoder 收到新码率后调整，这是现代流媒体的核心。

**录像分段和存储管理，否则磁盘早晚会爆。** 录像分段：长时间录像切成多个文件（如每 10 分钟一段），便于管理和回放，**分段边界必须是 I 帧**。存储空间管理：循环覆盖（旧录像自动删除）、按容量阈值清理、按时间保留，产品策略要明确。索引：每段录像建索引（开始时间、结束时间、关键帧位置），支持快速 seek，**无索引的录像难用**。文件系统选择：ext4（通用）、XFS（大文件优）、F2FS（闪存优），录像场景的写入模式（大块顺序写）影响选择。

**进程守护和健康检查，服务不能因为一个 bug 挂掉。** 进程守护：systemd unit / supervisor / 自写 watchdog，媒体服务进程崩溃自动重启。**健康检查**：定期探测服务状态（HTTP ping、内部心跳、关键资源占用），异常时报警 + 重启。资源监控：CPU、内存、温度、磁盘空间、网络流量，任何一项异常都可能暗示服务故障。日志：结构化日志（JSON）便于分析，日志分级，磁盘日志循环避免写满。

**指标暴露和服务化，运维要看得到。** 业务指标：在线用户数、每路码率、延迟分布、丢帧率、错误率，暴露给监控系统（Prometheus/Grafana）。接口：HTTP API（用户管理、流管理、配置）、WebRTC 信令、RTSP 控制。多租户：单台服务多用户时，资源隔离（每用户的路数上限、带宽限额），防止一个用户耗尽资源。**配置热更新**：调整码率、分辨率、启用/禁用流时不重启服务，通过信号或控制接口触发。

方向产出：
- 一条硬件媒体流水线（采集/解码 → 处理 → 编码 → 输出）；
- 长时间运行报告（24 小时以上，含稳定性、温度、内存泄漏、丢帧率）；
- 网络鲁棒性报告（断流重连、网络抖动、带宽自适应）；
- 存储管理方案（分段策略、循环覆盖、索引）；
- 监控与告警（指标暴露、健康检查、日志）。

## 8. Android 方向

Android 方向使用 Rockchip Android SDK 时，必须记录 SDK、内核、固件和板卡的准确版本，不照搬厂商文档。

## D1：Android 系统结构

### 第 14D 章：AOSP、Rockchip SDK 与分区

Android 方向是 RK3588 上"产品化"最重的一块。这一章先建框架：AOSP 是什么、vendor BSP 干什么、分区怎么切。**用 Rockchip Android BSP 时，必须记录 SDK、内核、固件、AOSP 版本与板卡的准确版本组合，不照搬厂商文档**；具体 Android 版本（13/14）和 GKI 版本以立项时选定为准。

**AOSP 和 vendor BSP 的分层。** AOSP（Android Open Source Project）是开源的应用框架、运行时（ART）、核心服务，不含厂商硬件专属代码；vendor BSP（Board Support Package）是厂商提供，含内核补丁、HAL 模块、固件、驱动、设备树，让 AOSP 能在具体 SoC/板卡上跑。**关系**：AOSP 是上游、vendor BSP 是下游适配，版本必须严格匹配（AOSP 13 ↔ 特定 kernel ↔ 特定 HAL）。**和 Linux 发行版的根本差异**：AOSP 不是"Linux 发行版"，它的 init、用户模型、权限（SELinux 强制）、应用模型（APK + ART）完全不同——把 Linux 习惯带到 Android 是常见错误。

**Android 分区模型，这是 Android 区别于 Linux 的第一道门槛。** `boot`（kernel + ramdisk，含 init 第一阶段）、`vendor_boot`（vendor kernel module + ramdisk，GKI 时代产物，让 kernel 和 vendor 模块解耦）、`system`（AOSP 系统代码：System UI、Settings、Telephony Framework）、`vendor`（厂商专属：HAL、驱动固件、厂商 APK）、`product`（OEM 定制：启动器、预装应用、主题）、`userdata`（用户数据，恢复出厂时清空）。**A/B 双分区**：boot_a/boot_b、system_a/system_b 等，升级写另一槽、重启切换、失败回滚，现代 Android 标配。

**GKI 和 vendor kernel 边界。** GKI（Generic Kernel Image）是 Android 12+ 强制要求，内核通用部分（核心 + 通用驱动）和 vendor 部分（板专属驱动）解耦，vendor 部分作为可加载模块。**意义**：通用内核能跨 SoC 共享、安全补丁统一推送，vendor 模块由厂商各自维护。版本协调：GKI 内核版本（5.10、5.15、6.1）必须和 AOSP 版本、vendor module ABI 对齐，错版本无法加载模块。**具体到 RK3588 Android**：选定 Android 版本对应的 GKI 内核版本以立项决策为准，rk-forge 不预设。

**adb、fastboot、recovery 工具链，Android 调试三件套。** adb（Android Debug Bridge）是用户态调试通道，`adb shell`、`adb push/pull`、`adb logcat`、`adb install`，开发期主力；fastboot 是 bootloader 级烧录和控制，`fastboot flash boot boot.img`、`fastboot reboot recovery`，比 adb 更底层；recovery 是独立于主系统的最小环境，负责 OTA 升级、恢复出厂、备份恢复，A/B 时代 recovery 也可能合并到 boot/vendor_boot。**和 Linux 调试的差异**：Linux 用 ssh + dmesg，Android 用 adb + logcat，调试方式根本不同。

**Linux 和 Android 启动链的根本差异，这块搞不清就会"把 Linux 假设照搬到 Android"。** Linux：U-Boot → kernel → init（systemd/busybox）→ 用户进程，进程模型松散、权限靠 UID；Android：bootloader → kernel + ramdisk → init → Zygote（fork 出所有 Java 进程）→ System Server（系统服务）→ Launcher（用户看到桌面），高度结构化、SELinux 强制访问控制。**差异要点**：init 用 `.rc` 文件不是 systemd unit、Java 应用都从 Zygote fork（共享启动开销）、进程间通信用 binder 不是 socket/D-Bus、权限模型基于 SELinux + Android permission。

实践：
- 列出板上所有分区（`adb shell ls -l /dev/block/by-name/`），标注每个分区的角色、大小、文件系统、是否 A/B。
- `adb shell getprop` 列出关键属性（AOSP 版本、kernel 版本、SDK 版本、vendor 信息）；形成"系统身份卡"。
- 跟踪一次启动：从 bootloader 到 Launcher，用 `dmesg` + `logcat -b all` 记录每阶段耗时和关键事件；画"启动时间线"。
- 分析一次失败启动（如 system 分区损坏、SELinux 阻断关键服务），从 logcat 反推原因；形成"启动失败诊断清单"。

### 第 15D 章：init、SELinux、Zygote 与 System Server

这一章讲 Android 用户态怎么起来——init 怎么读 rc、property 系统怎么工作、SELinux 怎么挡、Zygote 怎么 fork 出所有应用。**SELinux 是 Android 工程师最容易卡住的地方**，重点讲。

**init 和 rc 文件。** init 是 Android 用户态的 PID 1，从 ramdisk 启动；它读 `.rc` 文件（`init.rc`、`ueventd.rc`、各阶段 vendor rc）决定启动哪些服务、挂载哪些分区、设置哪些属性。**rc 语法**：`service`/`on`/`setprop`/`start`/`stop`，与服务管理、属性触发、动作执行有关。触发器（trigger）基于属性变化或事件（如 `boot` 阶段、`property:vold.decrypt=trigger_restart_framework`）触发动作，rc 文件之间的依赖通过 trigger 链起来。**和 systemd 的差异**：Android init 没有 unit 依赖图、没有 socket activation（早期）、配置语法完全不同，习惯 systemd 的开发者要重学。

**property 系统。** property（属性）是系统级 key-value 配置，`ro.build.fingerprint`、`sys.usb.config`、`dev.bootcomplete` 等，进程间共享状态。实现：property service（init 内）+ 共享内存区域 + SELinux 限制读写权限，每个属性有访问控制。**setprop / getprop** 是用户态命令；某些属性（`ro.` 前缀）只读、某些（`persist.` 前缀）持久化到 `/data`。调试用途：很多服务的启停由 property 触发，改 property 是测试系统行为的常用手段。

**SELinux：强制访问控制，Android 工程师最容易卡住的地方。** SELinux 是 Android 强制的安全机制（since Android 5），每个进程、文件、socket 都有 security context，策略决定谁能访问谁。**模式**：permissive（只记日志不强制，开发期）、enforcing（强制执行，产品必选），正式产品必须 enforcing。**denial 日志**：`logcat -b events | grep avc` 或 `dmesg | grep denied`，每条 denial 说明"谁（context）想做什么（perm）到谁（target context）被拒绝"。**修复策略**：写 `allow` 规则到 `.te` 文件，策略按 service 分（如 `surfaceflinger.te`、`vold.te`）。**工程纪律**：产品发布前必须 pass SELinux 强制模式，permissive 只能开发期用。

**Zygote、System Server、应用进程模型。** Zygote 是预启动的"模板进程"，加载完核心库后等 fork，**每个应用进程从 Zygote fork 出来，省去重复加载开销**；System Server 是 Android 的"大脑"，从 Zygote fork，运行所有核心系统服务（ActivityManager、WindowManager、PackageManager、PowerManager...）；应用进程从 Zygote fork，运行 APK 的 Java 代码（ART 虚拟机），每个应用独立进程、独立 UID、独立 SELinux context。**启动顺序**：init → Zygote → System Server → 系统服务就绪 → Launcher 启动，任何一环卡住用户就看不到桌面。

**bootanimation 和启动完成判定。** bootanimation 是开机动画进程，在 System Server 启动后、Launcher 启动前显示，告诉用户"系统正在启动"。`sys.bootcomplete` property 标记启动完成，很多服务监听它触发后续动作。**启动失败的典型场景**：(1) System Server 崩溃导致 bootanimation 后卡黑屏、(2) 某个关键服务（如 PackageManager）反复重启导致启动循环、(3) SELinux denial 阻断关键操作。调试：`logcat -b all` + `dmesg` + `adb bugreport`，分析"卡在哪一步"是关键。

实践：
- 跟踪一个系统服务的启动：从 rc 文件定义 → init 启动 → SELinux 检查 → 服务运行，用 logcat 和 ps 验证。
- 分析一组 `.rc` 文件，画"启动顺序依赖图"（哪个 service 触发哪个 trigger）。
- 故意触发一次 SELinux denial（如让一个 process 访问不该访问的文件），用 `logcat -b events` 找到 denial，写出对应的 `allow` 规则；验证加入策略后不再 denial。
- 分析一次"bootanimation 后卡黑屏"的失败（真故障或模拟）：用 logcat 反推卡在哪一步（System Server 崩溃？关键服务超时？SELinux 阻断？）。

### 第 16D 章：从内核设备到 Android 服务

这一章讲 Android 的 IPC 和硬件抽象——binder 怎么工作、HAL 怎么把硬件能力暴露给上层、AIDL 怎么定义接口。理解这套，才能把一个内核能力接到 Android 应用。

**Binder：Android 的 IPC 基石。** Binder 是 Android 自有的 IPC 机制，所有进程间通信用它（Java 层、Native 层都基于它）。**内核驱动（`/dev/binder`）一次拷贝**（发送方用户态 → 内核 → 接收方用户态映射），比 socket（两次拷贝）快，比共享内存（零拷贝）慢但更易用。ServiceManager 是服务注册中心，每个服务启动时注册、客户端通过名字查询，这是 Android 服务发现机制。性能：binder 单次调用典型几十微秒，高频调用（如每帧渲染）需要批处理或异步。

**HAL（Hardware Abstraction Layer）。** HAL 让上层 Framework 不依赖具体硬件，厂商实现 HAL、Framework 调用 HAL 接口。**形态演进**：旧版 HAL（C 库 + dlopen）、HIDL（HAL Interface Definition Language，Android 8+ Treble）、AIDL（Android 11+ 主推）。**关键意义**：HAL 让 Framework 和 Vendor 解耦、可独立升级（Treble），这是现代 Android 可维护性的基础。实例：Camera HAL、Audio HAL、Graphics HAL（HW Composer）、Gnss HAL、Sensors HAL，每个对应一类硬件能力。

**AIDL：现代接口定义语言。** AIDL（Android Interface Definition Language）定义跨进程接口的语言，编译器生成 Java/C++ 桩代码，调用远程方法像调用本地方法一样。**HIDL → AIDL**：Android 11+ 推荐 AIDL，逐步替代 HIDL，新接口必须用 AIDL。接口版本化：AIDL 支持接口版本（versioned interface），允许向后兼容扩展，这是稳定 ABI 的基础。**实现一个 HAL**：定义 `.aidl` → 编译生成桩 → 实现 stub 类 → 注册到 ServiceManager → 客户端 `getService`。

**Framework 和公开 API。** Framework（应用框架层）是 `android.*` 包，暴露给应用调用的 API（`Camera2`、`MediaCodec`、`SurfaceView`），API 稳定、版本化。**应用调用链**：App → Framework API → 通过 binder 调用系统服务 → 系统服务调用 vendor HAL → HAL 调用内核驱动。API vs 内部接口：应用只能用公开 API（`<uses-sdk>` 控制），不能用内部接口，这是 Android 安全模型的一部分。兼容性：Android 版本升级时 API 可能新增/废弃，应用要适配 `targetSdkVersion`。

**SELinux 和权限，两层安全模型。** 应用权限：Manifest 声明（`CAMERA`、`INTERNET`），危险权限运行时请求，用户可见的安全模型；SELinux 是内核级强制访问控制，应用和系统服务都受约束，和 App 权限是不同层次。**Vendor 服务权限**：vendor HAL 进程有自己的 SELinux domain，写 HAL 时同步写 `.te` 文件配置权限。调试：denial 日志（`logcat -b events | grep avc`），产品发布前必须 pass enforcing 模式下所有 denial。

**四层调用：kernel → HAL → Framework → App，这是 Android 系统工程师的基本功。** 一次"用户拍照"的完整链路：App 调 `Camera2` API → Framework CameraService → Camera HAL（vendor）→ 内核 V4L2 驱动 → 硬件 ISP。**每一层都有明确职责**：kernel 管硬件、HAL 抽象硬件差异、Framework 提供稳定 API、App 调用 API。调试跨度：bug 可能在任一层，要会用 `adb logcat`（看 Framework）、`dumpsys`（看服务状态）、HAL 日志（看 vendor 实现）、`dmesg`（看 kernel）。**理解这四层是 Android 系统工程师的基本功**，任何产品级问题都需要跨层定位。

实践：
- 把一个简单真实硬件能力（如 GPIO 控制 LED，或读传感器）从内核暴露到 Android 应用：写内核驱动 → 写 HAL（AIDL）→ 注册到 ServiceManager → 写 Framework API 或直接用 manager → 写 App 调用。
- 保存每一层证据：内核 dmesg、HAL 启动日志、ServiceManager 注册记录、App 调用结果。
- 故意制造一次跨层错误（如 HAL 没注册、SELinux denial、内核驱动 crash），从 logcat 反推错误层级；建"跨层错误诊断清单"。
- 测量一次完整调用链延迟：从 App 调用到内核响应，分解每层耗时；评估四层架构的延迟开销。

### 第 17D 章：Android 人机交互链

这一章讲 Android 怎么把画面、声音、输入接到用户——SurfaceFlinger、HWC、Audio HAL、Input。底层是 Linux 的 DRM/ALSA/Input，Android 在上面加了一层 HAL 和 Framework。

**SurfaceFlinger：Android 的合成系统服务。** SurfaceFlinger 接收所有应用的 Surface（每个应用窗口一个），合成最终画面送显示。**和 Linux DRM 的关系**：SurfaceFlinger 是 DRM 的用户态消费者（第 9 章），把多 Surface 合成后用 DRM atomic 提交。Surface 类型：应用 Surface（一个窗口）、StatusBar、NavigationBar、Wallpaper，每个有 z-order。工作流：应用通过 BufferQueue 提交 buffer → SurfaceFlinger 接收 → 合成（GPU 或 HW Composer）→ 提交到 DRM → vsync 显示。

**Hardware Composer（HWC），Android 流畅度的关键。** HWC 是硬件合成器 HAL，让 SurfaceFlinger 能用 SoC 显示硬件（DRM plane）做合成，而非全部用 GPU 合成。**性能意义**：硬件合成零 GPU 开销、零 CPU 开销，让 GPU 空出来给应用——这是 Android 流畅度的关键。决策：SurfaceFlinger 把"哪些 Surface 用 HW 合成、哪些用 GPU 合成"的决策交给 HWC，HWC 根据硬件 plane 数量和能力决定。**和 DRM plane 的关系**：每个 HW 合成的 Surface 对应一个 DRM plane，plane 数量决定 HWC 能合成多少层。

**Audio HAL 和 AudioFlinger。** AudioFlinger 是 Android 的音频服务，管理音频流、混音、路由，调用 Audio HAL 和 ALSA（第 9 章相关）通信；Audio HAL 是厂商实现，封装底层 ALSA/PCM 操作，处理输入输出流、采样率转换、音量控制。**和 Linux ALSA 的关系**：Audio HAL 是 ALSA 的用户态封装，Linux ALSA 暴露 PCM 设备，Audio HAL 选择并配置。路由：扬声器、耳机、蓝牙、HDMI 音频，产品级要处理路由切换（如插耳机自动切换输出）。

**Input 子系统和 EventHub。** InputReader 从内核 `/dev/input/event*` 读事件（按键、触摸、鼠标），转换为 Android InputEvent；InputDispatcher 把 InputEvent 路由到正确的窗口（焦点窗口），WindowManager 维护焦点信息。**触摸事件流**：DOWN → MOVE → UP，多点触控（多个 pointer id 同时），手势识别（点击、长按、拖拽）在应用层做。输入延迟：从硬件事件到应用响应典型 10-30ms，延迟大用户感知卡顿。

**触摸、多屏、旋转的产品场景。** 多屏：RK3588 可同时输出多路显示（HDMI + DSI 等），Android 多屏支持需要把每个屏幕作为独立 Display 暴露给 Framework；旋转：屏幕旋转 90/180/270 度，需要 SurfaceFlinger 和 HWC 配合（合成时旋转、或硬件 plane 旋转），触摸坐标也要跟着转；**触摸和显示的对应**：每个触摸屏绑定到正确的 Display，多触摸屏产品要处理 device-to-display 映射。热插拔：HDMI/USB 触摸的热插拔要 SurfaceFlinger 和 InputReader 同时响应，产品级健壮性要求。

**Linux DRM/ALSA 和 Android HAL 的边界。** Linux 层（DRM、ALSA、input）是底层，Android HAL 是它们的用户态封装 + Android 化（接 binder、加权限、加版本化）。**调试分界**：底层硬件 bug（DRM fault、ALSA underrun）看 dmesg，上层 Framework 问题（SurfaceFlinger 行为）看 logcat。性能：HAL 增加了一层 binder 调用，开销几十微秒级，高频场景（每帧合成）需要批处理。**通用知识**：Linux 上的 DRM/ALSA/Input 知识（第 9、10 章）在 Android 下依然适用，只是封装层不同——理解 Linux 底层是做 Android HAL 的前提。

实践：
- 用 `dumpsys SurfaceFlinger` 和 `dumpsys audio` 看当前显示与音频状态；`getevent` 看输入事件。
- 分析一次完整合成：从应用提交 Surface 到 SurfaceFlinger 合成到 HWC 决策到 DRM 提交；用 ftrace 或 systrace 抓每一步。
- 测试多屏场景（如适用）：扩展桌面或镜像模式，观察 SurfaceFlinger 如何处理两个 Display；触摸屏绑定是否正确。
- 测试旋转：旋转屏幕，观察合成、触摸坐标、应用窗口的响应；测量旋转响应延迟。
- 故意制造一次 HWC 失败（如 plane 不够），观察 SurfaceFlinger 是否能 fallback 到 GPU 合成；记录性能差异。

### 第 18D 章：Camera HAL 与 MediaCodec

这一章讲 Android 怎么用摄像头和硬件编解码——Camera2 API 到 ISP、MediaCodec 到 MPP。底层还是第 10、11 章那套，Android 加了 HAL 层。

**Camera HAL：从 Camera2 API 到 ISP。** Camera2 API 是应用层 API，提供精细控制（手动曝光、RAW 捕获、多流），替代旧版 Camera API；CameraService 是 Framework 服务，管理多个相机设备、应用请求排队、和 HAL 通信；Camera HAL 是厂商实现，封装 ISP/sensor 控制，处理 capture request、产 capture result。**ISP 和 IQ**（第 10 章）：Camera HAL 调用 ISP 驱动（如 rkisp）+ 厂商 IQ tuning 文件，**IQ 调参是厂商专属，rk-forge 不深入**。多流：Camera2 支持同时输出多路（预览流 + 拍照流 + 分析流），HAL 要协调多流格式和分辨率。

**MediaCodec：硬件编解码 API。** MediaCodec 是 Android 应用层硬件编解码 API，应用请求 codec、配置、提交输入 buffer、取输出 buffer。**和 MPP 的关系**（第 11 章）：MediaCodec HAL 内部调用 MPP（或厂商等效库），应用不直接用 MPP，而是通过 MediaCodec。异步 API：MediaCodec 支持异步回调模式，吞吐高于同步模式，推荐用于产品级应用。**输入输出**：输入可以是 ByteBuffer（压缩域）或 Surface（图像域，零拷贝），输出同理，**零拷贝路径要走 Surface**。错误恢复：MediaCodec 状态机复杂，错误（如 codec 重置）要正确处理，否则应用卡死。

**MPP 和 Android 媒体框架的边界。** MPP 是 Rockchip 平台的硬件编解码库（第 11 章），Android 上不直接暴露给应用，作为 MediaCodec HAL 的实现。**边界**：应用用 MediaCodec（标准 API）→ CameraService/MediaServer 调用 MediaCodec HAL → HAL 调用 MPP → MPP 调用 VPU 驱动。调试：MediaCodec 行为看 logcat（MediaCodec 标签），MPP/VPU 内部看厂商日志或 dmesg，**不同 bug 在不同层**。兼容性：MediaCodec API 跨 Android 版本相对稳定，MPP/驱动版本和 HAL 实现绑定，可能因厂商 BSP 升级变化。

**权限和 SELinux，Android 隐私模型。** 相机权限：`android.permission.CAMERA`（危险权限，运行时请求），应用必须有权限才能用 Camera2 API；麦克风权限：`android.permission.RECORD_AUDIO`，用于录音或视频通话；存储权限：录像落盘需要存储权限，Android 10+ 用 MediaStore API。**SELinux**：Camera HAL 进程和 MediaCodec 进程有自己的 SELinux domain，写 HAL 时同步写 `.te` 文件。隐私：Android 要求应用使用相机/麦克风时显示指示器（since Android 12），产品级要遵守。

实践：
- 写一个最小 Camera2 应用：预览 + 拍照；用 `dumpsys media.camera` 看 camera 服务状态、logcat 看 HAL 调用。
- 写一个 MediaCodec 应用：硬件解码一段视频到 Surface 显示；用 `dumpsys media.codec` 看 codec 信息。
- 测试多流相机：同时输出预览（Surface）+ 分析流（ImageReader），观察 HAL 如何处理。
- 故意制造一次错误（如不支持的 codec、分辨率错误），观察 MediaCodec 错误回调；分析错误传播到应用的路径。
- 检查 SELinux：enforcing 模式下跑应用和 HAL，确保无 denial；如有，写出对应 `.te` 规则。

### 第 19D 章：形成可维护 Android 产品

这一章是 D 方向的收口——把一个能跑的 Android 系统做成可维护的产品：定制 Launcher、product/vendor 配置、A/B OTA、回滚、工厂恢复。

**Launcher 和系统应用定制。** Launcher 是 Android 桌面应用，产品级经常替换为定制 Launcher（车载界面、kiosk 界面、信息亭）；系统应用定制：Settings、SystemUI（状态栏、导航栏）、Setup Wizard，按产品需求修改或替换。**product 分区**：OEM 定制内容放这里（Launcher、预装 APK、主题），让 system 分区保持通用、便于升级。编译：AOSP build 系统（`lunch`/`m`），定制通过 overlay、product 配置、APK 预装实现。

**product 和 vendor 配置。** product 分区配置：`product.mk`、`product/*.mk`，定义预装应用、主题、默认设置；vendor 分区配置：`vendor/*.mk`，定义厂商 HAL、驱动、固件，SoC 厂商（Rockchip）和 OEM 各自维护。**overlay（资源覆盖）**：让 OEM 在不修改 system 的情况下定制字符串、图标、布局，现代 Android 推荐方式。配置分层：AOSP 默认 → vendor → product → OEM overlay，后层覆盖前层。

**A/B OTA 升级，现代 Android 标配。** A/B OTA：升级时写"另一槽"（如当前在 a，写 b），重启切换到 b，失败自动回滚到 a。**优势**：升级过程中系统正常使用、无 downtime、无 bricking 风险。实现：UpdateEngine（系统服务）+ A/B 系统镜像 + bootctrl HAL（控制启动槽）。升级包：full OTA（完整镜像，大）、incremental OTA（差分，小但需要源版本），产品推送策略要选。**升级流程**：下载包 → 校验签名 → UpdateEngine 写另一槽 → 重启 → bootctl 切换 → 新槽启动 → 标记 successful → 升级完成。

**recovery 和回滚。** recovery：独立最小环境，负责 OTA 升级执行、恢复出厂、备份恢复，A/B 时代 recovery 可能并入 boot/vendor_boot；恢复出厂：清空 userdata、重置 system 设置，保留或清除某些 OEM 数据（按策略）。**回滚**：A/B 模式下，新槽启动失败 N 次（典型 7 次）自动回滚到旧槽，保证升级不会 bricking。非 A/B 设备：旧版 Android 用 recovery 模式做升级，失败可能 bricking，现代 Android 不推荐。

**版本升级和数据兼容，升级路径要测。** 系统升级（如 Android 13 → 14）：AOSP 大版本升级，可能涉及数据库 schema 变更、API 废弃、SELinux 策略变更，测试范围大；应用数据兼容：升级后用户数据保留，数据库 schema 迁移、SharedPreference 兼容，OEM 应用要测升级路径；Vendor 升级：vendor 分区升级涉及 HAL 版本变化，Framework 和 vendor 的接口（HIDL/AIDL）要兼容。**回归测试**：升级路径（旧版本 → 新版本）+ 全新安装（新版本）必须都测，很多 bug 只在升级路径出现。

**工厂恢复和诊断，售后和产线的需要。** 工厂恢复：恢复到出厂状态，清 userdata、重置 system 设置、保留或清除 OEM 数据；诊断模式：OEM 经常内置诊断工具（屏幕测试、按键测试、传感器测试），用于产线测试或售后；ADB 和 fastboot：产线与售后用 adb/fastboot 烧录、调试、恢复，产品级要保留这些通道（可能有签名保护）；日志收集：`adb bugreport` 收集完整系统状态，用于售后问题分析，隐私敏感信息要脱敏。

方向产出：
- 一个真实硬件能力的 kernel—HAL—Framework—App 完整闭环（建议从 D3 选一个简单能力延伸到产品级）；
- 系统定制方案（Launcher、SystemUI、product/vendor 配置）；
- 升级与回滚方案（A/B OTA、升级路径测试）；
- 真板稳定性证据（24 小时长跑、温度、内存、关键指标）；
- 恢复与诊断方案（恢复出厂、诊断模式、日志收集）。

## 9. GPU 高级选修

GPU 不作为所有学习者的必修，也不在软件栈版本未确认时承诺具体开源驱动状态。

### 第 G1 章：Mali-G610 软件栈边界

GPU 方向是选修，不作为结课必需。这一章先建"GPU 软件栈四层"的通用模型，再讲 Mali-G610 的特殊之处——它的开源驱动栈（Panthor/PanVK）成熟度随时间变化，**具体状态以课程实施时的主线内核和 Mesa 文档为准，不预设**。

**GPU 软件栈四层，先记牢。** 应用层是 OpenGL ES / Vulkan / OpenCL 应用，调用用户态图形 API；用户态驱动（Mesa 或厂商闭源）把 API 调用翻译成 GPU 命令流（command buffer），这是 GPU 厂商或开源社区实现的核心；内核 DRM 驱动管理 GPU 硬件、内存、调度、上下文切换，通过 DRM ioctl 暴露给用户态；GPU 固件（firmware）是 GPU 自己跑的微码，执行调度、电源管理、命令解析，由厂商签名发布、不开源。

**内核 DRM 驱动，主线和厂商两条路线。** 内核驱动是 GPU 和操作系统的桥：分配 GPU 内存（GEM buffer）、管理 GPU 上下文（context/fence）、调度命令（command stream submission）。**Mali 驱动历史上分两条路线**：Arm 官方的 mali-bifrost/mali-midgard 系列（kbase，厂商 BSP 常用）与开源社区的 Panfrost/Panthor（主线，逆向 + Arm 配合）。主线状态：Valhall（Mali-G610 架构）的开源驱动栈是否已完全支持、性能是否产品级，**以课程实施时的主线内核和 Mesa 文档为准**，不预设"完全可用"或"完全不可用"。

**GPU 固件，和 NPU/VPU 固件一样是 blob。** 固件是 GPU 微码，负责命令调度、电源管理、内存管理（虚拟化、上下文隔离）、安全检查；来源 Arm 发布、签名验证，通常不开源、与具体 GPU 型号绑定。和内核驱动关系：内核驱动加载固件到 GPU、与之通信，**固件版本必须和内核驱动匹配**。主线策略：固件通常作为单独 blob 加载（类似 NPU/VPU 固件），见 [blobs.md](../blobs.md)；rk-forge 倾向最小化 blob。

**Mesa：开源用户态图形栈。** Mesa 是开源的 OpenGL/Vulkan/OpenCL 实现，包含多个驱动（radeonsi/AMD、iris/Intel、Panfrost/PanVK/Arm Mali 等）；和厂商闭源栈对比，厂商闭源（如 Arm Mali 用户态 blob）性能可能更好但版本绑定、不开源，Mesa 开源、和主线同步、可调试。**Mesa 主线对 Mali-G610 的支持状态以课程实施时的 Mesa release notes 为准，不预设**。

**OpenGL ES 和 Vulkan，现代和传统的选择。** OpenGL ES 是移动版 OpenGL，状态机模型，简单易用、跨平台，老牌 API；Vulkan 是现代低开销 API，显式同步、显式资源管理、命令缓冲，性能更高但代码复杂。**性能差异**：Vulkan 减少 CPU 开销（驱动验证少）、支持多线程提交，高频渲染（游戏、实时合成）Vulkan 优势明显。选择：新项目优先 Vulkan，老项目或跨平台兼容选 OpenGL ES，Mesa 同时支持两者。

**Panthor / Panfrost / PanVK 的适用关系，这是 Mali-G610 的关键判断。** Panfrost 是开源 Mali 驱动，覆盖 Midgard/Bifrost 架构（Mali-T880、Mali-G31、Mali-G72 等），**不支持 Valhall（Mali-G610）**；Panthor 是开源 Mali 驱动，针对 Valhall 架构（包括 Mali-G610），较新，成熟度逐步提升；PanVK 是 Mesa 的 Vulkan 驱动，基于 Panfrost/Panthor，让 Valhall GPU 能跑 Vulkan；mali-bifrost-kbase / mali-valhall-jm 是 Arm 官方驱动，性能成熟但闭源用户态。**决策原则**：Mali-G610 上选 Panthor + PanVK 是 mainline-first 路线，但成熟度和性能以课程实施时的 Mesa/主线状态为准，**产品级可能需要 fallback 到 Arm 官方栈**。详见 [sdk-diff.md](../sdk-diff.md) 的 GPU 章节对照。

实践：
- 查当前板上的 GPU 软件栈：内核驱动模块名、Mesa 版本、固件版本、用户态库（`glxinfo`、`vulkaninfo`）；形成"GPU 栈身份卡"。
- 对比主线 Panthor/PanVK 和厂商 mali-valhall-jm 栈（如 BSP 提供）：跑相同 OpenGL ES / Vulkan 测试，对比 FPS、CPU 占用、温度、兼容性。
- 跑一组公开 benchmark（如 Glmark2、vkmark），记录性能数据；建"GPU 性能基线"。
- 评估当前 GPU 栈是否满足产品需求：性能、稳定性、兼容性、可维护性；不满足时考虑 fallback 策略。

### 第 G2 章：渲染、同步与显示

这一章讲 GPU 渲染怎么输出到屏幕——EGL/Vulkan 的 swapchain、buffer 和 fence 的显式同步、GPU 渲染到 DRM 的零拷贝衔接。

**EGL：OpenGL ES 和窗口系统的桥。** EGL 是 OpenGL ES 和原生窗口系统（Wayland/X11/Android SurfaceFlinger/DRM KMS）之间的胶水层，管理 surface、context、display。关键对象：`EGLDisplay`（连接窗口系统）、`EGLSurface`（drawable，对应一个 dma-buf）、`EGLContext`（OpenGL ES 状态机）。**和 dma-buf 的桥**：EGL 可以导入外部 dma-buf 作 `EGLImage`，让 OpenGL ES 直接渲染到 V4L2/RGA/NPU 的 buffer，这是零拷贝渲染的关键（第 5 章）。swap：`eglSwapBuffers` 把当前渲染完的 surface 提交给窗口系统显示，背后是 page flip + fence 同步。

**swapchain：Vulkan 的多 buffer 模型。** swapchain 是 Vulkan 的窗口表面抽象，一组（典型 2-3 个）可显示 buffer 轮转，渲染到一个、显示另一个。**和 EGL 的差异**：Vulkan swapchain 显式管理 buffer（应用知道有几个、哪个在用），EGL 隐藏细节。acquisition：渲染前 acquire 一个 free buffer → 渲染 → queue submit → present，每步都有同步原语。模式：FIFO（vsync 同步，无撕裂）、MAILBOX（低延迟，可能丢帧）、IMMEDIATE（无同步，可能撕裂），产品选 FIFO 或 MAILBOX。

**buffer 和 fence：显式同步，Vulkan 的核心。** Vulkan 的核心是所有同步显式，buffer 有 ownership 概念，谁拥有谁负责同步。**semaphore 是 GPU 内部同步**（命令 A 完成才执行命令 B）；**fence 是 GPU → CPU 同步**（CPU 等 GPU 命令完成）。和 dma-buf fence（第 5 章）的关系：Vulkan 的 semaphore/fence 是用户态抽象，底层映射到 drm_syncobj / dma_fence，这是 explicit fence 模型的具体实现。性能：正确使用显式同步能避免 CPU 等 GPU 的浪费，用错（如多余 wait）会引入延迟。

**GPU 渲染到显示，零拷贝衔接 DRM。** 渲染输出 dma-buf：Vulkan/EGL 把渲染结果写到 dma-buf（DRM GEM buffer），这个 buffer 可以直接给 DRM 显示。**和 DRM plane 的衔接**：把渲染好的 dma-buf 设为 DRM plane 的 framebuffer，atomic 提交，GPU 渲染 → DRM 显示零拷贝。modifier：GPU 渲染可能用 tiled layout（性能优），DRM 必须支持同 modifier 才能直采，否则要 RGA 转 linear（第 12 章）。多 buffer 流水：渲染 buffer N → 显示 buffer N-1 → 同时准备 buffer N+1，这是 60 FPS 流畅的基础。

**CPU/GPU 同步，异步执行的代价。** 异步执行：CPU 提交命令后立刻继续，GPU 异步执行，CPU 不能假设"提交完就是渲染完"。**同步策略**：(1) CPU 提交后等 fence（同步，简单但浪费 CPU）、(2) CPU 继续做其它事、下一帧再检查 fence（异步，性能优）。资源生命周期：buffer 正在被 GPU 用时 CPU 不能修改，要等 fence signal 才能复用 buffer。**常见 bug**：CPU 在 GPU 还在渲染时就改 buffer → 数据竞争 → 画面撕裂或崩溃，**用 fence 同步是必须的**。

实践：
- 写一个最小 OpenGL ES 程序（用 EGL + dma-buf），渲染到 dma-buf 然后给 DRM 显示；用 ftrace 验证 GPU 渲染和 DRM 提交的同步关系。
- 写一个最小 Vulkan 程序（用 swapchain 或 dma-buf import），对比和 OpenGL ES 版本的 CPU 占用、FPS、延迟。
- 测量 CPU/GPU 同步开销：故意在错误时机读 buffer（不等 fence），观察数据竞争现象；加入正确同步后对比。
- 用 dma-buf import 让 GPU 直接渲染 V4L2 摄像头帧（在帧上画检测结果或处理）；验证零拷贝渲染链路。

### 第 G3 章：GPU compute 与 profiling

GPU 不只是画图，也是通用并行计算引擎。这一章讲 GPU compute 适合什么任务、和 CPU/NPU 怎么分工、以及怎么 profile 找瓶颈。

**GPU compute：通用并行计算。** GPU 不仅是图形处理器，还是通用并行计算引擎，OpenCL / Vulkan Compute / OpenGL Compute Shader 都能跑通用计算。**适合 GPU 的任务**：数据并行（同一段代码处理大量数据）、计算密集（每个工作项算术多）、内存访问规律（coalesced access）。**不适合 GPU 的任务**：控制流密集（branch divergence）、小数据量（启动开销大于计算）、强串行依赖（GPU 并行优势发挥不出来）。**和 CPU 对照**：CPU 单线程快（高时钟、深流水、强分支预测）、GPU 并行吞吐高（数千核心），任务性质决定哪个更快。

**GPU compute 和 CPU 推理对照，以及和 NPU 的分工。** 神经网络推理本质是大规模矩阵乘 + element-wise 操作，理论上是 GPU 的强项。**和 NPU 对比**：NPU 是专门为神经网络设计的（INT8 加速器），单位功耗性能优于 GPU；GPU 更灵活（任意算法、任意精度）。**和 CPU 对比**：GPU 比 CPU 快得多（数千倍并行），但启动开销（kernel launch、数据传输）大，小模型 CPU 可能更快。**用例**：在没有 NPU 的场景用 GPU 推理；或把 NPU 不支持的算子（如复杂后处理）放 GPU；或同时用 NPU + GPU（NPU 跑主网络、GPU 跑后处理）。

**GPU profiling 工具，瓶颈要量出来不是猜出来。** Mesa 内置 profiler：`MESA_LOG_LEVEL`、`GALLIUM_HUD`（实时 overlay 显示 GPU 指标），开源栈主力；厂商工具：Arm Mobile Studio（Mali GPU 专属，闭源但免费），性能分析功能丰富；perf / ftrace：内核级，看 GPU IRQ、command submit、fence signal，和 CPU 联合分析。**指标**：GPU 占用率、内存带宽、shader 热点、cache 命中率——**任何"为什么 GPU 慢"都要靠 profiling 而非猜测**。

**吞吐、延迟、同步、内存的瓶颈分析，四类不同。** 吞吐瓶颈：GPU 算力不够（每秒处理像素/顶点不够），优化方向是简化 shader、降分辨率、降精度；延迟瓶颈：每帧命令提交到完成时间长，优化方向是减少命令数量、避免 stall、减少同步等待；同步瓶颈：CPU 等 GPU（fence wait）、GPU 等 CPU（命令没提交），优化方向是双 buffer 命令、异步提交；内存瓶颈：GPU 访存带宽不够（texture 采样过多、shader 访存不规律），优化方向是压缩 texture、改 shader 访存模式、用 shared memory。**综合分析**：瓶颈可能是上述任一，profiling 才能定位，**盲优化往往无效甚至反向**。

**CPU/GPU/内存综合优化，各尽其职。** 任务分配：CPU 跑控制流 + 串行任务、GPU 跑并行渲染 + 计算、NPU 跑神经网络、VPU 跑视频 codec、RGA 跑图像几何，各尽其职；数据流：减少跨 IP 的拷贝（第 5 章 dma-buf），GPU 渲染的输出直送 DRM 显示，不回 CPU；同步开销：减少 fence wait、批处理命令，高频小调用累加起来开销巨大。**整体目标**：找到整个系统的瓶颈（可能是 GPU、可能是带宽、可能是 CPU 提交开销），针对性优化，**不能孤立看 GPU**。

实践：
- 实现一个可与 CPU 对照的渲染或计算任务（建议：矩阵乘或简单图像处理如高斯模糊），用 OpenGL ES Compute Shader 或 Vulkan Compute。
- 测量多维度指标：吞吐（GFLOPS 或像素/秒）、单次延迟、CPU 占用、GPU 占用率、内存带宽、温度稳态；和 CPU 版本对比。
- 用 Mesa profiler 或 Arm Mobile Studio 分析瓶颈：是 GPU 算力？是访存？是同步？给出针对性优化方案并实施。
- 把 GPU compute 和 NPU 推理结合（如 NPU 跑主网络、GPU 跑后处理）；用 dma-buf 在两者间共享数据，验证零拷贝。
- 写一份"CPU vs GPU vs NPU 任务选择决策表"，按任务类型（控制流/并行计算/神经网络/图像处理）给出推荐执行单元和原因。

## 10. 候选毕业项目

学习者只选择一个主项目；不能同时要求完成 AI、媒体和 Android 全部方向。

## 项目 A：RKNN 边缘 AI 盒

**建议进入主路线：是，AI 方向首选。**

- 目标：接收摄像头或网络视频，执行实时推理并提供本地/远程结果。
- 最小版本：一个模型、一个真实输入、RGA 预处理、NPU 推理、结果显示或 API。
- 依赖课程：H0–H3、N1–N5。
- 硬件：开发板、散热、已确认摄像头或网络输入。
- 关键风险：模型算子不支持、版本配对、预处理复制、温控降频。
- 真板验收：精度、端到端延迟、持续帧率、CPU/内存、温度、24 小时稳定性、输入恢复。

## 项目 B：MPP/RGA/DRM 媒体设备

**建议进入主路线：是，媒体方向首选。**

- 目标：形成低 CPU 占用的硬件解码、处理、显示或编码设备。
- 最小版本：单路输入、MPP、RGA、DRM 或编码输出、性能监控。
- 依赖课程：H0–H3、M1–M5。
- 硬件：显示器或摄像头/网络输入，按项目方向确认。
- 关键风险：格式/stride 不兼容、隐式复制、内存带宽、同步和掉帧。
- 真板验收：稳定播放/编码、延迟、CPU 占用、复制次数、断流恢复、温控和长期运行。

## 项目 C：智能屏或 Android 定制终端

**建议进入主路线：有条件。**

- 目标：形成带显示、触摸和至少一种真实硬件能力的产品原型。
- 最小版本：自定义启动界面/Launcher、显示触摸、一个 HAL/AIDL 硬件闭环、恢复入口。
- 可选增强：摄像头、音频、AI 或媒体能力只选择一项。
- 依赖课程：H0–H3、D1–D6。
- 硬件：显示屏、触摸、音频/摄像头等必须在立项前确认。
- 关键风险：Android SDK 体量、硬件配套、SELinux、OTA 和应用工作量掩盖系统课程。
- 真板验收：稳定启动、硬件闭环、SELinux 正确、升级/回滚、异常恢复、长期运行。

CFDesktop 可以作为智能屏或 AI 盒的产品界面，但不替代底层媒体、AI、Android 或可靠性验收。

## 11. 结课标准

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

## 12. 硬件和方向确认门

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

## 13. 明确不讲或推迟

- 不把 RK3588 写成稳定/完整支持——当前是 `partial`（真机 boot 到 GNOME 桌面 + GPU/LCD/触摸板验），但 VOP2 hard-lock 修复仍是候选镜像、WiFi/BT、NPU/VPU、摄像头未接，连续冷/热启动稳定性验证未完；
- 开发板和主要配套硬件已确认（iTOP-RK3588 + LCD/触摸），DTS/镜像布局见 [board/rk3588-topeet/](../../board/rk3588-topeet/)，但摄像头、Android 等未确认方向不写结论；
- 不把运行厂商 demo 计为课程完成；
- 不要求同时推进 Linux、Android、GPU、NPU、媒体和摄像头；
- 不默认把所有 RK3588 硬件能力纳入课程；
- 不重复 RK3568 的完整字符设备和通用驱动基础；
- 不承诺未核实的 codec、GPU、NPU 或摄像头能力；
- 不把峰值跑分当作产品性能；
- 不执行缺少恢复和密钥治理的不可逆 secure boot 操作；
- 不把 CFDesktop 界面完成等同于底层产品闭环。

