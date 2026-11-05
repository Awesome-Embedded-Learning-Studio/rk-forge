---
title: "卷一：读取真板，而不是背诵命令"
---

# 卷一：读取真板，而不是背诵命令

> RK3506B 线 · 卷一 · 第 1–2 章 · [返回线总览](index.md)

### 第 1 章：AES-RK3506B 系统全景

一句话：先认识板——家当、两条启动路线、闭源与开源的分界线；产出一张「源码 → 产物 → 分区 → 日志」对照表，当后面所有章节的参照原点。

要点：

- RK3506B = 3×Cortex-A7 跑 SMP Linux + M0 协处理器（多核异构 AMP，第 2 章展开）；板上家当：512MB DDR3、W25N04KV 512MB SPI-NAND、双 RJ45、RTL8733BU USB WiFi dongle；开发机 WSL2 几个 G 内存即可
- 两条启动路线（SPI-NAND / SD）由板级 strap 决定，链结构相同、差别只在介质与偏移；NAND 是卷四的可靠性主课，SD 路线不再只是预告——[sd-boot 卷](../../tutorial/sd-boot/)三章正文已兑现（RKFW 容器、SD-1 手动、SD-2 autoboot），适合快速试验与置备
- 启动链背下来：`BootROM → rkbin(TPL/SPL/DDR init, 闭源) → 可选 OP-TEE → U-Boot(主线) → Linux(主线) → rootfs → init`
- **闭源与开源的分界画在 rkbin 之后**——mainline-first 的咽喉，守不住就垮成又一个 BSP 镜像
- 四档状态口径（verified / partial / planned / blocked）；诚实现状：U-Boot 2026.07 + Linux 7.1 已板上跑通，但纯主线 boot 卡在 rkbin DDR init（第 3 章专讲）

实践：
- 拿一份 [logs/](../../logs/) 里的完整串口日志，逐行标出各阶段
- 把日志版本号映射回 [board.yaml](../../../boards/aes/board.yaml) `sources:` 与 [forge.yaml](../../../forge.yaml) 的 pin
- 把镜像映射到分区偏移与加载地址，建「源码—产物—分区—日志」对照表

保存证据：带行号标注的启动日志、启动链图、基线版本与产物摘要。

### 第 2 章：ARMv7-A、armhf 与三核 Cortex-A7

一句话：把「32 位」的硬约束与工具链坑讲清楚，专治从 64 位平台过来的人。

要点：

- ARM / Thumb / Thumb-2 混合编码：`-marm`/`-mthumb` 反汇编对比，是读 oops 栈回溯、对照厂商私有汇编的前提
- armhf 的 `hf` = hard-float，浮点走 VFPv4 寄存器；**装成 soft-float 工具链是经典坑**（`__aeabi_*` 链接错误离真因八丈远）；工具链由 board.yaml `toolchain:` 声明
- 七种处理器模式（USR/SYS/FIQ/IRQ/SVC/ABT/UND + Monitor）；AAPCS 调用约定用户态/内核态/signal frame 各一套，别混
- 次级核上线走 PSCI 或平台私有方法；OP-TEE 由 rkbin 先起，SMC 切换隔离
- 4GB 虚拟地址是硬天花板（highmem 这类约束），是切 AArch64 的根本动机之一；A7 跑 Linux、M0 跑裸机/RTOS，共享内存 + 中断通信

实践：
- `arm-linux-gnueabihf-gcc` 编 ELF32，`readelf -h` 核对 machine/flags
- 同一函数 `-marm`/`-mthumb` 各编一次，反汇编对比
- 真板 `cat /proc/cpuinfo`、`nproc`、`taskset` 看三核与调度

## 素材与取证

| 资产 | 用途 |
|---|---|
| [boards/aes/](../../../boards/aes/) | 板级目录当实物教具：五套 kernel config、parameter 表、RKBOOT ini |
| [logs/atk-standard-boot.txt](../../logs/atk-standard-boot.txt) | 第一份串口读物，第 1 章标注练习的原材料 |
| books/RK3506B 包的 ARMv7 编程手册与 Cortex-A7 TRM | 第 2 章架构素材（`.claude/books/`，本地资料） |
| [tutorial/host/](../../tutorial/host/) | 三板共用第 0 步前置卷（八章总纲 + WSL2/usbipd 两篇正文已兑现），第 1 章开发机环境在此承接，本卷不重述 |

## 缺口（待写）

- 第 1 章：「源码 → 产物 → 分区 → 日志」对照表练习未成章；逐行标注启动日志未设练习。素材：[logs/atk-standard-boot.txt](../../logs/atk-standard-boot.txt)、[boot/00 路线图](../../tutorial/boot/00_roadmap.md)。
- 第 2 章：七种处理器模式、ARM/Thumb 混编对比、AAPCS 调用约定、PSCI 次级核上线、highmem 约束未写（[boot/01](../../tutorial/boot/01_toolchain.md) 只到实用子集）。素材：books 的 ARMv7 编程手册与 Cortex-A7 TRM（`.claude/books/`，本地资料），挂 boot/01 之后作进阶篇。
