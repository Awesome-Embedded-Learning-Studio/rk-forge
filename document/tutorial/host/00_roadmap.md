---
title: "host 卷总纲：Linux 工作台与构建"
---

# host 卷总纲：Linux 工作台与构建

> 板无关基础卷：全部实验在 host（含 qemu-user）上真跑，零板级挂账。本文件是课程设计层总纲（定位、目录、依赖、最小实验、素材映射五件套），正文逐章走 content_forge 编辑闭环生产，编号与进度只留在本页，不进正文标题。
>
> 卷状态：⚪ 总纲立稿（2026-09-28 内部规划，2026-10-25 并入公开课纲）。成卷落点就是本目录，[00_wsl2](00_wsl2.md)、[01_usbipd](01_usbipd.md) 已兑现第 1 章的部分内容。

## 1. 领域定位

一句话：把手上这台电脑变成一台可靠的嵌入式构建工作站，并让读者能读懂 rk-forge 仓库里每一类工程文件。

- **教什么**：Linux 命令行基本功（以 forge 的视角看工作台）、shell 读功与工程脚本纪律、Git（基本功 → submodule / git am / bisect）、Make 与 Kbuild、Kconfig、交叉工具链（三元组 / ABI / 选型）、ELF 与二进制工具箱；收官于 host/armhf/aarch64 三向构建。
- **为什么是第一卷**：后续每一卷都站在这台工作台上；工具链选错（hard/soft float、前缀、版本）的代价在下游才爆发，所以它是地基的地基。最小验收「host/armhf/aarch64 三向构建并解释 ELF」由第 8 章兑现。
- **rk-forge 风味**：不写通用 Linux 101。每个知识点都从仓库自己的现实出发——board.yaml 的 toolchain 块、patches/linux/series、kernel.config、`python3 -m forge doctor`、reference/ 里 vendor build.sh 的对照。厂商书的环境搭建章（VMware/SDK 菜单）按[素材取舍判据](../../planning/index.md)（🔴 低价值）不收，只作 vendor vs mainline 反面参照。

### 边界（不收 / 移交）

| 内容 | 去向 |
|---|---|
| forge 编排器、content-hash 三纪律、可复现构建深讲 | 3506B 卷七（交付取证）；本卷只到「会跑 doctor、读得懂 board.yaml」 |
| 板侧 ELF64 / vermagic / oops 栈回溯 | 3568 卷一第 2 章；本卷只讲通论 |
| 用户态 C/C++ 编程本体 | 待重做的应用编程线（账面回退中）；本卷只做「编译与检视」 |
| VMware / Ubuntu 安装菜单、厂商 SDK 环境脚本 | 🔴 不收，反面参照 |
| 编辑器 / IDE / 桌面环境 | 不收 |

## 2. 章节目录（8 章）

| # | 章 | 章旨（读完能做什么） | 状态 |
|---:|---|---|---|
| 1 | 工作台：命令行基本功与 WSL2 现实 | 文件/权限/进程/管道/环境变量过关；理解 PATH 与 WSL2 互操作；会用 `python3 -m forge doctor` 体检 | 🟡 [00_wsl2](00_wsl2.md)、[01_usbipd](01_usbipd.md) 已兑现部分 |
| 2 | shell 读功与工程脚本纪律 | 读懂内核/构建系统里嵌的 shell 与 vendor 脚本；理解「新脚本一律 Python 纯标准库」的裁决与代价 | ⚪ |
| 3 | Git：从提交到 bisect | 基本功 → submodule（rkbin pin）、format-patch/git am（series 补丁）、bisect 定位回归 | ⚪ |
| 4 | Make：从规则到 Kbuild | 规则/变量/模式规则/伪目标；增量构建的 mtime 原理；读得懂 `obj-$(CONFIG_X) +=` | ⚪ |
| 5 | Kconfig：CONFIG_ 的世界 | Kconfig 语言、.config 与宏、defconfig 与 fragment；能读 boards/*/kernel.config 并逐项解释 | ⚪ |
| 6 | 交叉工具链：三元组、ABI 与选型 | 逐段解读 arm-none-linux-gnueabihf / aarch64-none-linux-gnu；hard/soft float；apt vs Arm GNU 15.3 vs vendor 三选型对照 | ⚪ |
| 7 | ELF 与二进制工具箱 | ELF 布局；file/readelf/nm/objdump/strip 各自在看什么；静态 vs 动态；host 工具检视交叉产物 | ⚪ |
| 8 | 三向构建收官 | 一份源码 × 三套工具链的迷你编译矩阵（纯标准库 Python），readelf 断言自检，qemu-user 跑交叉产物 | ⚪ |

## 3. 章间依赖

```text
Ch1 工作台 ─→ Ch2 shell/脚本 ─→ Ch3 Git ─→ Ch4 Make ─→ Ch5 Kconfig
                    │
                    └──────────→ Ch6 工具链 ─→ Ch7 ELF ─┐
                                                        ├─→ Ch8 收官
              (Ch3/4/5 也汇入 Ch8)──────────────────────┘
```

Ch3、Ch6 起点都只要 Ch1/Ch2，两支可并行；Ch4→Ch5 顺序敏感；Ch8 汇收全部。

## 4. 每章最小实验（提纲）

- **Ch1**：跑 `python3 -m forge doctor` 逐行解释；数 WSL2 脏 PATH 条目并解释构建为何拒绝；/opt 权限练习。
- **Ch2**：通读 reference 里 vendor build.sh 的一段逻辑并说出哪里难测；对比 shell 字符串拼接与 argv 数组（src/forge/core/proc.py）；演示 source 与执行的区别。
- **Ch3**：`git log --oneline` + `git blame` 还原一次真实改动；玩具仓库 `git am` 一遍 series 再看署名与可 bisect 性；`git submodule status` 看 rkbin pin；造 bug 用 bisect 定位。
- **Ch4**：手写三目标 Makefile（带模式规则），touch 单文件验证只重编一个产物；在内核树 Makefile 里标出受 CONFIG_ 控制的行。
- **Ch5**：逐项解释 boards/rk3568-atk/kernel.config 动的是哪个符号；`make defconfig` + menuconfig 改一项 + diff 出连锁。
- **Ch6**：两套工具链 `--version` 对照前缀差异；armhf 与 aarch64 各编最小 C，`readelf -h` 对拍 hard-float ABI；读两板 board.yaml 的 toolchain 块说明前缀为何不同。
- **Ch7**：同一份 C 三向编译，file + readelf 三份对拍 Class/Machine/Flags/NEEDED；nm 看 U/T 符号；strip 前后 size 对照。
- **Ch8**：`qemu-aarch64-static`/`qemu-arm-static` 跑通交叉产物；矩阵脚本输出全绿报告；命令与输出按四要素（前提/步骤/期望/实际）归档。

## 5. 卷级验收门槛

1. 同一份源码在三套工具链下编出三个产物，能用 readelf 逐项解释 Class/Machine/ABI/浮点差异；
2. armhf 与 aarch64 产物经 qemu-user 跑通，输出与 host 版一致；
3. 全程命令与真实输出归档（四要素口径），第二人按正文可复现。

QEMU 边界声明（诚实口径）：qemu-user 证明软件控制流与指令集执行，不证明目标板外设、时序与硬件行为；上真板属板线卷的验证面，不在本卷门禁内。

## 6. 素材与证据

| 现有资产 | 用途 | 状态 |
|---|---|---|
| [boot/01_toolchain](../boot/01_toolchain.md) | Ch1/Ch6/Ch7 底稿（hard-float、none 前缀、readelf 验证值、WSL2 PATH） | 🟡 强锚点，需泛化（旧路径 scripts→src/forge、toolchain.conf→board.yaml 已漂移，以现路径为准） |
| [forge/00_forge](../forge/00_forge.md) | Ch2/Ch4 背景（DAG、content-hash 思想） | 🟡 锚点，深讲归 3506B 卷七 |
| `src/forge/`（doctor.py、core/proc.py、build/、cli.py） | Ch1/Ch2/Ch4/Ch5 实物教材 | 🟢 在库 |
| `boards/*/`（board.yaml toolchain 块、kernel.config、patches series、parameter） | Ch3/Ch5/Ch6 实物教材 | 🟢 在库 |
| `third_party/rkbin`（submodule pin） | Ch3 submodule 实物 | 🟢 在库 |
| `reference/rk3588{,_android}/build.sh` | Ch2 反面/对照参照 | 🟢 在库（本地资料，不入站） |
| [rk3568/01_boot](../rk3568/01_boot.md) 工具链/ELF64 段 | Ch6/Ch7 底稿 | 🟡 板侧部分归 3568 线 |
| /opt Arm GNU 15.3 两套 + qemu-{arm,aarch64}-static | 实验环境 | 🟢 本机就位 |

> 每章规格细则（认知目标分档、降级路径、素材逐条映射）封存于内部规划区 host 卷总纲底稿，开写各章时回看；正文以本页目录与门槛为准。
