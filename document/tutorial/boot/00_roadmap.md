# Ch0 — 路线图：为什么是 RK3506，为什么 mainline-first

> 这是 rk-forge 教程的第一章。在动手编译任何东西之前，我们先把"要去哪、为什么这么走"讲清楚。这一章不敲一行命令，但它会决定后面每一章你看到的代码、踩到的坑、还有最后板上亮起的那行 `rk3506 login:` 到底是怎么来的。

## 前言：又是一块 Rockchip？

说实话，提到 Rockchip，绝大多数人的第一反应是 RK3588——八核、NPU、能跑桌面、Armbian 一键刷机。再往下是 RK3568，Collabora 和一票社区早就把它伺候得明明白白。这些热门芯片有一个共同点：好做，而且早就被做烂了。你今天再去给 RK3588 写一份"如何启动主线"，大概率是在重复造一个没几个人会看的轮子。

我们偏不走这条路。rk-forge 服务的是 RK3506——一颗几乎没人理的入门级 Rockchip SoC。它便宜、它朴素，国内开发板圈子里有一块 ATK 的板子在卖，但在主线 Linux 的版图上，它接近一片空白。做深不做宽，避开红海，去啃那道没人做的菜——这就是这个项目最初的样子。

所以你得先理解一件事：rk-forge 不是又一个 Armbian，不是 Yocto，不是厂商 BSP 镜像。它不卖成品饭。它卖的是三样东西——一份能按顺序打上去的补丁库，一份诚实地告诉你"主线到底还差什么"的差距报告，还有一本像你现在读着的这样、从空机器一步步带你把最新主线 Linux 跑到 UART 的书。如果非要打个比方。。。嗯：别人端上来的是一盘做好的菜，而我们把菜谱、灶台、还有一本陪你做饭的手册一起递给你，专门做那道没人做的菜。我也一直坚持认为：很多事情最好掰开来仔细看看，能减少不少问题——笔者混的隔壁RK3588的群亦是如此。

## 我们手上这块板

这本书从头到尾，你会在一块具体的板上反复折腾：RK3506B，正点原子（ATK）出的那块开发板。我们管它叫"AES 板"——AES 是 Awesome Embedded Studio（我们工作室）的缩写，给这块我们亲手移植的上层SDK冠上自己的别名。它朴素得很可爱——一颗 32-bit 的 ARM Cortex-A7，三个核，外加一个 M0 协处理器；板载 512MB DDR3，存储是一颗 Winbond 的 SPI-NAND（W25N04KV，512MB）；面板上有两个 RJ45 网口、一块 800×1280 的屏接口，WiFi 则靠一个插在 USB 上的 RTL8733BU dongle。

你的开发机不需要多豪华。笔者现在都记得——啊，你的编译机需要16GB内存等等。额，其实最好要（小声逼逼，骗部门经费的还是要），不过小声的说——您完全不需要那样做。笔者的WSL就给了几个G。照样愉快的开发。

我自己是在 WSL2（Ubuntu）里干完所有事的，交叉工具链用的是 `arm-linux-gnueabihf`（Arm GNU Toolchain 15.2）。RK3506 是 Cortex-A7、带硬浮点，所以工具链后缀是 `hf`——千万别手滑装成 soft-float 的那个 `gcc-arm-linux-gnueabi`，不然你会在一个完全想不到的地方收获一堆链接错误。具体的环境检查我们放到 [Ch1](01_toolchain.md) 再细讲，这里你只要记住：一块 RK3506B 板子、一根串口线、一台装了 WSL2 的机器，足够了。

## 启动链：这条链长什么样，哪里闭源、哪里开源

这一段是整本书的技术坐标系，我们先把它画清楚，后面所有的折腾才有处安放。

RK3506 从上电到你能在串口敲下回车，要经过这样一条链：

```
ROM(片上固化) → rkbin(TPL/SPL, 闭源) → U-Boot(主线, 开源) → Linux(主线, 开源) → rootfs → init
```

你可以把它想成一场接力赛。第一棒是芯片里烧死的 BootROM，它干不了什么大事，只负责把下一段代码从 SPI-NAND 搬进内存、交棒。真正把内存"点活"的，是第二棒——rkbin。这里有个绕不开的硬现实：RK3506 的 DDR 初始化代码，Rockchip 没开源，它就藏在 rkbin 的 TPL/SPL blob 里。在 BootROM 跳进来、任何开源代码还没跑起来之前，必须先把 DRAM 初始化好，否则后面一切都是空中楼阁。这也是为什么 [blobs.md](../../blobs.md) 里我们把这条写得很死：rkbin 是当前唯一绕不开的闭源依赖，整个项目对 blob 的态度是"先用着、诚实记录、盯着消除路径"，而不是假装它不存在。

你可能会问：既然 U-Boot 都开源了，我们自己写一段 DDR 初始化不就完了？这条路我们趟过，内部叫方案 A，而且目前没走通。主线 U-Boot 里其实有 RK3506 的 SoC 级驱动，包括 sdram 初始化的框架，我们用它编出来的 loader，DDR 确实被点起来了——串口能打出 `DDR d27ac532c4 ... fwver: v1.06`，证明 BootROM 加载了我们的 idblock。但紧接着该由我们自己的 SPL 出 banner 的地方，输出变成了全波特率的乱码，SPL 在 DDR 之后那一瞬间就崩了。RK3506 的 DDR init 之所以难自研，是因为它跑在整个链最前面那段"还没有 RAM、还没有 C 运行时"的极早期，全靠对 DDR PHY 寄存器的裸 poke 加一套私有 training 算法，而这套参数 Rockchip 没给源码。偏偏这块板又没引出 JTAG，崩在 SPL 里你连一行打印都抓不到，只能一遍遍改、烧、盯着满屏乱码猜。所以现状很诚实：我们借 vendor 的 DDR/SPL/OP-TEE blob 把链跑通，自己的 SPL 那一段还在趟——这就是"纯主线 boot"目前唯一卡住的地方。当然，笔者也不太敢挑战，怕被送律师函。

等 rkbin 把 DDR 点亮、把环境搭好，它就把接力棒交到 U-Boot 手里——从这里开始，后面全是主线开源代码了。我们用的 U-Boot 是主线 2026.07，Linux 是主线 7.1，rootfs 是 buildroot 出的 busybox。这条链最关键的一点，是那条闭源与开源的分界线：它就画在 rkbin 之后。rkbin 之前，我们借厂商的 blob；rkbin 之后，从 U-Boot 到 init，每一行都能在主线仓库里翻到源码、能 `git bisect`、能打补丁。这也是为什么后面 Ch2 我们会花一整章去和 rkbin 较劲——它就卡在链的咽喉上，搞不定它，后面全白搭。

> 这里先给你打个预防针：所谓"纯主线 boot"，目前还做不到，卡点就在 rkbin 这段 DDR init。自己写 SPL 去替代它（我们内部叫方案 A）这条路还在趟，没成。所以诚实的说法是——我们的 U-Boot 和 kernel 是纯主线，但启动链最前段仍然借了厂商 blob。这个差距到底有多大、还差什么，我们会在 [sdk-diff.md](../../sdk-diff.md) 里逐项量化给你看，不藏着。

## 一件很重要的事：主线已经准备好了

讲完了链的结构，接下来要回答一个更关键的问题——这条路到底走不走得通？答案藏在 2026 年的几个事实里，每一条我们都核实过，不是道听途说。

RK3506 的 pinctrl 和 clock 支持，是从 Linux 6.19 开始进的主线（Linus Walleij 那一拉）。但 6.19 已经 EOL 了，所以我们把目标钉在更新的 7.1 上。U-Boot 那边更干脆，SoC 级别的支持（Jonas Karlman 的 v2 系列）已经整个合并进了主线 U-Boot，跟着 2026 版一起发了。

把这两件事连起来，你会得出一个对我们极其有利的结论：对于"用主线把 RK3506 启动起来"这件事，整个 RK-SDK 其实坍缩成了两样东西。第一样是 rkbin，那个绕不开的 DDR blob；第二样，是一块板级设备树（`.dts`）——因为上游主线有了 SoC 的支持，却还没有这块具体板子的描述。而这块板级 DT，恰恰是 rk-forge 要写、要贡献、要往上游推的东西。换句话说，我们不是在从零拼一堆补丁去强行启动一颗没人管的芯片，而是在已经就绪的主线地基上，补上最后那块属于我们这块板的拼图。这比想象中可行，也比那些热门芯片的同质化活计有意思得多。

## 为什么是 mainline-first，不是 BSP

你可能要问：厂商不是给了 BSP 吗（ATK 那套就停在 linux 6.1.118），为什么放着现成的不用，非要去啃主线？

因为主线意味着可持续、可上游、可教、可 bisect；而 BSP 意味着过期、锁死、黑盒。厂商的 6.1.118 在它出货那天是新的，但主线已经走到了 7.1，那些安全补丁、驱动修复、新特性，BSP 一辈子都吃不到。更要命的是，BSP 里往往混着一堆厂商私有改动，你既没法把它拿到上游去，也没法在出问题时干净地二分定位。我们的态度很明确：主线是主线，BSP 是 Phase 4 的安全网——真到了主线某条路走不通、需要兜底的时候再去翻它，而不是一上来就把整个项目焊死在厂商的旧版本上。

举个我们真实撞过的例子。vendor 的 U-Boot 是从 2017 版 fork 出来的，它读 FIT 镜像的那套代码和主线完全是两回事。我们最早把主线 U-Boot 往里装时，vendor 的 SPL 死活不肯加载我们的镜像，串口甩一句 `Unsupported hash algorithm`——表面看像是 hash 算法的事，可顺着 vendor 的 `fit_nodes.sh` 一翻，人家自己也用 sha256，真因是 vendor fork 的 FIT 节点结构和主线 binman 生成的对不上。这种 bug，你被困在 vendor 的私有 fork 里：主线的 git 历史帮不上忙，因为主线压根没有 vendor 那套 FIT 打包逻辑；你也 bisect 不进去，因为那是 Rockchip 没开源的 2017 fork。最后是靠 `dumpimage` 把 vendor 镜像的 FIT 结构逆向出来、照着复刻才解决的。换成主线 U-Boot，同样的链路是透明可读的，每一步都能在源码里追、能 `git blame`、能动手改。所以 mainline-first 的收益不是情怀，是出问题时你手里真有工具。

## 这本书怎么走

讲完了"为什么"，我们把"怎么走"也交代清楚，让你心里先有张地图。

Ch1 是工具链，把 `arm-linux-gnueabihf` 和 host 环境理顺，这是后面所有编译的前提。Ch2 是 U-Boot 和 rkbin——我们会和那个闭源 blob 正面交锋，用 binman 把启动镜像打包出来，烧到板上，亲眼看着 U-Boot 的 banner 从串口里蹦出来。Ch3 是内核：在已经就绪的主线 SoC 支持上，加上我们这块板的设备树，一路解码 bootlog，直到 earlycon 亮起、shell 出现。

每一章的结尾，我们都会贴一段真实的 UART 抓取——"成功长这样"长什么样，绝不合成。但我也得提前跟你交个底：这条路不是一路顺风的。RK3506 这条链，我们踩了一路坑。rkbin 的 SPL 背后藏着三个不可违背的隐性契约；SPI-NAND 的读写加上 loader 写弱 rootfs，演成了一整部 saga；有一阵子板子一写就 external abort，翻了半天才发现是 reserved-memory 没给 OP-TEE 留对；USB 要调 PHY，WiFi 要移植 out-of-tree 驱动……这些坑，我们全都老老实实记在了 [document/pitfalls/](../../pitfalls/) 的七篇踩坑日记里，每一条都挂着对应的串口原文。

踩坑不是失败，是路标。你在这本书里看到的每一段"我们为什么这么改"，背后多半都挂着一个曾经把我们按在地上摩擦的坑。

## 成功长这样

说了这么多，最后给你看一眼这条路走到头是什么样。下面这段，是从我们最近一次全链板上验证的串口日志里截出来的（[boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)），没有合成一个字：

```
DDR d27ac532c4 typ 25/03/11-14:46:28,fwver: v1.06
...
DDR3, 750MHz
BW=16 Col=10 Bk=8 CS0 Row=15 CS=1 Size=512MB

U-Boot SPL 2017.09-g80d18cf0259-250930 ... fwver: v1.12
## Checking uboot 0x00800000 ... sha256(90347127d8...) + OK

U-Boot 2026.07-rc4-g7e23760a5650 (Jun 21 2026 - 02:50:05 +0000)
Model: Rockchip RK3506 Evaluation Board (ATK RK3506B)
DRAM:  512 MiB
```

注意看这条链的每一个环节是怎么交接的：rkbin 的 DDR init 先把 512MB 内存点亮，然后交棒给主线 U-Boot 2026.07，hash 校验一路绿灯。接着 U-Boot 自动从 SD 卡把 kernel 拉起来——

```
Hit any key to stop autoboot: 0
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...

Linux version 7.1.0-00016-gbded0f841093 ... #1 SMP Sat Jun 20 19:20:53 CST 2026
Machine model: AES RK3506B Board
```

主线 7.1 的内核起来了，认出了我们写的板级 DT（`AES RK3506B Board`），三核 SMP 全部就位。最后，rootfs 挂上、init 跑起来：

```
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w with ordered data mode.
VFS: Mounted root (ext4 filesystem) on device 179:3.
Run /sbin/init as init process
...
Welcome to rk-forge buildroot
rk3506 login: root
```

`rk3506 login:`——读完这本书，你手上的板子，能从一根空 SPI-NAND（或一张 SD 卡）一路跑到这一行。这条路我们走过一遍了，现在轮到带你走。给板子拍张照不过分，然后我们 [Ch1](01_toolchain.md) 见。
