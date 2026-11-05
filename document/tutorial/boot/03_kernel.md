# Ch3 — 内核：补上那块属于咱们的板级设备树

> Ch2 把主线 U-Boot 在板上跑起来了，接下来咱们往这块底座上塞内核。主线 Linux 对 RK3506 的 clk、pinctrl、reset 驱动其实早就在主线里了，可偏偏这颗 SoC 连一份设备树都没有。这块板级 DT 正是 rk-forge 要补的核心。

## 前言：主线有驱动的骨架，缺的是描述血肉的设备树

U-Boot 能跑了，而咱们下一步自然要面对的就是内核。这里有个对项目定位很关键的事实：主线 Linux 7.0.12 / 7.1 对 RK3506 是**有驱动**的，`clk-rk3506`、`rst-rk3506`、`pinctrl-rk3506` 这些早就合并进了主线。而驱动只是骨架。设备树负责告诉它这颗 SoC 上装了哪些控制器、各在什么地址，这块板子又启用了哪几个。而 DT 这一层，上游**连 SoC 级的 `rk3506.dtsi` 都没有**，更别提板级的 dts 了。

Ch0 的那个判断在咱们这里落到了实地：rk-forge 真正的贡献点在补这块板级设备树、并把它往上游推，驱动咱们一行不写。这一章干的就是这件事，从原厂的 `rk3502.dtsi` 把 SoC 描述搬过来、改成主线纯的，再给这块 AES 板写一份板级的 dts。

## 补 SoC DT：从原厂搬，主线纯

SoC 设备树的搬运听起来像体力活，但咱们扒过一遍原厂 SDK 的 include 链之后，有个反直觉的发现能省不少事。原厂对这块板的 DT 其实**稀疏得很**：io-domains 它根本不走 DT 的建模（loader 配 IO 电压），PMIC 也省了（全是 fixed regulator），连 MTD 分区都走 cmdline `ubi.mtd=...` 而不是 DT 节点。所以“对齐原厂”能对齐的并不多，迁移的真身是补上原厂省略掉的那些主线板级 DT。

具体补的 [`rk3506.dtsi`](../../../boards/aes/patches/linux/0001-ARM-dts-rockchip-rk3506b-aes-SFC-W25N04KV-SPI-NAND-R.patch)（SoC 级），核心的节点是 cru（时钟）、grf/grf_pmu（寄存器）、ioc（IO 控制器），外加的还有 pinctrl 加 gpio0-4、uart0、gic、timer、otp，还有 sfc（SPI Flash 控制器）的节点。clock-ID 和原厂共用的就是同一套 `rockchip,rk3506-cru.h`，所以适配量不大。然后在板级的 `rk3506b-aes.dts` 里启用 `&sfc`、挂上 `flash@0`，就是那颗 Winbond W25N04KV SPI-NAND 的闪存。然后咱们用 fixed-partitions 把 7 个分区摆开，uboot、misc、vnvm、recovery、boot、rootfs、userdata 的七个名字，咱们按自己的 parameter 表落位。这里有个省心的点：W25N04KV 主线的 `drivers/mtd/nand/spi/winbond.c` **本来就支持**（芯片的 id `aa,23`、容量 4Gb），NAND 驱动咱们一行都不用写。

## 翻车一：SFC 读出来全是坏的，80MHz 裸奔的代价

DT 补好了，内核也起来了，SPI-NAND 读出来的数据却是坏的：bit 错、OOB 读坏，`mtd bad` 一查甚至报出了过半的“坏块”。笔者当时一度真以为这颗 NAND 出厂就半残，差点往坏块管理的方向深挖。

咱们后来看清的真因其实很朴素。主线那个 `rockchip_sfc.c` 驱动**从来不写采样延迟线的寄存器（`SFC_DLL_CTRL0`）**，也就是完全不做采样窗口的调谐。而原厂同名驱动里有个 `rockchip_sfc_delay_lines_tuning`，板子一上电就扫一遍窗口、把延迟线设到采样最稳的位置。80MHz 的频率裸奔、采样点又不调谐，读到的 bit 是非确定性地翻的，OOB 也跟着读坏了。那些坏块全是 80MHz 把 OOB 读坏造成的假象，块本身是好的。

bringup 那会儿最快见效的解法是一行 DT：咱们把 `spi-max-frequency` 从 80MHz 降到 50MHz，50MHz 下的采样窗口大到不调谐也稳，读就干净了。但这不过是一时权宜的过渡，真正的终局在后面。

> 终局的目标是把读速拿回 80MHz。后来咱们从原厂驱动把 DLL 调谐移植进了主线 sfc 驱动（[patches/linux/0002](../../../boards/aes/patches/linux/0002-spi-rockchip-sfc-DLL-tuning-RK3506-power-good-gate-W.patch) + DT 侧 [0003](../../../boards/aes/patches/linux/0003-ARM-dts-rockchip-rk3506b-aes-bump-SFC-read-to-80MHz.patch)），在板上扫出巨大的采样窗口、锁到 cell 130 附近，实测的窗口是 `[90,170]`，80MHz 下读稳了，读速比 50MHz 快了一半，跟原厂 EVB 对上了，rk3506-evb2-v10 出厂就是 80MHz 的档位。完整的排查记录见 [pitfalls/04](../../pitfalls/04-sfc-nand-saga.md)。所以现在的定型链是 80MHz 加 DLL 调谐，50MHz 降频只是 bringup 阶段还没移植 DLL 时的过渡。
>
> 这里还顺带交代一个阴的细节：100MHz 咱们也试过，其实不行。80MHz 的实际时钟是 PLL 抽出来的 75MHz tap，DLL 的窗口才有得扫。100MHz 那一档的 PLL 抽出来是 98MHz，DLL 扫出的窗口是 `[0,0]`、一个 cell 都不给。所以 80MHz 不是随便挑的，这颗 DLL 在这颗 SoC 上能稳的最高档就是它。

## 翻车二：bootm 把自己覆盖了

咱们准备好了内核 FIT，在 U-Boot 的 `=>` 提示符下把它读进内存、`bootm` 跳过去，听着是天经地义的。但第一版咱们把 kernel FIT 暂存到了 `0x02080000`，这正是内核自己的加载地址，结果 `bootm` 一边解压、一边往同一个地址写，自己把自己覆盖了，直接就崩了。

咱们换个不冲突的暂存地址就解决了：`0x04000000`。引导序列就成了这样：

```
=> mtd read boot 0x04000000 0 0xc00000
=> setenv bootargs 'earlycon=uart8250,mmio32,0xff0a0000 console=ttyS0,1500000'
=> bootm 0x04000000
```

咱们把 kernel FIT 从 boot 分区读到 `0x04000000`，设好了 bootargs 再 bootm。`0x04000000` 这个数后面会反复地出现，咱们要认准它就是避开 kernel load 区的暂存点。

## 翻车三：console “卡住”了，其实是波特率没带

内核好不容易起来了，`Starting kernel ...` 也打出来了，结果 earlycon 把控制权交接给真正的 ttyS0 console 之后，屏幕就没了动静，乍看像是内核卡死了，其实人家在好好跑，只是你看不见。

这是 RK 的 DW 8250 console 的一个通病：bootargs 里的 `console=ttyS0` 如果不跟波特率，console 接管之后用的波特率就不对了，输出就乱了。正解的要求是**必须带波特率**：`console=ttyS0,1500000`，上面那行 bootargs 里已经带上了。这样的翻车最磨人，咱们盯着一个“卡死”的串口排查半天内核，结果根因在 bootargs 漏了几个字符。

## 成功长这样

咱们爬完几次翻车，内核终于在板上起来了。下面这段是从内核 bringup 的定型 log 里截的，出处是 [boot-sdl-stage-end-of-kernel-uboot-202606151100](../../logs/boot-sdl-stage-end-of-kernel-uboot-202606151100.txt) 的原始记录，咱们一个字没合成：

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

每一行都值回了票价。`Starting kernel` 说明 U-Boot 把内核成功交下来了。`Linux version 7.0.12` 出的是主线内核，原厂的 6.1 已经退场了。最让人踏实的是 `Machine model: AES RK3506B Board` 这一行，内核认出了咱们亲手写的板级设备树。`earlycon` 和 `ttyS0 enabled` 说明 console 通了。最后的那段 `panic: Unable to mount root fs` 不是 bug，它其实是预期——咱们这一章压根没配 rootfs，它自然就挂不上根文件系统了。
