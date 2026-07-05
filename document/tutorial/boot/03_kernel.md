# Ch3 — 内核：补上那块属于我们的板级设备树

> Ch2 把主线 U-Boot 在板上跑起来了，接下来往这块底座上塞内核。主线 Linux 对 RK3506 的 clk、pinctrl、reset 驱动其实早就在主线里了，可偏偏这颗 SoC 连一份设备树都没有——这份板级 DT 正是 rk-forge 要补的核心。

## 前言：主线有驱动的骨架，缺的是描述血肉的设备树

U-Boot 能跑了，下一步自然是内核。这里有个对项目定位很关键的事实：主线 Linux 7.0.12 / 7.1 对 RK3506 是**有驱动**的——`clk-rk3506`、`rst-rk3506`、`pinctrl-rk3506` 这些早就合并进了主线。但驱动只是骨架，它还得有一份设备树告诉它"这颗 SoC 上有哪些控制器、各在什么地址、这块板子又启用了哪几个"。而这份 DT，上游**连 SoC 级的 `rk3506.dtsi` 都没有**，更别说板级 dts。

这就是 Ch0 那个结论落到实地：rk-forge 真正的贡献点在补这块板级设备树、并把它往上游推，驱动我们一行不写。这章干的就是这件事——从 vendor 的 `rk3502.dtsi` 把 SoC 描述搬过来、改成主线纯的，再给这块 AES 板写一份板级 dts。

## 补 SoC DT：从 vendor 搬，主线纯

搬 SoC 设备树听起来像体力活，但扒过一遍 vendor SDK 的 include 链之后，有个反直觉的发现能省不少事。vendor 对这块板的 DT 其实**稀疏得很**：io-domains 它根本不走 DT 建模（loader 配 IO 电压），PMIC 也不用（全是 fixed regulator），连 MTD 分区都走 cmdline `ubi.mtd=...` 而不是 DT 节点。换句话说，"对齐 vendor"能对齐的并不多，迁移的真身是补上 vendor 省略掉的那些主线板级 DT。

具体补的 [`rk3506.dtsi`](../../../patches/linux/0001-ARM-dts-rockchip-rk3506b-aes-SFC-W25N04KV-SPI-NAND-R.patch)（SoC 级），核心是 cru（时钟）、grf/grf_pmu（寄存器）、ioc（IO 控制器）、pinctrl 加 gpio0-4、uart0、gic、timer、otp，再加 sfc（SPI Flash 控制器）节点；clock-ID 这块和 vendor 共用同一套 `rockchip,rk3506-cru.h`，所以适配量不大。然后在板级 `rk3506b-aes.dts` 里启用 `&sfc`、挂上 `flash@0`（那颗 Winbond W25N04KV SPI-NAND），再用 fixed-partitions 把 7 个分区（uboot/misc/vnvm/recovery/boot/rootfs/userdata）按我们自己的 parameter 表摆好。这里有个省心的点：W25N04KV 主线的 `drivers/mtd/nand/spi/winbond.c` **本来就支持**（芯片 id `aa,23`，4Gb），NAND 驱动我们一行都不用写。

## 坑之一：SFC 读出来全是坏的——80MHz 裸奔的代价

DT 补好，内核一起来，SPI-NAND 读出来的数据却是坏的：bit 错、OOB 读坏，`mtd bad` 一查甚至报出过半"坏块"。笔者当时一度真以为这颗 NAND 出厂就半残，差点往坏块管理的方向深挖。

真因其实很朴素。主线那个 `rockchip_sfc.c` 驱动**从来不写采样延迟线寄存器（`SFC_DLL_CTRL0`）**，也就是完全不做采样窗口调谐；而 vendor 同名驱动里有个 `rockchip_sfc_delay_lines_tuning`，上板会扫一遍窗口、把延迟线设到采样最稳的位置。80MHz 这个频率裸奔、采样点又不调谐，读到的 bit 是非确定性地翻的，OOB 跟着读坏——那些"坏块"全是 80MHz 把 OOB 读坏造成的假象，块本身是好的。

bringup 那会儿最快见效的解法是一行 DT：把 `spi-max-frequency` 从 80MHz 降到 50MHz，50MHz 下采样窗口大到不调谐也稳，读就干净了。但这只是权宜，不是终局。

> 终局是把读速拿回 80MHz。后来我们从 vendor 驱动把 DLL 调谐移植进了主线 sfc 驱动（[patches/linux/0002](../../../patches/linux/0002-spi-rockchip-sfc-DLL-tuning-RK3506-power-good-gate-W.patch) + DT 侧 [0003](../../../patches/linux/0003-ARM-dts-rockchip-rk3506b-aes-bump-SFC-read-to-80MHz.patch)），上板扫出巨大的采样窗口、锁到 cell 130 附近（实测窗口 [90,170]），80MHz 下读稳，读速比 50MHz 快了一半，跟 vendor EVB（rk3506-evb2-v10 出厂就是 80MHz）对齐。完整 saga 见 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md)。所以现在的定型链是 80MHz + DLL 调谐，不是 50MHz 降频——50MHz 只是 bringup 阶段还没移植 DLL 时的过渡。
>
> 这里还顺带交代一个阴的细节：100MHz 我们也试过，不行。80MHz 的实际时钟是 PLL 抽出来的 75MHz tap，DLL 才有窗口可扫；100MHz 那档 PLL 抽出来是 98MHz，DLL 扫出的窗口是 [0,0]——一个 cell 都不给。所以 80MHz 不是随便挑的，是这颗 DLL 在这颗 SoC 上能稳的最高档。

## 坑之二：bootm 把自己覆盖了

内核 FIT 准备好，在 U-Boot 的 `=>` 提示符下把它读进内存、`bootm` 跳过去，听起来天经地义。但第一版笔者把 kernel FIT 暂存到了 `0x02080000`——这正是内核自己的加载地址。`bootm` 一边解压、一边往同一个地址写，自己把自己覆盖了，直接崩。

解法是换个不冲突的暂存地址：`0x04000000`。引导序列就成了这样：

```
=> mtd read boot 0x04000000 0 0xc00000
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> bootm 0x04000000
```

把 kernel FIT 从 boot 分区读到 `0x04000000`，设好 bootargs，再 bootm。`0x04000000` 这个数后面会反复出现，记住它就是"避开 kernel load 区的暂存点"。

## 坑之三：console "卡住"了，其实是波特率没带

内核好不容易起来了，`Starting kernel ...` 也打出来了，结果 earlycon 把控制权交接给真正的 ttyS0 console 之后，屏幕就"没动静"了——看着像内核卡死，其实人家在好好跑，只是你看不见。

这是 RK 的 DW 8250 console 的一个通病：bootargs 里 `console=ttyS0` 如果不跟波特率，console 接管后波特率不对，输出就乱了。正解是**必须带波特率**：`console=ttyS0,1500000`，上面那行 bootargs 里已经带上了。这种坑最磨人——你盯着一个"卡死"的串口排查半天内核，结果根因在 bootargs 漏了几个字符。

## 成功长这样

几个坑爬完，内核终于在板上起来了。下面这段是从内核 bringup 的定型 log（[boot-sdl-stage-end-of-kernel-uboot-202606151100](../../logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt)）里截的，一个字没合成：

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

每一行都值回票价：`Starting kernel` 说明 U-Boot 把内核成功交下来了；`Linux version 7.0.12` 是主线内核，不是 vendor 的 6.1；`Machine model: AES RK3506B Board` 这行最让人踏实——内核认出了我们亲手写的那份板级设备树；`earlycon` 和 `ttyS0 enabled` 说明 console 通了。最后那个 `panic: Unable to mount root fs` 不是 bug，是预期——我们这章压根没配 rootfs，它自然挂不上根文件系统。
