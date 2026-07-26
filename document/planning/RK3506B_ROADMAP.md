---
title: "RK3506B 教学路线：从主线 BSP 到可靠工业设备"
---

# RK3506B 教学路线：从主线 BSP 到可靠工业设备

> 状态：**partial（课程规划）**。仓库已经拥有 AES-RK3506B 的主线 U-Boot、Linux、SPI-NAND/UBIFS、SD、Buildroot、OpenWrt、外设和真板日志基线；本文件规划如何把这些工程成果组织成课程。单章是否完成仍须以对应配置、构建产物和真板证据为准。

## 1. 路线承诺

RK3506B 路线不以“烧录一个 rootfs”作为终点，而是训练学习者把一块资料不完整、带有厂商启动约束的开发板，做成一个：

- 能解释启动链；
- 能从源码重复构建；
- 能定位 bootloader、内核、设备树、rootfs 和存储故障；
- 能可靠烧录、冷重启和恢复；
- 能接入网络与工业接口；
- 能长期维护补丁和证据；
- 最终可以承载工业网关、OpenWrt 路由或数据采集业务的嵌入式系统。

完成本路线后，学习者的角色应从“Linux 系统使用者”提升为“能够独立维护 ARM32 板级支持的 BSP 工程师”。

## 2. 平台角色与边界

| 项目 | 本路线定义 |
|---|---|
| 目标 SoC | Rockchip RK3506B，ARMv7-A / 32 位 |
| 当前课程载体 | AES-RK3506B |
| 系统重点 | 主线优先 bring-up、SPI-NAND/UBIFS、SD、Buildroot、OpenWrt、工业接口 |
| 架构重点 | armhf ABI、ARMv7-A 异常模型、Cortex-A7 SMP |
| 工程重点 | 版本 pin、补丁序列、BSP/Mainline 差距、可复现构建、真板取证 |
| 闭源边界 | DDR、SPL/TPL、TEE 等 rkbin 产物；必须明确记录来源和配对约束 |
| 不承担 | AArch64 EL0–EL3、PCIe 高速驱动、复杂媒体/NPU/Android 主课程 |

课程只能把 AES-RK3506B 的真板结论用于该板卡。其他 RK3506/RK3506B 板卡即使 SoC 相同，也必须重新确认设备树、存储、接口和启动配置。

## 3. 适合谁学习

### 直接进入者

应具备：

- Linux 命令行和 Git 基础；
- C 语言、指针、结构体和基本 Makefile 能力；
- 能阅读简单原理图和芯片 datasheet；
- 理解进程、文件系统、设备文件和网络接口的基本概念。

不要求提前会：

- U-Boot；
- Linux 内核移植；
- NAND、UBI、UBIFS；
- Rockchip 打包格式；
- OpenWrt 平台移植。

### 已学过其他 Linux BSP 的学习者

可以跳过通用的 Linux、C 和交叉编译入门，从以下内容开始：

1. Rockchip 启动链与 rkbin；
2. RK3506B 的 ARM32 与板级设备树；
3. SPI-NAND/UBI/UBIFS 可靠性；
4. Buildroot/OpenWrt 双系统路线；
5. 工业接口与毕业项目。

## 4. 能力成长地图

| 阶段 | 学习者要解决的问题 | 阶段成果 |
|---|---|---|
| R0 读懂基线 | 板子实际经过哪些启动阶段 | 启动链图和证据索引 |
| R1 掌控启动 | 如何替换并验证 U-Boot、内核、DTB | 可复现的主线启动链 |
| R2 掌控存储 | 为什么 NAND 能读却未必可靠写 | 可恢复、可压力验证的 UBIFS 系统 |
| R3 掌控系统 | 如何形成自己的产品 rootfs | Buildroot 产品系统或 OpenWrt 网络系统 |
| R4 掌控硬件 | 如何接通网络和工业接口 | 可持续运行的接口服务 |
| R5 掌控交付 | 如何让第二个人复现并验收 | 版本、补丁、日志和测试闭环 |

## 5. 课程编排

## R0：读取真板，而不是背诵命令

### 第 1 章：AES-RK3506B 系统全景

先认识这块板。AES-RK3506B 上是一颗 RK3506B——32 位 ARMv7-A，三个 Cortex-A7 跑 SMP Linux，旁边还坐着个 Cortex-M0 协处理器。"A7 上 Linux、M0 上裸机/RTOS"这种多核异构 AMP，是它区别于纯应用处理器的地方，也是第 2 章会展开的特色。板上你能摸到的家当：512MB DDR3、一颗 Winbond SPI-NAND（W25N04KV，512MB）、两个 RJ45 网口、一个屏接口、WiFi 靠插在 USB 上的 RTL8733BU dongle。开发机不用豪华——笔者在 WSL2（Ubuntu）里给了几个 G 内存就把整条链干完了，16GB 那种规格是隔壁 RK3588 群的事。

**它有两条启动路线：SPI-NAND 和 SD。** BootROM 选哪条由板级 strap/电阻决定，两条链结构完全一样，差别只在镜像落在哪种介质、U-Boot 用哪种偏移去读。NAND 这条是 R3 的可靠性主课（SPI-NAND → UBI → UBIFS，坑最深、价值最大）；SD 这条更像普通块设备，适合快速试验和置备镜像（见 [tutorial/sd-boot/](../tutorial/sd-boot/)）。先把"两条路都通"当成 R0 的目标，R3 再钻进 NAND 的可靠性细节。

启动链长这样，先把它背下来（后面每一章都在逐段拆它）：

```
BootROM(片上固化) → rkbin(TPL/SPL/DDR init, 闭源) → 可选 OP-TEE → U-Boot(主线) → Linux(主线) → rootfs → init
```

**这条链最关键的一笔，是闭源与开源的分界——画在 rkbin 之后。** rkbin 之前借厂商 blob（DDR/SPL/TEE，详见 [blobs.md](../blobs.md)）；rkbin 之后，从 U-Boot 到 init，每一行都能在主线仓库翻到、能 `git bisect`、能打补丁。这条分界线就是 mainline-first 的咽喉，守不住它整个项目就垮成又一个 BSP 镜像。

一条主线启动涉及几类资产，你要能把它们串起来：主线源码（U-Boot/Linux）、rkbin blob（来自 Rockchip）、板级设备树补丁、打包工具（`forge`、`fit-pack.py`）、最终的镜像（idblock、uboot.img、boot.img、rootfs）。这些镜像又落到分区表固定偏移里——idblock 在 SPI-NAND/SD 起始，之后 loader、U-Boot proper、boot、rootfs 各有位置。把它们串成一张"源码 → 产物 → 分区 → 启动日志里的版本号"的对照表，是 R0 的核心产出，也是后面所有章节的参照原点。

最后说清状态口径，RK3506B 整份路线都绕着它：🟢 `verified` 是仓库已有真板证据（日志 + 产物 + 配置齐备）、别人能复现；🟡 `partial` 是工程基线已板上验证但课程化没做完——**RK3506B 现在就在这档**；⚪ `planned` 是目标定了但没真板；🔴 `blocked` 是明确卡死。诚实现状：主线 U-Boot 2026.07 和 Linux 7.1 已经板上跑通（证据在 [logs/](../logs/)），但"纯主线 boot"还做不到——卡在 rkbin 的 DDR init，这个坑第 3 章会专门讲。

实践：
- 拿一份 [logs/](../logs/) 里的完整串口日志，逐行标出 BootROM、DDR、SPL、U-Boot、Linux、rootfs 各阶段。
- 把日志里的版本号（`U-Boot 2026.07-rc4`、`Linux 7.1.0`）映射回 [config/](../../config/) 下声明的源码 pin。
- 把镜像文件映射到真实分区偏移和加载地址，建立你自己的"源码—产物—分区—日志"对照表。

保存证据：带行号标注的启动日志、启动链图、基线版本与产物摘要。

### 第 2 章：ARMv7-A、armhf 与三核 Cortex-A7

RK3506B 是 32 位的，这一章先把"32 位"这件事的几个硬约束和工具链坑讲清楚——尤其是从 64 位平台过来的人容易栽的地方。

**ARM/Thumb/Thumb-2。** ARMv7-A 同时认 32 位 ARM 指令和 16 位 Thumb 指令；Thumb-2（ARMv6T2 起的 16/32 位混合编码）是 Cortex-A7 默认编出来的东西，你反汇编内核和用户态看到的几乎都是它。同一份 C 源码加 `-marm` 或 `-mthumb` 能选编码，反汇编对比能看清调用约定、序言/尾声、`bx lr` 怎么交接。这不是闲笔：读 oops 栈回溯、对照厂商 BSP 的私有汇编时，看不懂指令编码就两眼一抹黑。

**armhf 的 `hf` 后缀，装错就完。** `arm-linux-gnueabihf` 的 `hf` 是 hard-float——浮点参数直接走 VFPv4/D16 寄存器（`s0–s15`/`d0–d7`），而不是软浮点 ABI 塞进整数寄存器或栈。**手滑装成 `gcc-arm-linux-gnueabi`（soft-float）是经典坑**：链接期甩你一脸 `undefined reference to __aeabi_*` 的浮点桩错误，报错位置离真正的因八丈远。RK3506 是 Cortex-A7 带硬浮点，所以工具链后缀必须是 `hf`，由 [config/toolchain.conf](../../config/toolchain.conf) 声明、`forge` 自动选用。AAPCS 的调用约定（`r0–r3` 传参、`r4–r11` 被调用者保存、栈对齐）用户态、内核态、signal frame 各一套，别混。

**七种处理器模式。** ARMv7-A 的 USR/SYS/FIQ/IRQ/SVC/ABT/UND，加 Security Extension 引入的 Monitor 模式。Linux 用户态跑 USR、内核跑 SVC、中断进 IRQ、未定义指令进 UND。异常向量表、`svc` 系统调用入口、中断控制器的入口寄存器保存——这套机制是后面读 oops、理解调度时机和中断延迟的基础，这里先有个骨架。

**PSCI、OP-TEE 与次级核。** 32 位 Rockchip 平台的 CPU 上线走 PSCI（`CPU_ON`）或平台私有方法：主核在 U-Boot/内核启动阶段释放次级核，次级核跳到指定入口跑内核二次初始化，三个 A7 核就是这么上来的。OP-TEE 作为 secure world 的常驻 firmware，在 normal world Linux 之前由 rkbin 起好，两者靠 SMC 切换隔离。

**32 位地址空间是硬天花板。** 用户态/内核态共享 4GB 虚拟地址：用户态通常 0–3G（看 `PAGE_OFFSET` 配置），内核占高端。RK3506B 的 512MB 物理内存靠 `ZONE_NORMAL` + lowmem 映射就够，但你要知道 64 位平台上不存在的 `highmem` 这类约束——这是 32 位平台的命，也是 RK3568/RK3588 切到 AArch64 的根本动机之一。多核异构 AMP 这里也提一句：A7 三核跑 Linux，M0 可以独立跑裸机/RTOS，两者靠共享内存和中断（IPC/邮箱）通信——这是 RK3506B 区别于单线程应用处理器的能力，第 1 章点过。

实践：
- 用 `arm-linux-gnueabihf-gcc` 编一份 ELF32，`readelf -h` 看 machine = ARM、flags 标 EABI/hard-float。
- 同一份 C 函数加 `-marm` 和 `-mthumb` 各编一次，反汇编对比序言、`bx lr`、Thumb-2 的 16/32 位混合编码。
- 真板上 `cat /proc/cpuinfo`、`nproc` 看三核上线和 BogoMIPS；`taskset` 改亲和性观察调度。

## R1：掌控 Rockchip 启动链

### 第 3 章：rkbin、DDR 与闭源边界

这一章是整条启动链的咽喉，也是 rk-forge 诚实地把"做不到"写出来的地方。读完你得能回答一个问题：**为什么 DDR 初始化偏偏绕不开那颗闭源 blob？**

**DDR init 跑在整条链最前段，那时连 RAM 都没有。** DRAM 还没点亮、C 运行时不存在、栈和数据段无处安放——只能用一段纯汇编裸 poke DDR PHY 寄存器，配一套私有 training 算法。主线 U-Boot 的 SoC 级 sdram 框架给了架子，但 RK3506 那套 training 参数和 PHY 调优 Rockchip 没开源，藏在 rkbin 的 TPL/SPL blob 里。BootROM 跳进来、开源代码还没跑起来之前，DRAM 必须先被点活，否则后面一切是空中楼阁。

**这正是 rk-forge 自研 DDR init（内部叫"方案 A"）目前卡住的地方。** 用主线 U-Boot 的 sdram 框架编出来的 loader，DDR 确实被点起来了——串口能打出 `DDR d27ac532c4 ... fwver: v1.06`，证明 BootROM 加载了我们的 idblock。但紧接着该由我们自己的 SPL 出 banner 的位置，输出变成全波特率的乱码，SPL 在 DDR 之后那一瞬就崩了。RK3506 的 DDR init 之所以难自研，因为它跑在"还没有 RAM、还没有 C 运行时"的极早期，全靠对 PHY 寄存器的裸 poke 加私有 training，**偏偏这块板没引出 JTAG**——崩在 SPL 里咱们连一行打印都抓不到，只能一遍遍改、烧、盯着满屏乱码猜。所以现状很诚实：借 vendor 的 DDR/SPL/OP-TEE blob 把链跑通，自研 SPL 那段还在趟。

**rkbin 里通常打包三段，它们是配对的，不能拆开换。** TPL（DDR init/DRAM training）、SPL（加载并校验下一段、跳 U-Boot proper）、可选 OP-TEE（secure world）。每段对下一段有版本/格式约束：SPL 期望的 FIT 节点结构、hash 算法、镜像偏移，必须和它要加载的 U-Boot 镜像对得上。一个我们真实撞过的坑：vendor fork 的 U-Boot 是从 2017 版 fork 出来的，它读 FIT 的代码和主线完全是两回事——把主线 binman 生成的 FIT 喂给 vendor SPL，它甩一句 `Unsupported hash algorithm`，看着像 hash 算法的事，真因是 vendor fork 的 FIT 节点结构和主线对不上（参见 [tutorial/boot/00_roadmap.md](../tutorial/boot/00_roadmap.md) 关于 vendor fit_nodes 的复盘）。

**所以别混用不同来源的 blob。** DDR、SPL、TEE 是配对的：TPL 给出的 DDR 配置（容量、频率、PHY 参数）必须和 SPL 期望的 RAM 布局一致；TEE 的 reserved-memory 范围必须和内核 DT 留出的 hole 对齐。混用（vendor SDK 一份、社区一份、主线一份）会破坏这条隐性契约——表现是 SPL 起不来、TEE 抢内存、内核 `reserved-memory` 不匹配导致 OP-TEE 区被踩。

最后把两个概念分清，别混：**主线优先** ≠ **纯主线 boot**。主线优先是 U-Boot、Linux、设备树走主线源码（能 bisect、能上游、能追每一行），rkbin 借厂商 blob 但诚实记录、盯着消除路径——rk-forge 现在的状态。纯主线 boot 更进一步，要求连 DDR init 都是开源的——这是目标，目前没做到，卡在 rkbin 那段。别把"主线优先"标榜成"无 blob"，那是骗人。维护一份闭源清单（每个 blob 的来源、版本、配对、用途、卡点）和消除路径，详见 [blobs.md](../blobs.md) 与 [sdk-diff.md](../sdk-diff.md)。

实践：
- 用 `binman` 或 `dumpimage` 把 loader 拆开，列出每个段的来源和版本；说明每个不可替代 blob 实际做了什么。
- 分析一组 SPL/TEE 不匹配的失败日志（参考 [tutorial/boot/](../tutorial/boot/) 与 [pitfalls/](../pitfalls/) 的复盘）。
- 对照厂商启动链和 rk-forge 主线启动链，把差异写进 [sdk-diff.md](../sdk-diff.md) 对应小节。

### 第 4 章：U-Boot、FIT 与启动策略

rkbin 把 DDR 点亮、环境搭好，接力棒就交到 U-Boot——从这开始后面全是主线开源代码。这一章讲 U-Boot 怎么把内核加载起来、FIT 怎么打包、以及为什么我们要用纯 Python 重写一个打包器。

**U-Boot 设备模型（DM）和内核的 device model 是一回事。** `uclass`/`driver`/`device`，由 DT 触发 probe。RK3506 的 SoC 级 DM 驱动（clk、pinctrl、sdram、serial、MMC/SFC）已经进主线，板级 `.dts` 把具体接线接进去就行。DM 在 SPL 阶段是精简版（`SPL_DM`），RAM 还紧时也能用统一接口起 serial/mmc；到 U-Boot proper 阶段是完整版，能挂环境、跑 bootflow。

**`bootcmd` 是自动执行的脚本，`bootargs` 是给内核的命令行。** `bootcmd` 决定怎么找镜像、怎么加载、怎么跳；`bootargs` 是内核启动参数（`console=`、`root=`、`rootwait`、`rw`）。环境变量可以存 NAND 固定偏移、MMC 专用分区、或 baked-in 到镜像里。**改环境变量后一定要验回退路径**——万一新值起不来，得有"按某个键进救援"的机制，否则一次写错环境变量板就变砖。

**NAND 和 SD 两条路，读取方式不同。** SPI-NAND 路线：U-Boot 在 NAND 上按固定偏移读 loader/uboot/boot/rootfs，因为没有 GPT 那种灵活分区表，偏移是和烧录工具、镜像布局硬约定好的。SD 路线（见 [tutorial/sd-boot/](../tutorial/sd-boot/)）可以走 GPT 分区，更灵活，适合置备/救援镜像和快速试验；BootROM 通过 strap 选介质，U-Boot 阶段还能在两种介质之间切。

**FIT（Flattened Image Tree）用节点描述多组件。** kernel + dtb + initrd + 多个配置，每段可以挂 hash（sha256 之类）做完整性校验，加载地址和入口地址在节点里声明。这里有个接着第 3 章的坑：vendor fork 的 FIT 节点结构和主线 binman 生成的可能对不上（就是那个 `Unsupported hash algorithm`）；FIT overlay（`fdt apply`）改 dtb 时也一样，节点偏移和大小必须和 SPL 期望的布局一致，否则 SPL 跳进来踩到错地方。**rk-forge 的解法是用纯 Python 的 [scripts/fit-pack.py](../../scripts/fit-pack.py) 字节级复刻 vendor 认的布局**——绕开 vendor 那套没开源的 2017 fork，而不是和它较劲。

最后，设计启动链时要预留三种用途，且互不破坏：**正常启动**从主分区加载产品和 rootfs（日常运行）；**置备启动**从 initramfs 起、把产品镜像写进 NAND（首启置备，见第 9 章）；**救援启动**从一个最小 rootfs 起、产品 rootfs 挂不上时用来诊断和恢复。三条规矩：置备不写救援分区、救援不覆盖正常分区、环境变量能回退到任一模式。一份"NAND 设备能不能交付"的硬指标，就是 rootfs 挂不上时你还能不能进得去。

实践：
- 手动用 `fatload`/`mmc read`/`ubi read` 读一段 FIT 并 `bootm` 起来，对照 `printenv` 看 bootcmd 每一步。
- 改一个可观察的内核参数（如 `console=`、`loglevel=`），验证它在内核启动日志里生效。
- `dumpimage -l` 检查 FIT 的组成和 hash；对比主线 binman 和 rk-forge `fit-pack.py` 输出的字节差异。
- 设计一个"正常启动失败 → 自动回退救援"的环境变量脚本，测它的幂等性。

阶段产出：启动失败决策树、可解释且可恢复的启动方案（正常/置备/救援三种入口）。

## R2：主线内核、设备树与补丁

### 第 5 章：从 SoC 支持到一块具体板

主线有了 SoC 的支持，不等于你的板子就能起来——中间还差一份"这块具体板子的设备树"。这一章讲怎么把 SoC 的通用能力和你板上的接线接起来，以及拿到一条 `probe failed` 时怎么分层定位。

**先分清 `.dtsi` 和 `.dts`。** SoC 级 `.dtsi` 描述芯片固有能力（控制器寄存器基址、clock 树、中断号、pinctrl 组），主线社区维护、SoC 通用；板级 `.dts` 描述"这块板具体用了哪些 SoC 能力、外接什么器件、什么电平/上拉"，由 rk-forge 写、目标是推回上游。对 RK3506 来说，**SoC 级支持（pinctrl、clock、sdram、GMAC、SFC 等）已经进主线了**——pinctrl 和 clock 从 Linux 6.19 起，U-Boot 的 SoC 支持也已合并进主线。所以对"启动主线"这件事，整个 RK-SDK 坍缩成就两样绕不开的东西：① `rkbin`（第 3 章讲过）；② **一块板级设备树**——上游没有，rk-forge 来写。这块板级 DT 就是本项目要贡献回上游的那块拼图（详见 [tutorial/boot/00_roadmap.md](../tutorial/boot/00_roadmap.md)）。

**外设节点的五件套：`compatible` / `reg` / `interrupts` / `clocks` / `resets`。** `compatible` 是驱动匹配的钥匙，通常写 `"vendor,soc-periph", "vendor,periph"` 两段；`reg` 是寄存器物理基址和长度；`interrupts` 是中断号和触发类型；`clocks`/`resets` 是它依赖的时钟和复位 phandle。这五个属性构成一个外设的资源依赖，**缺一不可**：缺 clock 会 probe defer、缺 reset 会在异常路径上漏复位、缺 interrupt 走不到中断处理。从厂商 DTS 抄属性值时，要核对每个值是 SoC 固有（照抄）还是板级接线（按你的板子改）。

**RK3506 有个别的 Rockchip 没有的东西：RMIO。** 普通的 pinctrl 把物理 pad 复用成某种功能（GMAC、I²C、SPI、GPIO……），由 pin bank/group/drive-strength/pull 组成；GPIO 是 pinctrl 之上的子节点，管输入输出和中断。RK3506 在这之上多了一层 RMIO——一个交叉开关（routing matrix），能把"控制器信号 → pad"的映射重新路由。**板级布线受限时，靠 RMIO 可以把某个功能挪到空闲 pad**，这是 RK3506 区别于普通 Rockchip 的特色。RMIO 的配置也走 pinctrl，但语义比单纯 pinmux 多一层路由，写设备树时一定按你的板子原理图核对，别拿参考板的配置照抄。

**从厂商 DTS 提取硬件事实，是 mainline-first 纪律的核心练习。** 厂商 BSP 的 DTS 是一份"已经能跑"的硬件描述，但里面混杂了四样东西：SoC 固有事实、板级接线、厂商私有 quirk、临时 workaround。提取时要分类：硬件事实（DRAM 容量、PHY 接法、外设地址）可以采纳；厂商做法（私有 binding、调试节点）应该丢掉。**绝不照抄厂商 DTS**——把它当"硬件事实的来源之一"，再用主线 binding 重写一份干净的板级 `.dts`。这一步做不好，要么把厂商 quirk 当宝贝带进主线，要么丢掉真实的硬件事实，两头错。

**拿到 `probe failed`，先分层，再动手。** 一条 probe 失败可能属于四层里任何一层：SoC 级（主线有没有这个 SoC 的支持、`CONFIG_ARCH_ROCKCHIP` 开了没）、板级接线（DT 节点没写对、pad 复用错、电平/上拉错）、内核配置（对应子系统的 `CONFIG_*` 没勾）、驱动（probe 路径、寄存器访问、IRQ 处理）。养成按这个顺序排查的习惯：**先看 SoC 支不支持 → 板级 DT 全不全 → config 勾没勾 → 最后才轮到怀疑驱动**。把问题归错层，会越改越乱——最常见的悲剧是板级 DT 漏了个 clock，却去改了半天驱动。

实践：
- 选一个真实外设（GMAC、SFC、I²C 任选），跟踪它从 DT 节点 → driver match → probe → 资源获取的完整路径。
- 安全范围内 `status = "disabled"` 一个外设、重启、再启用，看内核日志里 probe 的进出。
- 拿一条真实的 probe 失败日志，判断它属于哪一层（SoC/板级/config/驱动），说明依据。
- 为一个外设画出"DT 节点 → clock/reset/regulator → 寄存器 → IRQ"的资源依赖图。

### 第 6 章：有序补丁与主线差距

主线优先不是一句口号，它落地成一个具体的东西：**一份按顺序排好的补丁库**。这一章讲 rk-forge 的补丁库怎么组织、为什么"有序"比"打上"重要、以及怎么用一份差距报告判断主线这条路走得通走不通。

**补丁库是 quilt 风格的 `series`。** 补丁按依赖顺序排好，`git am` 落成真实 commit（不是一个 .patch 文件堆在角落里），可 bisect、可原子回滚。**顺序很重要**：先打 SoC 级补丁、再板级、再驱动、最后才是临时诊断补丁。打乱顺序，后面补丁的 context 对不上、应用失败；更阴险的是 bisect 时因为前置改动缺位得到错误结论，让你盯着一个无辜的 commit 改半天。

**这里有个老毛病必须修掉：只打最后一个补丁、坏了静默跳过。** 这是一些 BSP 脚本的常态——打补丁的脚本遇错就 `|| true`，最后只留下最后一个补丁生效，前面的全没打上，构建却"成功"了，bug 就这么藏进去。rk-forge 的 `apply-series.sh` 用 `git am --check` 先干跑校验、失败整个 series 原子回滚，**要么全打上、要么全不打**，不留这种静默跳过的余地。

**三类补丁要分清，命运各不相同。** 板级补丁（板级 `.dts`、defconfig 增量）目标是上游化；驱动补丁（主线驱动里 RK3506 还没支持的 SoC 级或外设级代码）也可以提上游；临时诊断补丁（debug print、PHY 实验、临时绕过）**不进主线**，必须明确标记（`WIP:`/`HACK:` 前缀或单独分支），问题解决后清掉。一个易被忽略的坑：临时诊断补丁如果不标记、混进 series，bisect 时会引入误导性信号——你以为找到 bug 了，其实是那个 debug print 改了时序。

**"在我机器上能跑"不算数。** 验证补丁库的纪律是从零开始：`git clone` 全新主线源码 → `git am` 整个 series → 干净构建 → 干净跑一次 → 干净烧到板上。每一步都要求不依赖本地未提交改动。`git am` 失败时整个 series 回滚到应用前状态（原子性）；patch 之间的依赖关系图画出来，方便排错。

**最后，维护一份 BSP/Mainline 差距报告。** 主线缺什么、BSP 有什么、差多少、还能不能 boot，逐子系统写清楚：bootloader、DDR init、SoC 驱动、网络、存储、外设。这份报告就是 [sdk-diff.md](../sdk-diff.md)，是判断"主线这条路走不走得通"的依据。报告口径只有两条：**不合成、不夸大**——RK3506B 当前主线 U-Boot 2026.07 + Linux 7.1 已板上跑通就标 `verified`，自研 DDR init 没成就标 `blocked` 并写清卡点。哪些改动值得上游化？通用价值高、绑了主线 binding、能被其他板复用的优先（板级 `.dts`、SoC 级驱动补丁、YAML binding）；板子特有 quirk、临时 workaround、私有用户态工具不进上游。rk-forge 的补丁库天然就是上游化的预热池。

实践：
- 在全新 `git clone` 的主线源码上，把 rk-forge series 完整 `git am` 一遍，确认无冲突、干净编译；故意挪乱一条补丁顺序，观察失败现象和原子回滚。
- 选一个外设，完成"厂商 BSP 实现 → 主线现状 → rk-forge 补丁"三段对比，写进 [sdk-diff.md](../sdk-diff.md) 对应小节。
- 整理 series 的依赖关系图，标出哪些是上游化候选、哪些是临时诊断。

## R3：SPI-NAND 与可靠存储

这是 RK3506B 路线的核心差异化课程。

### 第 7 章：SPI-NAND 不是普通块设备

抓一块板子上的 W25N04KV，先把一个直觉摁进去：它**不是 SD 卡那种"写进去就稳"的东西**。这一条决定了 R3 整章为什么这么长——也决定了为什么"烧录工具说成功"在这颗料上一钱不值。

**读、写、擦除的单位不一样。** 最小的读/写单位是 page——这颗料是 2048 字节数据 + 128 字节 OOB；但擦除不能按 page 来，只能按 erase block（64 或 128 个 page 一把擦掉）。OOB 那 128 字节不是给你写应用数据的，它存 ECC 校验码和文件系统元数据，硬件和 UBI 会自己管——**你别去碰它**，碰了 UBI 会以为自己的元数据坏了。

**出厂就允许有坏块。** 这是 NAND 和 SD/eMMC 最根本的差别。SD 卡里那颗 FTL 控制器把坏块、磨损均衡、垃圾回收全帮你藏好了，你看到的是一块干净的块设备；SPI-NAND 没这层，**你直接在前线**。W25N04KV 标称 512MB，但从出厂那一刻起里面就可能已经有几个坏块（factory bad），用着用着还会长新的（grow bad）。所以 NAND 上永远有两件事必须做：跳过坏块、磨损均衡。R3 后半段的 UBI/UBIFS 就是来干这两件事的。

ECC 这层 SPI-NAND 自己做了——on-die ECC，写时算校验码塞进 OOB、读时检测纠正，W25N04KV 这颗能纠 1–8 个 bit。但**你要会读 status 寄存器里的 `ECC status` 位**，它告诉你这次读"纠了几个 bit"还是"已经超能力、纠不动了"。在 Linux 里这映射成两个返回码，一定分清：

- `EUCLEAN`——"我帮你纠了，但这块料快不行了，盯着点"。在 AES-RK3506B 的长跑日志里你会反复看到它，**这是 NAND 正常的老化信号，不是 bug**；但你得画它的增长曲线，某天陡升了，就是该降级使用或换料的信号。
- `EBADMSG`——"数据已经丢了，救不回来"。读到这个，这一 page 的内容已经不可纠正，文件系统只能把它当坏块处理。

软件分层记住一条链就够了：**`spi-mem` → MTD → UBI/UBIFS**。SPI-NAND 是把 NAND die 挂到 SPI 总线上的封装；SoC 这头是 SFC（Serial Flash Controller），既发标准 SPI 命令、也认 SPI-NAND 专用的 page read/program/erase。Linux 把这套抽象成 MTD 设备（`mtd_info`），向上给 page 级 read/write/erase，向下走 `spi-mem`。这一层是 rk-forge 在主线上的真板基线——不是从厂商 BSP 里挖的，证据在 [tutorial/rootfs/](../tutorial/rootfs/) 和 [logs/](../logs/)。

**这一章最该反直觉的一句：读取稳定 ≠ 写入可靠。** 读 page 通常很稳，ECC 兜得住大部分错；但写才是可靠性主战场。写过程中断电（program 还没 settle）、program disturb（写这块、邻居受牵连）、read disturb（同一块被反复读、电荷老化）、retention（电荷随时间漏掉）——任何一条都能让"当初明明写成功"的数据过几个月读不出来。烧录工具报"成功"只代表它把 page program 命令发出去了、status 回了个 OK，**不代表数据真的在 NAND 上落稳了**：settle、ECC 回读校验、坏块标记它一个都没做。所以"可靠"这个结论只能由 Linux 自己下——写完 read back、跑 ECC、扫坏块。第 9、10 章的置备和长跑可靠性，就是来兑现这件事的。

最后一件你迟早会撞上的事：**SFC 时钟和 DLL 调谐**。SFC 跑几十甚至上百 MHz 没问题，但每个频率下能不能稳读，取决于内部 DLL 的采样窗口——采样点偏早或偏晚都是错码。厂商 SDK 通常带一份按板子走线和信号完整性调过的调谐表；一旦电气边界变了（走线长、电源毛刺、温度极端），窗口就会收缩。所以验收 SPI-NAND 可靠性时，**别只在室温跑一遍就交差**，要在温度、电压边界都过一轮——这是 NAND 设备验收和 SD 卡的另一个差别，单一工况下"读得对"不等于整批可靠。

实践：
- `mtd_debug read` / `nanddump` 读出 NAND 的 ID 和几何，和 `/proc/mtd`、设备树分区表三方对一遍。
- 在长跑的板上 `dmesg | grep -E "ECC|EBADMSG|EUCLEAN|bad block"`，认出这几行日志各自长什么样。
- 抓一次真实读写错误的最小证据集：一段读出数据 + OOB + status + 内核日志（见 [tutorial/rootfs/](../tutorial/rootfs/)）。

### 第 8 章：从 MTD 到 UBI/UBIFS

第 7 章讲完 SPI-NAND 是"前线"，这一章讲怎么在裸 NAND 上搭一个能用的文件系统。结论先放这：**裸 NAND 上不能直接跑 ext4，必须经 UBI 上 UBIFS**（或用老旧的 JFFS2）。为什么、怎么搭、怎么验证，这章拆开讲。

**先建两个概念：PEB 和 LEB。** UBI 把 MTD 的 erase block 包成 PEB（Physical Erase Block），在 PEB 头部塞两个 header：EC header（erase counter，磨损均衡靠它）和 VID header（volume id，标记这块 PEB 属于哪个 UBI volume）。向上，UBI 把逻辑块 LEB（Logical Erase Block）暴露给 UBIFS——LEB 数 = 好的 PEB 数减去 UBI 自己保留的开销（wear-leveling pool、坏块预留）。UBI 在 LEB 和 PEB 之间做映射，**写坏一个 PEB 就悄悄重映射到备用 PEB，对上层完全透明**。你在 UBIFS 里写一个文件，感觉不到底下哪块 PEB 坏了、被换走了——这正是 UBI 存在的意义。

**`ubiattach` 干的事：扫一遍、建表、隔离坏块。** 它扫描整个 MTD 设备，读所有 PEB 的 EC/VID header，建立映射表、初始化磨损均衡，把出厂坏块和用着用着长出来的新坏块都隔离出主池。磨损均衡的目的是让所有 PEB 的 erase counter 趋同——偶尔被擦的 PEB 会被主动挪到 wear-leveling pool 的另一端，**避免"热点数据把某些块擦坏、冷数据块从未被擦"这种致命偏斜**。没有这一层，你把 rootfs 写进 NAND，用不了多久就会被某一个热点块拖垮。

**UBIFS 是日志式的，这是它能扛断电的关键。** 每次修改先进 journal（一份固定、循环重写的日志），journal commit 后才落到主区。挂载时如果 journal 不完整（比如写一半断电了），UBIFS 走 recovery 把没 commit 的事务回滚掉，保证文件系统一致——**这就是 RK3506B 上 `/persist.log` 能跨冷重启存活的底层机制**，也是我们敢说"NAND 可靠"的底气。`autoresize` 是另一个有用的挂载特性：挂载时把 volume 一次性扩到 MTD 能容纳的最大值，这对"rootfs 占一个固定 volume、容量大小留到首启再定"的设计很合手（见第 9 章）。

**UBIFS 和 ext4 是两个世界，别混用。** ext4 跑在带 FTL 的块设备（eMMC/SD）上，FTL 在底层把磨损均衡和坏块管理全藏好了，ext4 自己只是个块级文件系统；UBIFS 跑在裸 NAND（经 UBI）上，磨损均衡和坏块管理由 UBI 负责，UBIFS 自己处理 journal 和树结构。**把 ext4 直接放到裸 NAND 上是错误用法**——没有 FTL 兜底，ext4 会很快把 NAND 写坏。NAND 上要么 UBIFS（经 UBI），要么 JFFS2（已较老、性能差）。RK3506B 这块板的正确分工：NAND 路线走 UBIFS，SD 路线走 ext4。

**真板结论先说死：这条链在 AES-RK3506B 上已经过验证。** SPI-NAND + UBI + UBIFS 在多轮冷重启、断电、长期写入下能稳定工作，证据在 [tutorial/rootfs/](../tutorial/rootfs/) 和 [logs/](../logs/) 的可靠性轮次记录里。这不是抄厂商 spec，**是 rk-forge 自己在板上跑出来的结论**，是本路线的核心差异化成果——R3 这一整章，加上第 9、10 章的置备和长跑，都是围绕怎么把这个"可靠"下成定论。

实践：
- `ubinize` 生成一份 UBI 镜像，`dumpimage`/`ubireader` 检查它的 PEB/LEB/EC/VID header。
- 真板上 `ubiattach` → `mount -t ubifs`，观察 `dmesg` 里 attach 和 recovery 的过程。
- 制造一次 journal recovery（写过程中硬重启），分析 `dmesg` 里 UBIFS 的 recovery 输出。
- 验证 rootfs volume 的容量和挂载参数（`compr`、`autoresize`）。

### 第 9 章：首启置备、可靠烧录与救援

这一章是 R3 最硬的一课，也是 RK3506B 路线区别于"刷个镜像就完事"的关键——讲清楚为什么烧录工具的"成功"在 NAND 上一钱不值，以及我们用什么办法替代它。

**先认清一个反直觉的事实：烧录工具说"成功"，证明不了数据在 NAND 上稳了。** 烧写器、`flashcp`、`nandwrite` 的"成功"只代表 page program 命令发出去了、status 寄存器回了个 OK。但 NAND 的写入有 program disturb、retention、断电窗口——刚写完的 page 在几秒甚至几分钟内仍可能因为电源毛刺或电荷泄漏而出错。**验证 NAND 数据可靠，只能靠 Linux 自己**：写完 `read` 回来比对、跑 ECC、扫坏块、多轮冷重启后再读一遍。第 7 章讲过原理，这里落到工程上。

**rk-forge 的解法是首启置备（initramfs provisioning）。** 板子第一次从一个最小 initramfs 起来，在 Linux 用户态下把产品镜像（rootfs、boot）写到 NAND 目标分区，写完做 readback 验证、置位置备 marker、然后 `switch_root` 切进产品 rootfs。**为什么"用 Linux 写"而不是"用烧录工具写"？** 因为 Linux 跑起来之后，UBI 能做坏块管理、ECC 校验、磨损均衡，写错的概率远低于烧录工具的裸写——厂商烧录工具往往跳过这些层，写出来的 rootfs 在用户手上才暴露问题（我们撞过的 loader 弱写 saga 就是这一类，详见 [tutorial/rootfs/](../tutorial/rootfs/)）。

**`switch_root` 是 initramfs 到产品 rootfs 的交接点。** 它做 `pivot_root` + `exec /sbin/init`，切换前要 `umount` initramfs 占的临时挂载、把 NAND rootfs 挂到新根、释放 initramfs 占的内存。**分区变化是这一步最大的风险**：置备后若分区布局改了（扩容、加新分区），UBI volume 表会变、`/dev/ubi*` 编号会变，bootargs 里的 `root=`、`ubi.mtd=` 必须同步改——改坏一个，下次启动就找不到根。

**三种镜像分清楚，各管各的，互不破坏。** **正常镜像**是日常运行的产品 rootfs；**置备镜像**从 initramfs 起、负责把产品 rootfs 写进 NAND；**救援镜像**是另一个最小 initfs/rootfs，产品 rootfs 挂不上时用来诊断和恢复。救援镜像尤其重要——**它必须能独立启动**（不依赖 NAND 产品分区）、能挂 NAND 做诊断、能恢复或重写产品 rootfs。一份"NAND 设备能不能交付"的硬指标，就是 rootfs 出问题时你还能不能进得去救它。本板 ROM 只认 RK-tool 类型的烧写卡（见 [tutorial/sd-boot/](../tutorial/sd-boot/) 与仓库 QUICK_START），这一条要先摸清，否则你连救援通道都搭不起来。

**交付前必须演练"故意改坏 → 救援 → 恢复"。** 分区布局和启动链、bootargs、U-Boot 环境变量是硬约定的：U-Boot 按固定偏移读 boot、内核按 `root=` 找 rootfs、UBI 按 `ubi.mtd=` attach，改分区要同步改这一连串配置。恢复路径要在交付前想好、练过——万一新分区表坏了、U-Boot 环境变量改错了，怎么用救援镜像救回来。**不能等产品上线后才发现救不回来**，那是事故，不是工程。

实践：
- 跑一次完整首启置备：从 initramfs 起 → 写产品 rootfs 进 NAND → readback 验证 → 置位 marker → `switch_root` 进产品系统。
- 验证置备的幂等性：跑两遍，确认第二遍不破坏第一遍的 marker、不重复扩容 UBI volume。
- 模拟产品 rootfs 损坏（`dd` 写坏一个 page），从救援镜像启动、挂 UBI 卷、修复 rootfs，且不破坏无关分区。

### 第 10 章：断电、冷重启与长期可靠性

"板子能起来"和"板子能交付"是两件事。能起来只证明链路在某一刻通；**可交付要求它在长期运行、多次冷热启、异常断电、温度变化下都稳定**。这一章讲怎么把"启动一次"变成"可交付"。

**验收 NAND 可靠性，唯一办法是故障注入 + 多轮次重复。** 写满 → 冷重启 → 读验证 → 断电 → 再启 → 再读，循环往复，每一轮记录 ECC 错误数、坏块数、UBI 重映射次数、UBIFS journal recovery 次数。没有"跑通一次就 ship"这种事——NAND 的弱点恰恰藏在第 100 次冷重启、第 50 次断电里，前 99 次都好好的，第 100 次挂了，这才叫问题。

**`sync`、冷重启、journal recovery 三件事要串起来。** `sync` 把脏页写回存储；冷重启（直接断电，不是 `reboot`）模拟异常下电，最能暴露 NAND 和 journal 的弱点。冷重启后 `dmesg` 里应看到 UBIFS journal recovery、文件系统保持一致——**如果看到 `read-only remount` 或 `mount failed`，说明可靠性不达标，得回去查**。AES-RK3506B 上 `/persist.log` 跨冷重启存活、UBIFS recovery 通过，就是这条验收的板上证据（见 [logs/](../logs/)）。

**写放大是 NAND 寿命的隐形杀手。** 写放大 = NAND 实际写入量 / 用户请求写入量。UBI/UBIFS 的 journal、磨损均衡、坏块重映射都会放大写量；带 FTL 的块设备则把放大藏进 FTL 你看不见。部署时有几条硬规矩：**把可写数据集中到一个独立 UBI volume、把系统分区设只读、日志限频或转网络**——这三招能把 NAND 寿命从几周延长到几年。频繁往 NAND 写 `syslog` 是常见的事故源，要么轮转、要么丢 tmpfs、要么送网络日志服务器。

**工业设备的标准布局：只读根 + 可写数据区 + A/B 升级。** rootfs 只读（避免误改、避免 NAND 写放大），数据区可写（独立 UBI volume），升级用 A/B 双 rootfs（一个跑、另一个后台写新版本、写完切启动）。**A/B + 只读根是 NAND 设备最稳的部署模型**：升级失败能回滚、运行时不会误改系统分区、NAND 写入集中在数据区、磨损可控。这是工业网关和数据采集设备的必修课，也是毕业项目 A、C 的交付形态。

**故障注入手段和验收指标，提前定死。** 注入手段：硬断电、写过程中 `reboot -f`、人为注入坏块（`mtd_debug erase` 一个块）、`nand_sim` 在 host 上模拟坏块。验收指标："X 轮冷重启 + Y 轮断电 + Z 小时连续写"，每一轮都记录 ECC/坏块/recovery 次数——RK3506B 这块板的真板轮次数据在 [tutorial/rootfs/](../tutorial/rootfs/) 和 [logs/](../logs/)。

实践：
- 跑 X 轮"写满 → 冷重启 → 读验证"循环，输出每轮的 ECC/坏块/重映射统计。
- 写过程中硬断电，重启后检查 UBIFS journal recovery 是否成功、文件系统是否一致。
- 模拟异常断电后的 rootfs 损坏，从救援镜像恢复，输出一份存储可靠性报告（坏块增长曲线、ECC 错误分布、journal recovery 命中次数）。

阶段产出：可恢复的 SPI-NAND 系统、NAND/UBIFS 验证规范、故障注入与恢复日志集合（喂给 [logs/](../logs/)）。

## R4：构建自己的用户系统

### 第 11 章：Buildroot 产品系统

buildroot 能编出 rootfs，不等于你有了产品 rootfs。这一章讲怎么把"一份最小 busybox 系统"做成"带自己业务、带构建身份、能维护的产品系统"——rk-forge 默认的 rootfs profile。

**先把一条纪律立住：改动全走 `BR2_EXTERNAL`，Buildroot 主树不碰。** `BR2_EXTERNAL` 是 Buildroot 留给定制者的目录：自定义 package、defconfig、board 文件、patch、`Config.in` 片段全放这里，Buildroot 主树保持干净。好处很实在——升级 Buildroot 版本时，你只需 rebase 自己的 `BR2_EXTERNAL` 这一层，不会和 Buildroot 主线改动打架。rk-forge 的 Buildroot 配置和自定义内容全走这条，绝不污染主树。

**工具链走外部，和 U-Boot/Linux 共用。** Buildroot 支持内部工具链（自己编 GCC/binutils）和外部工具链（用 `arm-linux-gnueabihf` 这种预编好的）。RK3506B 走外部，由 [config/toolchain.conf](../../config/toolchain.conf) 声明、`forge` 自动选用，**版本和 U-Boot/Linux 共用同一份**——这点很重要，工具链版本飘了，内核模块和用户态程序的 ABI 就对不上。sysroot 是工具链加目标库（libc、libgcc、内核 uapi）的根：编用户态程序时 `-sysroot` 指向它，链接期在这找 `.so` 和头文件。**sysroot 不一致是经典坑**——程序在 host 编过、target 上跑不起来（找不到 libc 或 ABI 不匹配）。

**三层定制：overlay、post-build、自定义 package，各管一摊。** `overlay/` 把任意文件按 rootfs 结构铺进去（`/etc/init.d/`、`/usr/bin/`），构建时 `cp -a` 进 staging——这是"成品文件直接铺"；`post-build.sh` 是镜像打包前跑的脚本，做收尾（生成 `/etc/version`、清调试信息）——这是"打包前的脚本逻辑"；自定义 package 把第三方源码（你的业务程序）写成 `foo.mk` + `Config.in`，让 Buildroot 像编普通包一样编它——这是"源码 → 编译 → 装进 rootfs"。**三者组合能覆盖绝大多数产品定制需求**，别一上来就 hack Buildroot 主树。

**BusyBox init + mdev，够小够用。** BusyBox init 是 `/etc/inittab` 驱动的最小 init：sysinit（系统初始化脚本）、respawn（getty/login）、shutdown（关机脚本）。`/etc/init.d/rcS` 按顺序跑 `S*` 脚本，就是 BusyBox 的"服务启动"机制。设备节点管理：BusyBox mdev 通过 hotplug 监听 uevent，自动创建 `/dev/*`——对 USB、SD 这类热插拔设备，mdev 配 `/etc/mdev.conf` 是轻量替代 udev 的方案，适合 NAND 这种资源紧张的板。

**最后，产品 rootfs 必须带可追溯的构建身份。** 版本号、git commit、构建时间、工具链版本、U-Boot/Linux 配对版本——这些由 `post-build.sh` 注入 `/etc/version` 或 `/etc/os-release`。故障定位时，**"这份 rootfs 是哪次构建出的、配哪份 U-Boot/内核"是第一句话**；没有构建身份的 rootfs 是不可维护的——别人拿到一块板，连它跑的是哪一版都不知道，怎么救？

实践：
- 把一个数据采集或状态上报程序写成 Buildroot 自定义 package（`foo.mk` + `Config.in`），编进 rootfs。
- 加 `/etc/init.d/S90foo` 启动脚本，让它系统启动后跑起来、配日志策略、异常退出自动重启。
- 真板上验证：安装位置、启动顺序、停止/重启、异常恢复、日志轮转。
- 注入构建身份到 `/etc/version`，验证两份不同 commit 的 rootfs 能在板上区分开。

完成结果不是"Buildroot 编译成功"，而是一份含自己业务程序、服务和维护信息的产品 rootfs。

### 第 12 章：OpenWrt 网络设备

buildroot 出的 rootfs 能跑业务，但你要的是一台"能 `opkg` 装包、LuCI 配置、A/B 升级"的网络设备，就该切到 OpenWrt profile 了。rk-forge 用 `--rootfs=openwrt` 切换，buildroot 不受影响——两条路并列，真板都验证过（见 [tutorial/openwrt/](../tutorial/openwrt/)）。

**OpenWrt 用三层组织硬件支持：target / subtarget / device。** `target` 是架构（如 `arm`）、`subtarget` 是 SoC 系列（如 Rockchip `armv7`）、`device` 是具体板子（如 AES-RK3506B），每层有对应的 `target/linux/*/` 子目录、`Makefile`、DTS、profile。**RK3506B 在 OpenWrt 里加一块新板，主要是写 device 的 DTS 和 profile、配 subtarget 的 `config-*`**，剩下 OpenWrt 主线框架接管。这和 Buildroot 的"BR2_EXTERNAL 改动"思路一致——把定制留在主树之外。

**工具链是 musl，和 Buildroot 不能混。** OpenWrt 默认用 musl libc（小、静态友好），工具链是 OpenWrt 自己编的；Buildroot 默认走 glibc 或 uClibc。**两套工具链绝对不能混用**：同一份 rootfs 混 musl 和 glibc 的 `.so`，会甩 `version GLIBC_x.x not found` 或 ABI 不匹配。OpenWrt 镜像和 Buildroot 镜像必须完全独立构建，不共享 sysroot。

**OpenWrt 最硬的约束：vermagic。** 内核模块（`kmod-*`）带 vermagic，模块的 vermagic 必须和运行内核**完全一致**才能加载，差一个字符就 `insmod: module verification failed`。vermagic 由内核版本加 `CONFIG_*` 编出来，意味着**升级内核 = 所有 kmod 必须重编 = opkg 仓库要同步更新**。任何自建 opkg 仓库都要配套管 vermagic，这是 OpenWrt 镜像管理的命门。rk-forge 让 OpenWrt 自建 kernel + rootfs（musl 工具链），vermagic 天然匹配，绕开了这个坑。

**OpenWrt 的"网络设备"栈，是它区别于 Buildroot busybox 的核心。** `opkg`（轻量包管理）、`uci`（统一配置接口，`/etc/config/` 下的 KV）、`procd`（init 替代，管服务生命周期和看门狗）、`netifd`（网络接口守护，管 bridge/VLAN/PPPoE/dhcp）、`firewall4`（基于 nftables 的防火墙）、`LuCI`（Web 管理界面）。**这一套把"网络设备"当一等公民**：配置、管理、热插拔、远程升级都有现成框架。RK3506B 双网口的天然应用场景——OpenWrt 边缘路由器——就是它的用武之地。

**Buildroot 还是 OpenWrt？按产品定位选，不是谁替代谁。** Buildroot 适合：自定义业务为主、网络是辅助、追求最小 rootfs、不需要动态装包（工业网关、数据采集终端的根盘）。OpenWrt 适合：网络是主功能、需要 uci/LuCI 管理、需要 opkg 动态装包和 A/B 升级、配置备份恢复（边缘路由器、企业级 AP）。RK3506B 同时支持两条路线：毕业项目 B（OpenWrt 边缘路由）用 OpenWrt，项目 A/C（工业网关、采集终端）用 Buildroot。

实践：
- 给 OpenWrt 镜像加一个自定义 opkg 包（一个守护进程 + 一个 uci 配置），编出来在板上 `opkg install` 验证。
- 写一个 procd 服务，让它崩溃后自动重启、依赖网络就绪后再启动。
- 配置双网口：WAN/LAN、DHCP server、NAT、防火墙规则，验证客户端能联网、规则生效。
- 验证 kmod 和内核 vermagic 配套（故意编一份不配套的 kmod，看 `insmod` 报什么）。
- `sysupgrade -b` 配置备份、`sysupgrade -r` 恢复，验证配置升级后存活。

阶段产出：Buildroot 产品镜像 或 OpenWrt 网络镜像（任选一条），加一份"Buildroot vs OpenWrt 选型报告"（喂给 [tutorial/openwrt/](../tutorial/openwrt/) 与 [tutorial/rootfs/](../tutorial/rootfs/)）。

## R5：工业接口与网络

### 第 13 章：双网口、GMAC 与 PHY

板上两个 RJ45，是 RK3506B 当工业网关和 OpenWrt 路由的命根子。这一章讲清楚一个网口从硬件到协议栈的整条链，以及"网口不通"时该从哪层查起。

**一个网口是四件套拼起来的：MAC、PHY、中间接口、MDIO。** MAC 是 SoC 里的以太网控制器（GMAC），管帧收发、DMA、checksum offload；PHY 是物理层芯片，把数字信号变成线缆上的电信号；两者之间用 MII/RMII/RGMII 这类接口连（RK3506B 的双口走 RMII）；MDIO 是 MAC 用来配置和读 PHY 寄存器的总线。AES-RK3506B 上的 PHY 是 YT8512——两个 RJ45 各走一条 PHY 链路。**摸清拓扑是排查"哪个网口不通"的第一步**，连有几个 PHY、是不是经过 switch 都不知道，就只能瞎猜。

**链路 up/down 是 PHY 自协商决定的。** PHY 自协商（auto-negotiation）决定速率（10/100/1000）和双工（半/全）。**协商失败会落到低速半双工，吞吐奇差**——这是"明明 link up 了却慢得像拨号"的常见真因。`ethtool eth0` 看当前协商结果，`ethtool -s eth0 speed 100 duplex full autoneg off` 能强制速率。强制速率两端必须一致，否则出现 link up 但全丢包的灵异现象。

**bridge、routing、NAT 是三种转发，数据通路不同，别混。** bridge（L2）把两个网口接到同一广播域，常用于"扩 LAN 口"；routing（L3）在不同子网间转发 IP 包，要内核开 `CONFIG_IP_FORWARD`；NAT 在出口改源 IP/端口，常用于"内网共享一个 WAN 出口"。**出问题时分层排查**：link/协商（PHY 层）→ ARP/邻居表（L2/L3 边界）→ route 表（L3）→ netfilter/NAT 规则。一上来就 `ping` 是没用的，先确认链路在哪一层。

**故障要归类：MAC、PHY、驱动、协议栈，四种病因。** MAC 故障（DMA 不工作、寄存器异常、中断不到）、PHY 故障（链路起不来、协商错速率）、驱动故障（probe 失败、NAPI 不调度、错误计数飙升）、协议栈故障（route 错、防火墙挡、socket buffer 满）。排查顺序：`ip link` 看 admin/oper state → `ethtool` 看 PHY 协商和统计 → `ethtool -S` 看 MAC 错误计数 → `ss`/`tcpdump` 看协议栈 → `nft list ruleset` 看防火墙。**把症状归到正确的层，能省下大量时间**——否则你在协议栈层调半天，真因是 PHY 上拉电阻没焊。

**吞吐、丢包、重连、长跑，是验收网口的四项硬指标。** 吞吐用 `iperf3` 打 TCP/UDP；丢包看 `ethtool -S` 的 `rx_crc_errors`、`rx_dropped`、`rx_missed_errors`；重连测拔线 → PHY down → 插回 → 链路恢复时序；长跑跑 24h+ iperf3 看 `rx_dropped` 增长和内存占用。**IRQ 分布也别忘**：双网口的中断应绑到不同 CPU 核（`/proc/interrupts` + `smp_affinity`），否则一个核被打爆就丢包。

实践：
- 独立验证两个网口：各接一台测试机，分别跑 iperf3，确认单口满速。
- 完成桥接或路由 + NAT：让 RK3506B 做两个网段之间的转发节点。
- 跑吞吐、丢包、断线重连测试，保存 `ethtool -S` 快照、内核日志、业务统计。
- 长跑 24h，输出一份"网络稳定性报告"，含 IRQ 分布、丢包趋势、重连时序。

### 第 14 章：I²C、SPI、UART 与 RMIO

工业接口三件套加 RK3506 的特色 RMIO，这一章讲怎么把外设接到这几条总线上，以及接不上时怎么分锅。

**先分清三件事：控制器、pinmux、板级接线，故障现象各不同。** I²C/SPI/UART 都是 SoC 里的串行控制器：控制器有寄存器基址、IRQ、时钟；pinmux 决定哪些 pad 复用成这个控制器的引脚；板级接线决定"这个控制器接了哪些器件、地址/片选/波特率多少"。**三者的故障分得很开**：控制器寄存器访问异常是 SoC 或驱动问题；pinmux 没配对，pad 还停在 GPIO 功能；板级接线错（地址错、片选错、电平错）则软件看起来全对、外设就是不响应。拿到一个"接不上"，先分清是哪一类。

**I²C 设备在 DT 里枚举，`i2c-tools` 是排查利器。** I²C 设备节点用 `compatible` + `reg`（7-bit 从地址）声明；用户态用 `i2cdetect` 扫总线、`i2cget`/`i2cset` 读写寄存器，内核态走标准 `i2c_client`。**几个经典坑**：上拉电阻缺失（总线起不来，`i2cdetect` 全空）、地址冲突（两个器件同地址）、电平不匹配（3.3V SoC 接 5V 器件要电平转换）、CLK 拉伸（clock stretching）控制器不支持。`i2cdetect -y N` 扫到地址是第一步，扫不到先查上拉和接线，别急着改驱动。

**SPI 有四种 mode，频率和片选也别瞎填。** SPI 的 mode 是 CPOL × CPHA 四种组合，不同器件要求不同；频率有上限（取决于器件和布线）；片选（CS）决定当前跟哪个从机说话。三者都在 DT 里声明，由 `spi_device` 持有。**填错 mode 是 SPI 最常见的事**——示波器上时钟相位和你以为的不一样，数据全错位。`spi-mem` 是为 SPI NOR/NAND/EEPROM 这类"命令式"器件的优化接口（一条命令读整页），普通 SPI 外设（传感器、ADC）走 `spi_transfer`——这条分界第 7 章讲 SPI-NAND 时提过。

**UART 最简单，RS-485 要管方向。** UART 是 TX/RX/GND 三线（可选 RTS/CTS 流控），Linux 抽象成 tty，`/dev/ttyS*` 是用户态接口。RS-485 是半双工差分总线，**必须管方向**：发送时拉 DE、接收时拉 RE。Linux 内核的 `SER_RS485` 接口（`ioctl TIOCSRS485`）支持自动方向控制，但要 UART 控制器硬件配合——**RK3506 的 UART 支持 RS-485 模式**，这是它做工业网关的加分项。

**RK3506 的 RMIO 又来了，这次落到接口上。** 第 5 章讲过 RMIO 是交叉开关，能把"控制器信号 → pad"的映射重新路由。在 I²C/SPI/UART 这里的实际用处：板级布线受限时，某个控制器的默认 pad 被占了，你可以靠 RMIO 把它挪到空闲 pad。**配置走 pinctrl，但语义比单纯 pinmux 多一层路由**——先决定"控制器信号 → RMIO 入口"、再决定"RMIO 出口 → pad"。改 RMIO 时一定核对你这块板的原理图，别照抄参考板。

实践（按真实硬件选若干项）：
- 接一个 I²C 传感器或触摸屏：`i2cdetect` 扫到、驱动 probe 成功、用户态读到合理数据。
- 接一个 SPI ADC 或 Flash：用 `spi-transfer` 或 `spi-mem` 读写，验证 mode/频率/片选配置正确。
- 接一个 UART/RS-485 协议终端：跑通半双工方向控制，做一轮收发测试。
- GPIO 告警或控制：把 GPIO 接到 input 子系统或 sysfs，验证输入防抖和输出电平。

### 第 15 章：USB、Wi-Fi 与音频选修

这三样在 RK3506B 上都板上验证过（README 的能力表里有），但都标"选修"——毕业项目用到哪样就深入哪样。这一章把它们一起讲，重点不在某个具体器件，而在理解"接进来要付什么代价"。

**USB 是 2.0，USB2PHY 加 DWC2。** RK3506 的 USB 是 USB 2.0：USB2PHY 管物理层（高速 480Mbps），DWC2 是 host/device 双模控制器。host 模式下，U 盘、WiFi dongle、HID 走标准 `usbcore` 加设备类驱动枚举。**USB 故障最常见三个原因**：PHY 时钟没起（USB2PHY 的 refclk 配错）、端口供电不足（外设拉电流超 spec，常见于机械硬盘）、OTG 角色切换的 ID 引脚没接对。

**WiFi 是 RTL8733BU，out-of-tree，这是它最该讲清楚的一点。** 板上的 WiFi 靠插在 USB 上的 RTL8733BU dongle，驱动**不在主线内核**，走 `cfg80211` 框架。rk-forge 把它搬到了 7.1 上，STA（连别人 AP）和 AP（自己开热点）都跑通，wlan0/wlan1 全链 probe 成功。但**`out-of-tree` 驱动的最大成本是版本维护**：每升一版内核都要重新 patch、确认 ABI 兼容，主线内核一变（比如 mac80211 接口签名变了）就可能编不过。这正是工业设备尽量避开 `out-of-tree` 驱动的核心理由——除非你别无选择，否则优先选主线已支持的硬件。

**音频链路：ALSA 顶、ASoC 扩、SAI 接、codec 转、DMA 搬。** Linux 音频栈分五层：ALSA 是顶层框架、ASoC 是 SoC 音频扩展（DPCM/DAPM）、SAI/I2S 是 SoC 的串行音频接口、codec 是外置音频芯片、DMA 负责把音频数据搬到控制器。AES-RK3506B 上是 ES8388 codec 加 SAI1——一条完整链路是 `CPU DAI (SAI1)` ↔ `CODEC DAI (ES8388)` ↔ 模拟侧，由 `simple-card` 或机器驱动把三段连起来。**任何一段配置错（DAI format、clock、BCLK/LRCLK 比例）都录不到声**——板上数字链路已通（声卡注册、aplay/mpg123 48k 干净播完），具体调音是另一层事。

**这一章的核心，是理解"接 `out-of-tree` 驱动 = 接受长期维护成本"这个权衡。** RTL8733BU 这类驱动每升内核都要重打补丁，是工业产品长期维护的隐患。替代路径：换主线支持的硬件、等驱动进主线、或用 vendor BSP 锁内核版本（这最后一条牺牲 mainline-first，是兜底，不是首选）。选修的意思是——毕业项目用到 USB/WiFi/Audio 哪一项就深入哪一项，不要求全做；但这个权衡判断，每个 BSP 工程师都得会做。

## R6：工程交付与真板取证

### 第 16 章：可复现构建与回归

"我机器上能编出来"不算交付。这一章讲 rk-forge 怎么用 `forge` 编排器把构建收成一条命令，让"任何人 clone 仓库、跑 forge、得到和我一样的镜像"成为可能。

**`forge` 把构建收成四个阶段：`setup → build → pack → assemble`。** setup 准备源码和补丁、build 编 U-Boot/Linux/rootfs、pack 打包成镜像、assemble 组装成可烧录的整体产物（详见 [tutorial/forge/](../tutorial/forge/)）。**编排器的价值是把散在 Makefile、shell 脚本、各种 README 里的步骤收成一条命令**，取代 RK-SDK `build.sh` 那种每次全量重编的体验。一条 `forge all` 跑完，`board/aes/out/update.img` 就是产物。

**所有输入必须 pin，否则三个月后编不出来是迟早的事。** 主线源码用具体 git commit、外部工具链用具体版本、`rkbin` 用具体 release、补丁库用具体 series 版本。**pin 的粒度越细，复现性越高**。`config/*.conf` 集中声明这些 pin 值（toolchain、Linux/U-Boot commit、`rkbin` 版本），`forge` 启动时读取。不 pin 的依赖，三个月后主线一更新你的构建就崩——这种事在嵌入式项目里见得太多了。

**增量构建靠内容哈希，不是时间戳。** `forge` 对源码树、补丁、配置算 sha256，哈希没变就跳过对应阶段、变了就重编对应产物——这让"改一个补丁只重编受影响部分"成为可能。**增量构建的纪律三条**：哈希算法要稳定（sha256）、输入集合要完整（不能漏算某个补丁文件）、缓存要能强制 invalidate（`--clean`）。**哈希算漏一个文件 = 增量构建返回错误结果 = 看似省时间实则埋雷**，这种 bug 比全量重编慢危险得多。

**干净构建和日常构建，分清楚什么时候用哪个。** 干净构建（`forge clean --full`）从零开始，所有阶段重跑，最慢但最可信；日常开发用增量，快但依赖哈希正确性。**规矩**：日常改一个驱动、调一个 DT 用增量；要交付镜像、要发版、要标 `verified` 时，必须干净构建验证一次。

**一项能力"已验证"，最低标准是三道检查都过。** host 检查（开发机环境：工具链版本、必要命令、磁盘空间）、构建检查（编译过没、产物齐不齐、哈希对不对）、真板检查（镜像烧到板上跑不跑得出预期）——**三道互相不能替代**。host 过了不代表构建对，构建过了不代表板上能跑。一项能力标 `verified`，意思是三道都过、别人能复现，缺一道都不算。详见 [tutorial/forge/](../tutorial/forge/) 和 [logs/](../logs/) 的真板记录。

实践：
- 在一台干净的开发机上 `git clone` rk-forge → `forge setup` → `forge build` → `forge assemble`，全程不依赖任何本地未提交改动，得到一份镜像。
- 对比两次构建（隔一段时间、不同 host）的产物哈希，验证可复现性。
- 故意改一个补丁，观察 `forge` 增量构建只重做受影响阶段；再用 `--clean` 重做，验证结果一致。
- 演练三道检查：host、构建、真板，记录每道的具体输出。

### 第 17 章：怎样证明一项能力已经完成

跑通一次不叫完成。这一章讲怎么把"我跑通了"变成"可由第二人复核的证据"——这是 RK3506B 路线收口的最后一章，也是 `partial` 升 `verified` 的硬标准。

**证据要有规范的命名和存放，乱起名等于没存。** bootlog 按 `boot-sdl-YYYYMMDDHHMM-说明.txt` 命名、产物按 `<组件>-<版本>.img` 命名、测试记录按 `<能力>-<日期>.md` 命名。RK3506B 的真板证据集中在 [logs/](../logs/)。**证据要长期保留、版本化（git 管理）**——临时存在本地、没入库的"我跑通了"不算证据，三个月后你自己都找不回来。

**一份完整 bootlog，从上电第一行截到 `login:`。** 中间不能断、不能合成——任何一段缺失，都让"这次启动到底是哪段工作的"变得无法核对。bootlog 要标版本：U-Boot/Linux 的 git commit、rootfs 的构建身份、`rkbin` 版本。这些信息嵌在日志本身的 banner 里，但**你要主动把它们和 [config/](../../config/) 的 pin 对一遍**，确认"日志里的版本 = 仓库里 pin 的版本"——否则你拿着一份对不上的日志，证据效力归零。

**每个产物都算 sha256，和源码 commit、补丁 series 版本一起记。** 哈希是"这份产物确实是从这份源码编出来的"的数学保证。别人拿到一份镜像，能用哈希核对它是不是你声称的那份；也能拿同样的源码自己编一遍，对比哈希是否一致，验证可复现性。idblock、uboot.img、boot.img、rootfs.img、整体固件包，一个都不能少。

**一条测试记录要写四件事：前提、步骤、期望、实际。** 前提（板子状态、外设、版本）、步骤（具体命令、操作顺序）、期望（应该看到什么）、实际（真的看到了什么）。**四者齐全才叫"可复核的测试"**：缺期望不知道结果对不对、缺步骤别人没法复现、缺前提别人不知道你跑在什么环境。常见的"我跑通了"往往是缺这四项的不可复核陈述——这种话在工程评审里一文不值。

**最后，状态更新要诚实，这是 rk-forge 的立身之本。** `verified`（log + 产物 + 配置齐备、可由第二人复现）、`partial`（基线板上验证但课程化未完成）、`planned`（目标定义但无真板）、`blocked`（明确卡在硬依赖）。**几条铁律**：跑通一次 ≠ `verified`；厂商 SDK 跑通 ≠ rk-forge `verified`；host 编译过 ≠ 真板通过。RK3506B 当前是 `partial`，升 `verified` 要把每一章的真板证据补齐——每一项能力的状态，都和它在仓库里的证据一一对应（见 [logs/](../logs/) 与 [tutorial/](../tutorial/)）。

最终产出：
- 可由第二人复现的构建说明（`forge` + 三道检查清单）。
- 一组可审查的真板日志（[logs/](../logs/) 里的 boot-sdl 系列）。
- 已知限制与回归清单（哪些能力 `blocked`、卡在哪、消除路径是什么）。

## 6. 候选毕业项目

每位学习者只需完成一个主项目。

## 项目 A：工业双网口协议网关

**建议进入主路线：是。**

- 目标：在两个网络区域之间转发、采集或转换现场设备数据。
- 最小版本：双网口、一个 UART/I²C/SPI 数据源、守护进程、本地持久队列、状态查询。
- 依赖课程：R3、R4、R5、R6。
- 硬件：AES-RK3506B、两个以太网连接、一个已确认的串行或总线设备。
- 关键风险：协议设备未确定、断网数据堆积、NAND 写放大。
- 真板验收：冷启动、断网重连、数据补传、多轮冷重启、24 小时运行、rootfs 救援。

## 项目 B：OpenWrt 边缘路由设备

**建议进入主路线：是。**

- 目标：形成可通过 LuCI/uci 管理、可安装软件包的双网口设备。
- 最小版本：WAN/LAN、DHCP、NAT、防火墙、自定义 opkg 和 procd 服务。
- 依赖课程：第 12、13、16、17 章。
- 硬件：AES-RK3506B、双网连接；Wi-Fi 功能按现有模块确认。
- 关键风险：kmod/vermagic、闪存容量、配置升级兼容。
- 真板验收：客户端联网、规则生效、服务重启、配置备份恢复、断电后配置存活。

## 项目 C：数据采集与本地协议转换终端

**建议进入主路线：作为可选项目。**

- 目标：采集现场总线或传感器数据，完成过滤、缓存和网络上报。
- 最小版本：一个真实数据源、本地时间戳和缓存、一种网络上报方式、诊断命令。
- 依赖课程：Buildroot 路线、工业接口、存储可靠性。
- 硬件：具体传感器或协议设备必须在立项时确认。
- 关键风险：未确认接口电平、协议范围过大、业务程序掩盖 BSP 学习目标。
- 真板验收：数据准确性、断网缓存、恢复补传、冷重启数据保留、长期运行。

## 7. 结课标准

完成路线不以“所有命令都执行过”为标准。学习者必须能够：

1. 独立说明 RK3506B 启动链及 rkbin 边界；
2. 从干净源码重复构建 U-Boot、Linux、DTB 和所选 rootfs；
3. 根据日志把故障定位到正确阶段；
4. 解释 SPI-NAND、UBI 和 UBIFS 的分层；
5. 完成多轮冷重启和存储恢复验证；
6. 接入至少一种工业接口和一种网络能力；
7. 交付一个毕业项目最小版本；
8. 保存版本、产物、日志、测试和已知限制。

## 8. 明确不讲或推迟

- 不把其他 RK3506 板卡写成已经兼容；
- 不用 RK3506B 课程代替完整 Linux/C 基础课；
- 不把闭源 rkbin 描述成开源；
- 不承诺无 blob 的纯主线启动；
- 不把显示、CAN、蓝牙、蜂窝网络等未形成稳定证据的能力列为必修；
- 不在本路线展开 AArch64、RK3588 媒体、NPU、GPU 或 Android；
- 不为了多平台抽象破坏现有 AES-RK3506B 基线。

