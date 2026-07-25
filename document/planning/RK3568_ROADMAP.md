---
title: "RK3568 教学路线：AArch64 Linux 驱动与接口工程"
---

# RK3568 教学路线：AArch64 Linux 驱动与接口工程

> 状态：**planned**。当前 rk-forge 尚未建立经过真板验证的 RK3568 target。本文件只定义教学目标、课程顺序、硬件依赖和项目候选，不表示 RK3568 已受支持。具体开发板、PCB 版本、存储、接口、设备树、BSP/SDK 版本确认前，不规划对应 pinout、镜像布局或烧录细节。

## 1. 路线承诺

RK3568 路线不重复 RK3506B 的 NAND bring-up，也不把 RK3588 的高级能力缩小一遍。它承担两项清晰任务：

1. 帮助学习者从 ARM32/Linux BSP 进入 AArch64、ATF 和 64 位用户系统；
2. 以真实外设为载体，系统学习 Linux 设备模型、标准驱动框架、DMA 和通用高速接口。

完成本路线后，学习者应能拿到原理图、datasheet、BSP 参考和一块新板，独立完成常见外设的 Linux 接入、调试、测试和交付。

## 2. 平台角色与边界

| 项目 | 本路线定义 |
|---|---|
| 目标 SoC | Rockchip RK3568，ARMv8-A / AArch64 |
| 具体开发板 | 待维护者确认 |
| 主角色 | 64 位通用 Linux 和驱动课程主平台 |
| 架构重点 | LP64、EL0–EL3、ATF、PSCI、64 位地址与 ABI |
| 驱动重点 | 设备模型、DT binding、IRQ、clock/reset/regulator、I²C/SPI、DMA、USB、PCIe、网络、基础 DRM |
| 用户系统 | Buildroot 教学系统；其他发行版只能在形成独立证据后增加 |
| 不承担 | RK3506B NAND 可靠性主课；RK3588 NPU、复杂 ISP/VPU、Android 产品主课 |

RK3568 与 RK3588 同为 AArch64，不代表二者能够共用 U-Boot、ATF、设备树、内核配置、模块、镜像或真板结论。

## 3. 适合谁学习

### 从 RK3506B 或其他 ARM32 BSP 进入

需要补：

- AArch64 工具链和 LP64；
- EL0–EL3 与 ATF；
- 64 位地址和 DMA 地址；
- cache 一致性；
- RK3568 具体启动存储和板级差异。

可以跳过：

- 交叉编译基本概念；
- U-Boot/Linux/rootfs 的通用定义；
- Git、补丁和基础日志阅读。

### 已经做过 Linux 驱动

通过自测后可以从 DMA、高速接口或 DRM 卷开始，但仍需完成：

- RK3568 基线证据；
- AArch64/ATF 对照；
- 板级资源与设备树审计。

### 直接进入

应具备：

- C 语言和基本数据结构；
- Linux 用户态编程；
- 进程、线程、文件、内存和并发基础；
- 能阅读简单原理图和芯片 datasheet。

本路线会补 Linux 驱动所需的最小内核基础，但不复制完整 Linux 基础教程。

## 4. 能力成长地图

| 阶段 | 学习者要解决的问题 | 阶段成果 |
|---|---|---|
| A0 理解平台 | ARM64 启动和 ARM32 有什么实质差异 | AArch64/ATF 启动图 |
| A1 掌握设备模型 | 怎样让内核发现并管理一个真实设备 | 规范的 platform driver |
| A2 掌握资源 | 怎样管理 GPIO、IRQ、clock、reset、regulator | 可正确上下电和响应中断的设备 |
| A3 掌握总线 | 怎样接入 I²C、SPI、UART 设备 | 使用标准子系统接口的驱动 |
| A4 掌握数据通路 | 怎样处理 DMA、USB、PCIe、网络 | 有性能数据的高速接口实验 |
| A5 掌握显示 | 怎样理解 DRM/KMS 显示对象 | 可解释的显示管线 |
| A6 掌握质量 | 怎样定位并证明驱动缺陷已经修复 | 驱动、测试、日志和文档交付 |

## 5. 课程编排

## A0：AArch64 与 RK3568 系统基线

### 第 1 章：RK3568 硬件和启动全景

RK3568 是社区主流支持的 AArch64 SoC——Collabora 等社区早就把它伺候得明白，主线支持成熟。这一章先建整张图的直觉：SoC 拓扑、启动链、BSP 与 mainline 的版本边界。具体板卡型号、PCB 版本、存储配置待维护者确认前，不写 pinout 和镜像布局——RK3568 当前是 `planned`，rk-forge 还没建 target。

**SoC 与 CPU 拓扑。** RK3568 是四核 Cortex-A55（ARMv8.2-A、AArch64），cluster 共享 L2 cache；A55 是能效核，四核 SMP 跑通用 Linux 驱动主课绰绰有余。**为什么 RK3568 适合做"通用 Linux 驱动主课"**：接口齐全（I²C/SPI/UART/USB/PCIe/GMAC/DRM）、社区主线支持成熟、外设能覆盖绝大多数子系统——你在它上学到的驱动框架知识，迁移到任何 AArch64 SoC 都通用。

**启动链全貌，和所有 AArch64 Rockchip 一样。** `BootROM → SPL/TPL → ATF(BL31) → 可选 OP-TEE → U-Boot → Linux → init`，每段职责：BootROM 加载下一段；SPL/TPL 训练 DDR；ATF 做 runtime secure monitor；U-Boot 加载内核并传 bootargs；内核挂 rootfs 起 init。**闭源段（BootROM 固化、`rkbin` 的 DDR/SPL blob）和开源段的分界画在 rkbin 之后**（详见 [blobs.md](../blobs.md)）——这和 RK3506B 一致，是 mainline-first 的咽喉。

**启动存储与分区。** RK3568 板卡通常用 eMMC 或 SD 作启动存储（具体按板子确认）；boot（kernel+dtb+ramdisk）、rootfs、vendor 等分区角色和 RK3588 一致（见 [RK3588 §2.3](RK3588_ROADMAP)）。镜像落到分区表固定偏移：idblock、loader、U-Boot proper、boot、rootfs 各有位置。

**BSP 与 mainline 的版本边界。** 厂商 BSP 通常停在某个 LTS 内核（如 5.10），主线已推进到更新版本；**主线对 RK3568 的支持已经很成熟**（pinctrl、clock、GMAC、USB、PCIe 等都进主线了），所以 RK3568 的 mainline-first 路线比 RK3506B 好走得多。差距口径见 [sdk-diff.md](../sdk-diff.md)。

**冻结一份最小真板基线，是 R0 的核心产出。** 版本 pin（U-Boot、ATF、Linux、rootfs、工具链），保存完整 bootlog、DTB、config、产物哈希——这份"已知良好"基线是后续每一章的参照原点。RK3568 待建 target 后补真板证据。

实践：
- 给一份完整启动日志逐行标注阶段；把日志里的版本号映射回源码 pin。
- 形成 CPU、内存、存储、设备树、内核版本的板卡硬件事实表。

### 第 2 章：AArch64 工具链、LP64 与 ELF64

RK3568 是 64 位的，这一章讲 AArch64 工具链和 ARM32 的关键差异——尤其是从 ARM32 过来的人容易栽的地方。

**AArch64 寄存器和调用约定。** X0-X30 通用寄存器，SP/LR/PC 各司其职；**AAPCS64 参数走 X0-X7、返回值在 X0**，调用者保存（X0-X7、X16-X18）和被调用者保存（X19-X28）约定明确。和 ARM32（r0-r12）的差异不仅是寄存器多了——调用约定、异常处理、栈布局全不同，**不能共用汇编**。读 oops 栈回溯时，X29（帧指针）、X30（返回地址）是关键。

**LP64 数据模型，从 ARM32 过来最容易栽的细节。** `int`=32、`long`=`pointer`=64。**64 位下 `long` 和指针变宽，结构体布局会变**——一份在 ARM32 上跑得好好的代码，搬到 AArch64 可能因为 `long` 尺寸变化而对齐出错或二进制不兼容。定宽类型（`uint32_t`/`uintptr_t`）是解药，**永远不要假设 `long` 是 32 位**。

**ELF64、动态链接、sysroot。** ELF64 的段和节、动态链接器加载流程；sysroot 是工具链加目标库（libc、libgcc、内核 uapi）的根，编用户态程序时 `-sysroot` 指向它。**sysroot 不一致是经典坑**：程序在 host 编过、target 上跑不起来（找不到 libc 或 ABI 不匹配）。库查找路径、`LD_LIBRARY_PATH`、target vs host 的隔离要理清。

**64 位内核、模块、用户程序，产物必须隔离。** `ARCH=arm64` 的内核构建；内核模块的 vermagic 和版本绑定；用户态交叉编译、strip、和 rootfs 对接。**ARM32 和 ARM64 产物绝对不能混**：两套工具链、两个 sysroot、两份 rootfs，混了就 `version GLIBC_x.x not found` 或 ABI 不匹配。错误架构程序/模块加载时的典型报错要认得。

实践：
- 同一份 C 源码分别编出 ARM32/ARM64 程序，对比 ELF 头（`readelf -h`）和结构体尺寸（`sizeof`）。
- 反汇编一个函数调用，观察 X0 / R0 的差异。
- 故意加载错误架构的 `.ko`，分析 dmesg 报错。

### 第 3 章：EL0–EL3、ATF 与 PSCI

这一章讲 AArch64 的异常级和 ATF——为什么 Linux 跑在 EL1、ATF 是什么、PSCI 怎么管多核。这是 32 位平台没有的概念（32 位用安全态/Monitor 模式）。

**异常级 EL0-EL3，AArch64 的核心抽象。** EL0 用户态、EL1 内核（Linux 跑这）、EL2 hypervisor、EL3 secure monitor；异常级别切换靠 `SMC`/`ERET` 等指令。**为什么 Linux 跑在 EL1**：EL1 有足够的权限管硬件、又不会越权到 secure world；EL2/EL3 各自承担虚拟化和安全监控。理解 EL 模型是看懂 AArch64 启动链的前提。

**ATF（TF-A）和 BL31。** ATF 的启动阶段 BL1/BL2/BL31/BL32/BL33，**BL31 是 runtime firmware，常驻不走**——它跑在 EL3，提供 PSCI 服务、SMC 处理，内核需要 secure 操作时通过 SMC 陷进 BL31。BL33 是 U-Boot。ATF 的存在是 AArch64 区别于 ARMv7 的标志（RK3506B 32 位没有 ATF）。

**PSCI 和多核启动。** PSCI（`CPU_ON`/`CPU_OFF`/`SUSPEND`）是 ARM 标准的电源状态管理接口；**次级核的释放靠 PSCI**——主核在内核启动阶段调 PSCI `CPU_ON` 唤醒次级核，次级核跳到指定入口跑二次初始化。`cpuidle`/`cpufreq` 也走 PSCI。

**可选 OP-TEE 和安全世界。** secure world / normal world 靠 EL3 隔离；OP-TEE 是开源 TEE，跑在 S-EL1，提供 TA（Trusted Application）运行环境。何时需要：产品要跑 DRM、密钥存储、安全启动校验时；不需求可省。RK 平台 OP-TEE blob 来源见 [blobs.md](../blobs.md)。

**Linux 进入 EL1 的交接。** 从 U-Boot（EL2 或 EL1）到 Linux 的异常级交接：U-Boot 通过 `booti` 把内核镜像加载到内存、配好 DTB 和 bootargs、跳进去；内核启动早期会降到 EL1 跑。**earlycon 出现之前发生了什么**：解压内核、修页表、设栈——这段没 console，出了问题只能靠 ATF/U-Boot 的早期打印。

**对照 RK3506B 的 ARMv7-A 启动模型，看清两代差异。** ARMv7 的安全态/Monitor 模式 vs AArch64 的 EL；RK3506B（32 位）没有 ATF，RK3568（64 位）必须有 ATF；**两块板的启动链和 blob 不能共用**——回到 [planning 总纲](./) 的硬边界。

实践：
- 从 bootlog 识别每个固件阶段（BootROM/SPL/ATF/U-Boot）；检查 CPU 上线时序。
- 分析一组 PSCI/CPU_ON 失败的日志。
- 和 RK3506B 的 ARMv7-A 启动模型做对照表。

### 第 4 章：U-Boot、设备树与开发 rootfs

这一章讲 U-Boot 怎么把内核加载起来、设备树怎么从 U-Boot 交给内核、Buildroot 怎么出最小 rootfs。**NFS root 对驱动开发的价值，是这章最该记住的一句**。

**启动方式和 bootcmd/bootargs。** eMMC/SD 启动：加载地址、偏移、环境变量；`bootcmd` 决定怎么找镜像、怎么加载、怎么跳；`bootargs` 是内核命令行（`console=`、`root=`、`rootwait`）。环境变量存 NAND 偏移、MMC 专用分区、或 baked-in。**改环境变量后要验回退路径**——万一新值起不来，得有按键进救援的机制。

**FIT 和 extlinux 两种启动方案。** FIT image 用节点描述多组件（kernel + dtb + initrd），每段挂 hash 做校验；extlinux.conf 是更简洁的启动配置。两种取舍：FIT 灵活但打包复杂，extlinux 简单但功能少。rk-forge 用纯 Python 打包 FIT 的做法见 [tutorial/forge/](../tutorial/forge/)。

**设备树从 U-Boot 到 Linux 的交接。** U-Boot 修改 `/chosen`、传 bootargs；dtb 和内核版本绑定（内核升级可能要求新 dtb）。**`fdt` 命令**在 U-Boot 下查看和修改设备树，调试时有用。

**Buildroot 最小开发系统。** 交叉工具链、最小 busybox rootfs；`BR2_EXTERNAL`（改动留主树外）、overlay、post-build。和主线内核/U-Boot 对接，注入构建身份（版本、哈希）。

**NFS root 对驱动开发的价值，这一节最值钱。** 内核和驱动在 host 编译、rootfs 在 host 挂载；**重启即加载新驱动，不必每次烧录 eMMC**。开发驱动时反复烧录 eMMC 是噩梦，NFS root 把这个周期从分钟级降到秒级。调试驱动的人没有 NFS root 等于裸奔。

实践：
- 建本地 Buildroot rootfs 和可选 NFS root；在 U-Boot 下改一个安全的内核参数并验证。
- 保留可恢复启动入口（环境变量回退）；验证内核、DTB、rootfs、模块版本一致。

## A1：Linux 驱动地基

### 第 5 章：字符设备与内核接口

这是 Linux 驱动的第一课——字符设备是最简单的驱动形态，理解了它，file_operations、用户态/内核态边界、并发同步这些核心概念就通了。但记住：**字符设备只是训练场，不是真实板级驱动的最终形态**，后面第 6 章会把它改造成 platform driver。

**内核模块的加载与生命周期。** 模块靠 init/exit 函数进出场；`module_param` 传参数、`EXPORT_SYMBOL` 导出符号给别人用。**模块依赖和加载顺序很重要**——`modprobe` 能处理依赖，`insmod` 不能；vermagic 把模块和内核版本绑死，版本不匹配直接拒绝加载。

**字符设备注册和 file_operations。** 主次设备号靠 `register_chrdev_region`（指定）或 `alloc_chrdev_region`（让内核分配）申请；`cdev_init`/`cdev_add` 把 cdev 注册进内核；**`file_operations` 是字符设备的灵魂**——open/read/write/release 这些回调，就是用户态 `read()`/`write()` 的最终落点。**`copy_to_user`/`copy_from_user` 是用户态和内核态的数据边界**，绝对不能直接 deref 用户态指针（那是安全漏洞，也是 oops 源头）。

**设备节点的创建。** 手动 `mknod` 是老办法；现代做法是 `class_create`/`device_create` 让 udev/devtmpfs 自动建 `/dev` 节点。主次设备号到 `/dev` 节点的映射，靠 devtmpfs 自动管理。

**并发与同步原语，选错就死锁或数据脏。** 原子操作（最轻）、自旋锁（短临界区，不能睡眠）、信号量/互斥锁（可睡眠）各有场景；**上下文约束是关键**：中断上下文只能用自旋锁，进程上下文才能用互斥锁。等待队列（`wait_queue`）和 `completion` 处理"等事件"，何时阻塞（进程上下文）、何时自旋（中断上下文）要分清。

**ioctl、poll、异步通知，用户态控制驱动的三件套。** `ioctl` 命令编号有约定（`_IO`/`_IOR`/`_IOW`/`_IOWR`，编码方向和尺寸）；`poll`/`select` 让用户态知道"现在能不能读/写"，靠等待队列实现；`fasync` 是异步通知（SIGIO），让内核主动叫醒用户态。三者组合，用户态才能高效地和驱动交互。

**错误路径与资源管理，这是驱动质量真正的分水岭。** `devm_*` 系列能自动释放资源（probe 失败或 remove 时），省去手动 free 的麻烦；**probe/open 中途失败的回滚顺序**必须严格——后申请的先释放，goto 链是惯用写法。**错误路径最考验驱动质量**，很多 bug 藏在"罕见错误分支的资源泄漏"里。

实践：
- 编写支持阻塞/非阻塞访问的字符设备；加 poll 和并发压力测试。
- 故意制造错误路径（probe 中段失败），验证资源完全释放。

> 字符设备是理解内核接口的训练场，不作为真实板级驱动的最终形态——从第 6 章起改造成 platform driver。

### 第 6 章：设备模型与 platform driver

字符设备是"自己注册自己管"，真实驱动要走设备模型——bus/device/driver/class 这套框架。这一章讲 platform driver，SoC 内部大多数外设都用它。

**Linux 设备模型对象。** bus/device/driver/class/kobject 是设备模型的积木；**引用计数管生命周期**，kobject 是基类。sysfs 是设备模型对用户态的投影，sysfs 属性的读写接口让用户态能配置驱动。

**platform bus 和 platform driver，SoC 内部外设的家。** platform bus 是给"非枚举式总线"（I²C/PCIe 能枚举，platform 不能）的统一抽象；SoC 内部控制器（USB、GMAC、I2C 控制器）都挂 platform bus。**probe/remove 是 driver 的核心**：设备和驱动靠 `compatible` 匹配上后调 probe，移除时调 remove。

**从 platform resource 获取资源。** `platform_get_resource` 拿寄存器区、`platform_get_irq` 拿中断号；**`devm_*` 系列是资源管理的正确姿势**——`devm_ioremap`、`devm_clk_get`、`devm_gpiod_get` 申请的资源，在 remove 时自动释放，不会泄漏。

**probe 失败、defer probe、remove 的语义。** probe 失败要返回错误码，内核会清理；**`-EPROBE_DEFER` 是特殊返回值**——"我这个驱动依赖的另一个驱动还没起来，等会儿再试"，内核会把 probe 推迟。常见于"先于 clock/regulator 起来的驱动"。remove 要和 probe 对称，资源全释放。

**设备模型对象关系，画张图就清楚了。** driver/device/class/sysfs 的关系，kobject 的层次。设备模型支撑 udev、电源管理、runtime PM——后面这些功能都建立在它之上。

实践：
- 把第 5 章的字符设备改造成 platform driver；从 platform resource 获取寄存器和 IRQ。
- 验证 probe 失败、defer probe、remove；绘制设备模型对象关系图。

### 第 7 章：设备树绑定与资源建模

设备树是 ARM 平台描述硬件的标准方式。这一章讲设备树怎么写、驱动怎么从设备树读资源、以及 binding 文档为什么重要。

**compatible 匹配，驱动和设备树的接头暗号。** `compatible` 字符串是驱动匹配设备树的钥匙，通常写两段 `"vendor,soc-periph", "vendor,periph"`（fallback）；`of_match_table` 在驱动里列出支持的 compatible。**of_device_id 结构和 `.of_match_table`** 是绑定的核心。

**标准属性五件套：`reg`、`interrupts`、`clocks`、`resets`、`supplies`。** `reg` 是寄存器物理基址和长度；`interrupts` 是中断号和触发类型；`clocks`/`resets` 是依赖的时钟和复位 phandle；`supplies` 是 regulator 供电。**phandle 是设备树的"指针"**，跨节点引用全靠它。`ranges`、`#address-cells`、`#size-cells` 处理地址空间的层级映射。

**SoC `.dtsi` 和板级 `.dts` 的分工。** SoC `.dtsi` 描述芯片固有能力（寄存器基址、clock 树、中断号、pinctrl 组），主线社区维护、SoC 通用；板级 `.dts` 描述"这块板具体用了哪些 SoC 能力、外接什么器件"，板子厂商或项目写。**板级 `.dts` 可以覆盖 `.dtsi`**（`status`、`pinctrl-0`、`bus-width`）。

**从设备树读属性。** `of_property_read_*` 系列读属性；`of_iomap` 映射寄存器、`of_irq_get` 取中断、`of_clk_get` 取时钟。设备树数据到驱动 probe 的数据流，是这一节的核心。

**设备树绑定（binding）和校验，为什么 binding 要上游化。** YAML binding 文档描述"一个节点应该长什么样"（哪些属性必需、值的格式）；`dtc` 编译、`dtbs_check` 用 binding 校验设备树。**binding 上游化是驱动进主线的前提**——主线不接受没有 binding 文档的驱动。

实践：
- 为一个实验设备编写或整理 binding 节点；从设备树读取属性。
- 故意制造缺失资源（缺 clock、缺 irq），分析 probe 结果；执行静态 DT 校验（`dtbs_check`）。

阶段产出：
- 一个结构规范的 platform driver；对应的设备树节点；用户态验证工具与测试记录。

## A2：GPIO、中断、电源与时钟

### 第 8 章：pinctrl、GPIO 与 input

这一章讲怎么管引脚——pinctrl 复用、GPIO 输入输出、input 子系统把按键触摸接到用户态。

**pinctrl 和 pinmux，把 pad 配成想要的功能。** SoC 的每个 pad 能复用成多种功能（GPIO、I2C、SPI、GMAC...），pinctrl 子系统管这件事。pin bank/group/drive-strength/pull 是 pinctrl 的基本概念。**设备树里 `pinctrl-0`/`pinctrl-names` 声明一个设备用哪些 pin 组**。引脚复用冲突是常见坑——两个设备声明同一个 pad，后 probe 的会失败。

**GPIO descriptor API，现代做法。** `gpiod_get`/`gpiod_direction_input/output`/`gpiod_set_value` 是 descriptor-based API，取代了旧的 `gpio_request`/`gpio_set_value`（基于编号）。**active-low/active-high 的抽象**：设备树里标 `GPIO_ACTIVE_LOW`，驱动用 gpiod API 时不用管物理电平反转，gpiod 自动处理。线名（line name）和板级映射让 GPIO 用名字而不是编号。

**input 子系统，按键触摸的标准入口。** input 设备注册后，上报事件（EV_KEY 按键、EV_ABS 触摸坐标、EV_REL 鼠标位移）；用户态从 `/dev/input/eventX` 读事件。**把按键接入 input 子系统而不是私有 ioctl**——这样所有标准工具（evtest、libinput）都能用，应用也不用为你的驱动写专门代码。debounce 防抖在 input 或 gpiod 层处理。

实践：
- 用真实按键或告警输入做 GPIO 中断或轮询；把按键接入 input（而不是私有 ioctl）。
- 故意声明冲突 pad，验证引脚复用冲突的报错。

### 第 9 章：GIC 与中断处理

这一章讲 ARM 的中断控制器（GIC）和 Linux 的中断处理——top half、threaded IRQ、中断风暴。

**GIC 架构。** GIC 有 v2/v3 多个版本，v3 引入 redistributor 和 LPI 支持；RK3568 的 GIC 版本以硬件为准。中断号、触发类型（边沿/电平）、亲和性（`smp_affinity`，把中断绑到特定 CPU）是 GIC 的基本参数。

**中断处理流程，top half 和 bottom half 的分工。** **top half（hardirq）是真正在中断上下文跑的那段**，必须快、不能睡眠；耗时工作推迟到 bottom half。bottom half 有几种实现：threaded IRQ（中断线程化，在内核线程跑，能睡眠）、workqueue（更重，能调度）、tasklet（逐步淘汰）。**`request_irq`/`request_threaded_irq`** 注册中断，后者把处理放到线程。**何时必须用 threaded IRQ**：处理需要睡眠或耗时（如 I2C 读寄存器）时，中断上下文不能睡眠，必须线程化。

**中断风暴、共享中断、丢中断，实战问题。** 中断风暴：某设备疯狂发中断，CPU 处理不过来；共享中断（`IRQF_SHARED`）：多个设备共用一个 IRQ 号，处理函数要能区分是不是自己的；丢中断：处理太慢或处理函数没正确清中断源，导致后续中断丢失。**`/proc/interrupts` 和 `/proc/softirqs`** 是诊断工具。

**延迟分析，中断响应要量。** 中断响应延迟（硬件事件到驱动处理的时间）用 tracepoint、`irqsoff` tracer 测；**延迟大的常见原因**：中断被禁用太久、threaded IRQ 调度延迟、共享中断里别的设备处理慢。

实践：
- 外部 GPIO 中断；中断计数和时间戳。
- 调整触发类型，分析错误现象；用 tracing 测响应延迟。

### 第 10 章：clock、reset、regulator 与 runtime PM

这一章讲驱动的"资源三件套"——时钟、复位、供电，以及 runtime PM 怎么省电。

**Common Clock Framework（CCF），Linux 时钟的统一框架。** 时钟有父子关系（parent/child）、频率、类型（mux 选择父时钟、divider 分频、gate 开关）。`clk_prepare_enable`/`clk_disable_unprepare` 开关时钟；`clk_get_rate` 查频率。设备树里 `clocks`/`clock-names` 声明依赖。**漏开时钟是经典 bug**——probe 时忘了 enable clk，寄存器读出来全是 0 或 hang。

**reset controller，复位信号的管理。** `reset_control_assert`/`deassert` 控制复位；设备树 `resets` 声明。**典型上电时序**：先 deassert reset、再 enable clock、再访问寄存器。顺序错（如先访问寄存器再 deassert）会读到垃圾值。

**regulator 供电依赖。** regulator 提供电压给设备（core 电压、IO 电压等）；`regulator_enable`/`disable`/`set_voltage`；设备树 `xxx-supply` 声明。**多路供电的上电顺序**很关键——有些设备要求 core 先上、IO 后上，顺序反了可能损坏硬件或锁死。

**runtime PM，设备空闲时自动省电。** runtime PM 让设备在不忙时自动 suspend（关时钟、降电压），忙时 resume。`pm_runtime_get/put_sync` 控制引用计数；`autosuspend_delay` 防止频繁开关。**漏关时钟、漏关电源的诊断**：`clk_summary`、`regulator_summary` 在 debugfs 能看到所有时钟和电源的状态，谁没关一目了然。

实践：
- 获取并管理真实设备的 clock/reset/supply；模拟 probe 中段失败，验证资源回收。
- 验证 suspend/resume 或 runtime suspend；分析漏关时钟。

## A3：标准总线与真实设备

### 第 11 章：I²C 与 regmap

I²C 是传感器、触摸屏、EEPROM 最常用的总线。这一章讲 I²C 驱动框架和 regmap——后者把寄存器读写统一到一套 API。

**I²C 子系统分层。** adapter（控制器驱动）、client（从设备）、message（传输）。设备树里 I²C 子节点声明从设备（`compatible` + `reg` 是 7-bit 从地址）。`i2c_transfer` 发自定义消息，`i2c_smbus_*` 走 SMBus 标准命令。**i2c-tools（`i2cdetect`/`i2cget`/`i2cset`）是排查 I²C 的利器**——先扫到地址，再写驱动。

**regmap，把寄存器读写统一。** regmap 抽象了"寄存器读写"——无论底层是 I²C、SPI 还是 MMIO，上层用同一套 API（`regmap_read`/`regmap_write`/`regmap_update_bits`）。好处：可缓存（避免频繁总线访问）、可调试（debugfs 暴露寄存器）、易适配多总线。**`regmap_config`** 配置 `reg_bits`/`val_bits`/`max_register`。

**标准子系统选择，别什么都写私有字符设备。** 同一个物理设备（如温度传感器）可以接入 hwmon（温度/电压监控）、IIO（ADC/加速度计）、input（触摸）等标准子系统。**优先用标准子系统**——这样标准工具（`sensors`、`iio_info`）能用，应用也不用为你的驱动写专门代码。

**总线错误与恢复。** I²C 的 NACK（设备不应答）、超时、总线死锁（SDA 被拉低起不来）；recovery 靠 SCL 脉冲把从设备释放。热插拔、拔插器件时驱动要能优雅处理。

实践：
- 接一个传感器或监控芯片；用 regmap 读写寄存器。
- 模拟总线错误（短路 SDA/SCL），分析恢复行为。

### 第 12 章：SPI 驱动

SPI 是另一条常用总线，接 ADC、传感器、SPI Flash、SPI 显示。这一章讲 SPI 驱动框架和它的坑。

**SPI 子系统分层。** controller（控制器）、device（从设备）、transfer（单次传输）、message（一组传输）。**mode（CPOL × CPHA 四种）、bits-per-word、max_speed_hz、片选（CS）** 是 SPI device 的核心参数，设备树里声明。**填错 mode 是 SPI 最常见的事**——示波器上时钟相位和你以为的不一样，数据全错位。

**同步和异步传输。** `spi_sync`（阻塞等完成）、`spi_async`（带回调，不阻塞）；`spi_message` 由多个 `spi_transfer` 组成，一次提交。小数据用同步，批量或高吞吐用异步。

**spi-mem 和普通 SPI 外设，两条路。** spi-mem 子系统为 SPI NOR/NAND/EEPROM 这类"命令式"器件优化（一条命令读整页），比传统 `spi_transfer` 高效；普通 SPI 外设（传感器、ADC）走 `spi_transfer`。**SPI NAND 走 spi-mem**——这条分界 RK3506B 的 SPI-NAND 章讲过。

**大块传输的性能边界。** DMA 传输 vs PIO；不同频率和传输长度的吞吐差异。逻辑分析仪对照软件发送和线上实际波形（CS、时钟、数据相位），是排查 SPI 的终极手段。

实践：
- 接一个 SPI ADC/传感器/显示；比较不同频率和传输长度。
- 用逻辑分析仪对照 SPI 事务，核对软件和波形。

### 第 13 章：UART、RS-485 与协议边界

UART 最简单，RS-485 要管方向。这一章讲 tty 子系统、RS-485 的方向控制、以及内核驱动和用户态协议的边界。

**tty 和 serial core。** UART 抽象成 tty，由 serial core + 8250/平台驱动管；`/dev/ttyS*` 是用户态接口。termios 配波特率、数据位、停止位、流控。

**RS-485 的方向控制，这是和 UART 最大的区别。** RS-485 是半双工差分总线，**必须管方向**：发送时拉 DE（Data Enable）、接收时拉 RE。Linux 内核的 `SER_RS485` 接口（`ioctl TIOCSRS485`）支持自动方向控制，但要 UART 控制器硬件配合（RK3568 的 UART 支持 RS-485 模式）。**方向切换时序**很关键——切早了数据截断，切晚了总线冲突。

**line discipline，协议在内核还是用户态。** line discipline（线路规程）是 tty 上的一层，可以处理特定协议（如 PPP、SLIP）。**大多数工业协议（Modbus、自定义）不该写内核 ldisc，应该放用户态**——内核负责字节流，用户态负责协议帧。

**内核驱动和用户态协议的边界。** 字节流（内核负责）vs 协议帧（用户态负责）。何时写内核 ldisc（少数情况，如 PPP），何时写用户态守护进程（多数工业协议）。工业协议服务的进程模型（多客户端、连接管理、状态机）通常在用户态实现。

实践：
- 验证串口和 RS-485；写一个用户态协议收发器（Modbus 或自定义）。
- 测试超时、半包、错误帧、断线重连。

## A4：DMA 与高速接口

### 第 14 章：DMAengine 与 cache 一致性

这是从基础驱动进入中高级驱动的分界章。DMA 让外设和内存直接搬数据、不占 CPU，但引入了"地址类型"和"cache 一致性"两个新问题。

**三种地址，必须分清。** CPU 虚拟地址（进程/内核看到的）、物理地址（RAM 的实际位置）、DMA 总线地址（设备看到的）。**IOMMU 存在时，DMA 地址经翻译才到物理地址**（RK3588 那种全 IP 过 SMMU 的平台上，设备地址 ≠ CPU 物理地址；RK3568 看具体配置）。驱动用 `dma_map_*`/`dma_alloc_*` 拿到的是 DMA 地址，这是写给设备寄存器的地址；**把它当物理地址用是入门级 bug**。

**coherent 和 streaming mapping。** coherent（`dma_alloc_coherent`）：硬件保证 CPU 和设备看到同一份 cache 一致的数据，不用显式 flush，适合常驻 buffer（如描述符环）；streaming（`dma_map_single`/`dma_map_sg`）：一次性传输，CPU 写完要 `sync_to_device`、设备写完要 `sync_to_cpu`。**选错就漏 flush（数据脏）或白 flush（带宽浪费）**。

**scatter-gather，大块传输的正确姿势。** scatterlist 把分散的内存段组合成一次 DMA 传输，`dma_map_sg` 映射整张表。大块或分页数据用 SG，避免单块连续内存的碎片化问题。

**cache 一致性，非一致架构必须显式 sync。** ARM 平台多数 IP 在非一致域，`arch_sync_dma_for_cpu/device` 是底层同步原语。**错误同步的现象**：读到旧数据（设备写了但 CPU cache 还是旧的）、写丢失（CPU 写了但没 flush 到 DDR，设备读到旧的）。

**DMAengine 框架，统一的 DMA 客户端接口。** `dmaengine_prep_*`（准备传输）、`dma_async_issue_pending`（提交）、回调（完成通知）。cyclic transfer（循环传输）用于音频等连续场景。**DMA 是中高级驱动的分水岭**——理解了三种地址和 cache 一致性，后面 USB/PCIe/网络都建立在它之上。

实践：
- 完成 DMA 内存传输；对比 PIO/DMA 的 CPU 占用和吞吐。
- 制造错误映射或错误同步，分析现象；用 trace/perf 记录数据通路。

### 第 15 章：USB

USB 接口丰富（host 外设、device gadget、OTG），驱动框架复杂。这一章讲 DWC3 控制器、枚举、gadget。**具体实验须等待开发板 USB2/USB3、Type-C 和角色确认**。

**USB 角色和 Type-C。** host（主，枚举外设）、device（从，被别人枚举）、OTG（双角色）；Type-C 的角色切换（DRP）、方向（正反插都行）让 USB 更复杂但更易用。

**DWC3 控制器，Rockchip 的 USB 核心。** DWC3 是 host/device 双模控制器，driver 分层（dwc3 核心 + dwc3-of-simple 平台层）。phy（usb2phy/usb3phy）和 controller 的关系、PHY 初始化时序是 USB 起来的前提。

**枚举、descriptor、endpoint，USB 协议的核心。** 枚举过程：host 给 device 分地址、读 descriptor（device/config/interface/endpoint）、加载驱动。**四种传输类型**：control（配置）、bulk（大批量，如 U 盘）、interrupt（周期小数据，如 HID）、isochronous（定时不保证完整，如音视频）。

**gadget，让板子当 USB 设备。** gadget framework 让板子能模拟 U 盘（mass_storage）、网卡（ncm/ECM）、串口（acm）等设备；configfs 动态组装 gadget，composite device 一个 gadget 多个 function。

**usbmon 和协议分析。** usbmon 抓 USB 包，Wireshark 能解析；这是定位 USB 协议问题的终极手段。

实践候选：
- host 外设枚举和压力测试；gadget 网络或存储功能。
- 热插拔、掉电、错误恢复。

### 第 16 章：PCIe 与 NVMe

PCIe 是高速串行总线，接 NVMe SSD、网卡、GPU 等。这一章讲 PCIe 框架。**仅在开发板确有可用 PCIe 接口和配套设备时进入主线**。

**Root Complex 和 Endpoint。** Root Complex（RC，主机侧）和 Endpoint（EP，设备侧）是 PCIe 的两端；PCIe 拓扑有 bus/device/function 三级寻址，switch 扩展更多端口。

**配置空间、BAR、MSI。** 配置空间读写（枚举设备、读 vendor/device id）；BAR（Base Address Register）分配设备内存映射到 CPU 地址空间；**MSI/MSI-X 是 PCIe 中断**（基于内存写，比 INTx 高效），高速设备必须用 MSI。

**PCI driver 匹配和链路训练。** PCI driver 靠 vendor/device id 匹配；`pci_enable_device` 启用设备。**链路训练（link training）** 是 PCIe 起来的过程，失败表现为设备探测不到或降速（gen1/2/3）。

**NVMe 作为 PCIe 设备。** NVMe 是 PCIe 上的存储协议，submission/completion queue 让存储吞吐远超 SATA/USB。

实践：
- 枚举设备，查 BAR/IRQ；跑存储或网络吞吐。
- 分析链路降速或训练失败。

### 第 17 章：GMAC、PHY 与网络性能

以太网是嵌入式设备的命脉。这一章讲 MAC/PHY/MDIO、NAPI、网络性能调优。

**MAC、PHY、MDIO 四件套。** MAC（控制器，管帧收发、DMA、checksum offload）、PHY（物理层芯片，管电信号）、中间接口（MII/RMII/RGMII）、MDIO（MAC 配置 PHY 的总线）。**PHY 自协商决定速率和双工**——协商失败落到低速半双工，吞吐奇差。

**descriptor ring 和 NAPI。** TX/RX descriptor ring 是 MAC 收发数据的环形队列；**NAPI（New API）是中断 + 轮询的混合**——中断触发后切到轮询，连续处理多个包再回中断模式，避免每个包一个中断的中断风暴。高负载下 NAPI 是吞吐的关键。

**ethtool 和链路管理。** `ethtool` 查看和配置链路（速率、双工、自协商、统计）；phylib 和 PHY 状态机管链路 up/down。

**吞吐、丢包、IRQ 分布。** 吞吐测 `iperf3`；丢包看 `ethtool -S` 的 `rx_crc_errors`/`rx_dropped`/`rx_missed_errors`；**IRQ 分布**把网卡中断绑到不同核（`smp_affinity`），否则一个核被打爆丢包。

实践：
- 链路配置和恢复；TCP/UDP 吞吐测试。
- CPU 占用、IRQ 分布、丢包分析；长时间网络稳定性。

## A5：显示与 HMI 选修

### 第 18 章：DRM/KMS 入门

> 只有在具体显示接口、屏幕和转换芯片确认后才能形成真板实验。

显示接口和屏幕确认后才能形成真板实验；本章先建 DRM/KMS 通用模型。

**framebuffer 和 DRM，新旧两代。** 老 fbdev 已经淘汰，现代 Linux 显示走 DRM/KMS；`/dev/dri/card0` 是 DRM 设备，render node 给 GPU 计算用。

**DRM/KMS 对象，四个核心。** plane（图层，可缩放/混合的内容）、CRTC（扫描器，按 pixel clock 从 framebuffer 读像素）、encoder（编码成物理链路协议 HDMI/DSI/eDP）、connector（物理接口，含 EDID、HPD）。**拓扑：plane → CRTC → encoder → connector**。Rockchip 的 VOP 是显示控制器，对应 CRTC + 多 plane。

**mode、pixel clock。** mode 是分辨率 + 刷新率（如 1920x1080@60），对应一组 hsync/vsync/blanking 时序参数；pixel clock = 总像素 × 帧率。**EDID 从显示器读 mode**（HDMI/DP），DSI/eDP 面板的 mode 写在设备树。

**pixel format、modifier、stride。** DRM 用 FOURCC 标识格式（XR24、NV12）；modifier 描述内存布局（tiled/linear）；stride 是行跨度。**modifier 不匹配是常见坑**——GPU/VPU 输出 tiled，CRTC 不支持就要 RGA 转 linear。

**atomic modesetting 和 page flip。** atomic 把 plane 配置 + CRTC 状态打包一次提交，要么全成功要么全回滚；page flip 在 vsync 切换 framebuffer，避免撕裂。

实践：
- 用 `modetest` 枚举 DRM 对象；显示测试图。
- 完成 page flip；分析 mode 或链路错误。

### 第 19 章：驱动调试工具

驱动写完不等于对，调试工具是定位问题的关键。这一章讲 dynamic debug、ftrace、perf、oops 分析。

**打印和 dynamic debug。** `pr_debug`/`dev_dbg` 配 dynamic debug（`/sys/kernel/debug/dynamic_debug/control`）动态开关打印；**过早打印（console 还没起来）的日志看不到**，要用 earlycon。

**debugfs 和 sysfs。** debugfs 是调试接口（`clk_summary`、`regulator_summary`、`gpio`、`iommu_groups`），sysfs 是稳定接口。两者分工不同。

**ftrace 和 tracepoint，内核行为时间线。** ftrace 抓 tracepoint（sched_switch、irq、dma_fence）；trace-cmd + KernelShark 让 ftrace 可视化。**定位延迟尖峰的标准流程**：抓一段 trace，看每个核在干什么。

**perf，性能热点。** `perf stat`/`record`/`report` 采样热点函数；常用指标 cycles、cache-misses、context-switches 能区分算力瓶颈还是内存瓶颈。

**oops/panic 分析和 KGDB。** oops 栈回溯靠 `addr2line`/`objdump` 定位源码行；panic 和 kdump 抓崩溃现场；KGDB 双机调试；KASAN/lockdep 等调试配置能抓内存错误和死锁。

实践：
- 定位一次空指针、泄漏、竞态或死锁。
- 记录 probe/IRQ/DMA 延迟；对比修复前后证据。

### 第 20 章：把驱动做成可维护交付物

驱动能跑只是第一步，做成可维护、可上游、可交付才是终点。这一章讲 Kconfig、binding、ABI、测试、patch series。

**Kconfig 和 Makefile。** `Kconfig` 加配置项（tristate: y/m/n），`Makefile` 用 `obj-$(CONFIG_*)` 决定是否编译。依赖和 select 关系要理清。

**设备树 binding，上游化的前提。** 为新节点写 YAML binding；`dtbs_check` 校验。**没有 binding 文档的驱动进不了主线**。

**用户接口和 ABI 稳定性。** 字符设备/sysfs/netlink 是常见接口；ABI 一旦暴露就难改，要慎重设计。用户接口要文档化（`Documentation/`）。

**错误路径和测试程序。** 错误路径完备性是驱动质量的核心；用户态测试程序 + kselftest 形成回归测试。

**patch series 和上游化。** 一个补丁一个 commit，`git format-patch`/`send-email`，带 `Signed-off-by`；patch series 拆分要合理（一个逻辑一个补丁），cover letter 说明背景。按社区流程（checkpatch、`Reviewed-by`）推进。

**host/构建/真板验证分层。** host 检查（开发机环境）、构建检查（编译和产物）、真板检查（板上跑通）三道分开，详见 [tutorial/forge/](../tutorial/forge/)。

最终产出：
- 驱动源码和配置；设备树/binding；用户态测试程序。
- 性能与稳定性报告；真板日志；已知限制清单。

## 6. 候选毕业项目

每位学习者选择一个主项目，不要求覆盖所有接口。

## 项目 A：Linux 通用驱动与接口验证平台

**建议进入主路线：是，首选。**

- 目标：将一组真实设备规范接入 Linux，并形成自动化验证平台。
- 最小版本：一个自行编写或深度移植的驱动、I²C/SPI/UART 中至少两类、中断、网络输出、自动测试。
- 进阶项：DMA、USB gadget、PCIe 或显示选择一项。
- 依赖课程：A1、A2、A3、A6；进阶项对应 A4/A5。
- 硬件：开发板确定后再选择传感器、ADC、输入设备或扩展板。
- 关键风险：外设选择过多、只追求点亮、缺少标准子系统接口。
- 真板验收：probe/remove、错误输入、并发压力、长时间运行、性能数据、日志完整。

## 项目 B：轻量工业 HMI

**建议进入主路线：有条件。**

- 目标：采集现场数据，在本地显示并通过网络管理。
- 最小版本：一个真实数据源、显示、触摸或按键、网络服务、状态记录。
- 依赖课程：I²C/SPI/UART、网络、DRM；GUI 框架只作为应用载体。
- 硬件：显示接口、屏幕、触摸和工业输入必须提前确认。
- 关键风险：GUI 工作量挤占驱动课程；显示硬件未确认。
- 真板验收：输入到显示闭环、热插拔/异常恢复、持续刷新、网络管理。

## 项目 C：PCIe/USB/网络综合设备

**建议进入主路线：有条件的高级项目。**

- 目标：围绕一个高速设备完成枚举、数据传输、网络服务和性能分析。
- 最小版本：PCIe 或 USB 二选一，加网络输出和性能监控。
- 依赖课程：DMA、USB/PCIe、网络、调试。
- 硬件：开发板对应接口和配套设备必须确认。
- 关键风险：信号完整性、供电、内核版本和外设兼容性。
- 真板验收：重复枚举、热复位或热插拔、吞吐、CPU 占用、错误恢复、长期运行。

## 7. 结课标准

学习者必须能够：

1. 解释 AArch64、ATF、PSCI 与 Linux 的交接；
2. 严格区分 ARM32/ARM64 工具链、sysroot、rootfs 和模块；
3. 编写一个规范的 platform/I²C/SPI 等真实驱动；
4. 正确管理 IRQ、GPIO、clock、reset 和 regulator；
5. 使用标准子系统接口而不是只暴露私有字符设备；
6. 完成 DMA 或一个高速接口实验；
7. 使用 ftrace/perf/dynamic debug 定位问题；
8. 交付驱动、设备树、测试、日志和已知限制；
9. 完成一个毕业项目最小版本。

## 8. 硬件确认门

以下事实确认前，相应章节只能保持 `planned`：

- 具体开发板型号和 PCB 版本；
- DRAM 容量；
- eMMC/SD/SPI Flash 等启动存储；
- 调试串口和烧录入口；
- 可长期使用的以太网、USB、PCIe、显示接口；
- 配套屏幕、触摸和扩展设备；
- 厂商 BSP/SDK、U-Boot、ATF 和 Linux 基线版本；
- 真板数量和自动化验证条件。

## 9. 明确不讲或推迟

- 不把 RK3568 写成已经支持；
- 不在板卡型号确认前写 pinout、分区和镜像布局；
- 不复制 RK3506B 的 SPI-NAND saga；
- 不从头复制完整 Linux/C 基础课；
- 不把字符设备 demo 当成驱动课程终点；
- 不一次覆盖所有内核子系统；
- 不把 RK3568 变成缩小版 RK3588；
- 不把 NPU、复杂 ISP/VPU、Android 放进本路线主干；
- 不默认与 RK3588 共用二进制产物。

