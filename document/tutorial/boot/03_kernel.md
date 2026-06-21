# Ch3 — 内核：补上那块属于我们的板级设备树

> Ch2 把主线 U-Boot 在板上跑起来了，这章我们往这块底座上塞内核。主线 Linux 对 RK3506 的 clk、pinctrl、reset 驱动其实早就在了，可偏偏连这颗 SoC 的设备树都没有——这块板级 DT 正是 rk-forge 的核心贡献。这章我们把它补出来，一行行解码 bootlog，直到 earlycon 亮起、console 真正接管。走完这一章，boot 系列的三块硬骨头（工具链 → U-Boot → 内核到 console）就全部啃下来了。

## 前言：主线有驱动的骨架，没有描述血肉的设备树

U-Boot 能跑了，下一步自然是内核。这里有个对项目定位极其关键的事实：主线 Linux 7.0.12 / 7.1 对 RK3506 是**有驱动**的——`clk-rk3506`、`rst-rk3506`、`pinctrl-rk3506` 这些早就合并进主线了。但驱动只是骨架，它还需要一份设备树告诉它"这颗 SoC 上有哪些控制器、各在什么地址、这块板子又启用了哪些"。而这份 DT，上游**连 SoC 级的 `rk3506.dtsi` 都没有**，更别提板级 dts。

这就是 Ch0 反复强调的那个结论落到实地：rk-forge 真正的贡献点，不是写驱动，而是补这块板级设备树，并且把它往上游推。这一章干的就是这件事——从 vendor 的 `rk3502.dtsi` 把 SoC 的描述搬过来、改成主线纯的，再给我们这块 AES 板写一份板级 dts。

## 补 SoC DT：从 vendor 搬，主线纯

搬 SoC 设备树这事，听起来像体力活，其实有个反直觉的发现能省不少事。我们把 vendor SDK 的板级 DT include 链一路扒下来，发现 vendor 对这块板的 DT 其实**稀疏得很**：io-domains 它根本不通过 DT 建模（loader 配 IO 电压），PMIC 它也不用（全 fixed regulator），连 MTD 分区都是走 cmdline `ubi.mtd=...` 而不是 DT 节点。换句话说，"对齐 vendor"能对齐的并不多——迁移的真身，是补上 vendor 省略掉的那些主线板级 DT。

具体补的 [`rk3506.dtsi`](../../../patches/linux/0001-ARM-dts-rockchip-rk3506b-aes-SFC-W25N04KV-SPI-NAND-R.patch)（SoC 级），核心是 cru（时钟）、grf/grf_pmu（寄存器）、ioc（IO 控制器）、pinctrl 加 gpio0-4、uart0、gic、timer、otp，以及 sfc（SPI Flash 控制器）节点。clock-ID 这块和 vendor 共用同一套 `rockchip,rk3506-cru.h`，所以适配量不大。然后在板级 `rk3506b-aes.dts` 里启用 `&sfc`、挂上 `flash@0`（那颗 Winbond W25N04KV SPI-NAND），再配 fixed-partitions 把 7 个分区（uboot/misc/vnvm/recovery/boot/rootfs/userdata）按我们自己的 parameter 表摆好。这里有个省心的点：W25N04KV 主线的 `drivers/mtd/nand/spi/winbond.c` **本来就支持**（芯片 id `aa,23`，4Gb），不用我们写一行 NAND 驱动代码。

## 坑之一：SFC 读出来全是坏的——80MHz 裸奔的代价

DT 补好，内核一起来，SPI-NAND 读出来的数据却是坏的——bit 错、OOB 读坏，`mtd bad` 一查甚至报出过半"坏块"。笔者当时一度真以为这颗 NAND 出厂就半残，差点往坏块管理的方向深挖。

真因其实很朴素：主线那个 `rockchip_sfc.c` 驱动**从来不写采样延迟线（DLL）的调谐**，而 vendor 驱动是会的。80MHz 这么高的频率裸奔，没有 DLL 做采样窗口调谐，读到的 bit 是非确定性地翻的，OOO 也跟着读坏——那些"坏块"全是 80MHz 把 OOB 读坏造成的假象，块本身是好的。当时的解法是一行 DT：把 `spi-max-frequency` 从 80MHz 降到 50MHz，50MHz 下读就稳了，bringup 够用。

> 诚实交代一句后续：后来我们把 vendor 的 DLL 调谐移植进了主线 sfc 驱动（[patches/linux/0002](../../../patches/linux/0002-spi-rockchip-sfc-DLL-tuning-RK3506-power-good-gate-W.patch)），扫出采样窗口，把读速拿回了 80MHz。完整 saga 见 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md)。但 bringup 那会儿，50MHz 是最快见效的路。

## 坑之二：bootm 把自己覆盖了

内核 FIT 准备好，在 U-Boot 的 `=>` 提示符下把它读进内存、`bootm` 跳过去，听起来天经地义。但第一版笔者把 kernel FIT 暂存到了 `0x02080000`——这正是内核自己的加载地址。`bootm` 一边解压、一边往同一个地址写，自己把自己覆盖了，直接崩。

解法是换个不冲突的暂存地址：`0x04000000`。引导序列就成了这样：

```
=> mtd read boot 0x04000000 0 0xc00000
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> bootm 0x04000000
```

把 kernel FIT 从 boot 分区读到 `0x04000000`，设好 bootargs，然后 bootm。`0x04000000` 这个数后面会反复出现，记住它就是"避开 kernel load 区的暂存点"。

## 坑之三：console "卡住"了，其实是波特率没带

内核好不容易起来了，`Starting kernel ...` 也打出来了，结果 earlycon 把控制权交接给真正的 ttyS0 console 之后，屏幕就"没动静"了——看着像内核卡死，其实人家在好好跑，只是你看不见。

这是 RK 的 DW 8250 console 的一个通病：bootargs 里 `console=ttyS0` 如果不跟波特率，console 接管后波特率不对，输出就乱了。正解是**必须带波特率**：`console=ttyS0,1500000`。上面那行 bootargs 里已经带上了。这种坑最磨人——你盯着一个"卡死"的串口排查半天内核，结果根因在 bootargs 漏了几个字符。

## 成功长这样

四个坑爬完，内核终于在板上起来了。下面这段是从内核 bringup 的定型 log（[boot-sdl-stage-end-of-kernel-uboot-202606151100](../../logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt)）里截的，一个字没合成：

```
Starting kernel ...

[    0.000000] Linux version 7.0.12-dirty ... #1 SMP Sun Jun 14 22:13:58 CST 2026
[    0.000000] OF: fdt: Machine model: AES RK3506B Board
[    0.000000] earlycon: uart8250 at MMIO32 0xff0a0000 (options '')
[    0.000000] Kernel command line: earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000
...
[    0.271255] printk: legacy console [ttyS0] enabled
...
[    1.054644] Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(0,0)
```

每一行都是一座里程碑：`Starting kernel` 说明 U-Boot 把内核成功交下来了；`Linux version 7.0.12` 是主线内核（不是 vendor 的 6.1）；`Machine model: AES RK3506B Board` 这一行最让人踏实——内核认出了我们亲手写的那份板级设备树；`earlycon` 和 `ttyS0 enabled` 说明 console 通了。最后那个 `panic: Unable to mount root fs` 不是 bug，是预期——我们这章压根没配 rootfs，它自然挂不上根文件系统。

## 走到这里

boot 系列三章走完，PLAN §5 那个硬里程碑——"RK3506 用主线 Linux 启动到 UART"——算是实打实拿下了。你能从一根空的 SPI-NAND 或一张 SD 卡出发，编出主线 U-Boot、补上板级设备树、把主线内核引到 console 亮起。这整条链，除了那个暂时绕不开的 rkbin DDR blob，从 U-Boot 到内核每一行都是主线源码、能追、能改、能 bisect。

至于内核起来之后那行 `panic: Unable to mount root fs` 怎么消掉——怎么让 rootfs 真正持久地落进 SPI-NAND、怎么把外设一个个点亮——那是后续篇章的事，不在 boot 系列里。boot 这三块硬骨头啃完了，给板子拍张照，撒花不过分。
