# Ch0 — 路线图：为什么是 RK3506，为什么 mainline-first

> 这是 rk-forge 教程的第一章。咱们在动手编译任何东西之前，“要去哪、为什么这么走”的路线要交代清楚。这一章咱们不敲一行命令，但它决定了后面每一章咱们看到的代码、遇上的毛病，还有最后板上亮起的那行 `rk3506 login:` 到底是怎么来的。

## 又一块 Rockchip？

咱们提到 Rockchip 的时候，绝大多数人的第一反应是 RK3588：八核、NPU、能跑桌面，Armbian 还给了一键刷机。比它再低一档的 RK3568，Collabora 和一票社区早就把它伺候明白了。这些热门芯片对咱们来说好做，生态也是现成的，不过成熟归成熟，一份从源码亲手把主线 Linux 跑起来、每一步为什么这么走都讲清楚的工程记录，仍然是空白的。

rk-forge 起步走的是 RK3506，一颗几乎没人理的、便宜又朴素的入门级 Rockchip SoC，主线 Linux 的版图上接近一片空白。做深不做宽、避开红海、去啃那道没人做的菜，这是项目最初的样子。后来咱们发现，RK3506 上垒起来的那一套（主线 U-Boot 加主线 kernel，加上有序补丁库、forge 编排器和诚实的差距报告），本身就是一套能复用的主线 bring-up 方法论，于是咱们又把它铺到了 RK3568 和 RK3588。RK3568 的 boot 已经在真正的板子上跑了起来，多路外设也过了板验，RK3588 已经跑到了 Ubuntu GNOME 桌面。所以这本书现在的形态是：起点放在了 RK3506，教程最完整的一块板也是它。RK3568 和 RK3588 承担的则是进阶场的角色，把同一套方法延伸到了 AArch64、异构、GPU/显示/媒体，去做那些更硬的课题。

不过有一条原则从头贯穿到尾，三块板全都走 mainline-first 的路线，咱们不偷懒去原厂 SDK 里抄现成答案，每一块都独立把从源码到板上跑通的证据链建起来。

所以咱们得把 rk-forge 是什么交代清楚。它不是又一个 Armbian 式的发行版，也做不了 Yocto 那一路的构建系统，更不是原厂 BSP 镜像的换皮，成品镜像它也是不卖的。它交付的是四件事：一份能按顺序打上去的补丁库（quilt 风格的 `series`，`git am` 落真实 commit、可 bisect、失败了就原子回滚），一份诚实的差距报告（[document/sdk-diff.md](../../sdk-diff.md) 逐子系统地把原厂有什么、主线有什么、差在哪、还能不能 boot 都列了出来），一个把 `setup → build → pack → assemble` 串成一个命令的 `forge.sh` 编排器，还有你现在读着的这本教程，它从空机器一步步把主线 Linux 带到了 UART。这四样东西是配套的。补丁复现得了、差距核对得了、构建一键就能跑、过程照着就能学，四样东西是咬合在一起的，缺了哪一样，主线移植这件事就少了一块拼图。

## 咱们手上这块板

这本书从头到尾的主角就一块板，也就是正点原子（ATK）出的那块 RK3506B 开发板，咱们要在它身上反复折腾。咱们管它叫“AES 板”，AES 是 Awesome Embedded Studio（咱们工作室）的缩写，给这块咱们亲手移植的上层 SDK 冠上自己的别名，顺便也避开了 ATK 这个正点原子的商标。它的样子朴素得很，也挺可爱的：CPU 是三个核的 32-bit ARM Cortex-A7，外加的还有一颗 M0 协处理器。板载的内存是 512MB DDR3，存储用的是 Winbond 的 W25N04KV，一颗 512MB 的 SPI-NAND。面板上有两个 RJ45 网口、一块 800×1280 的屏接口，WiFi 靠一个插在 USB 上的 RTL8733BU dongle。

开发机的配置不需要多豪华。笔者自己是在 WSL2（Ubuntu）里干完所有事的，WSL 只给了几个 G 内存，照样愉快地把活干完了。16GB 内存的规格是隔壁 RK3588 群的事，轮到 RK3506 这个量级的板子就用不到了。交叉工具链用的是 `arm-linux-gnueabihf`（Arm GNU Toolchain 15.2，当年的声明住在 `config/toolchain.conf` 里，那文件后来随 cce9f63 退役了，继任的是 [boards/aes/board.yaml](../../../boards/aes/board.yaml) 的 `toolchain:` 块，`forge` 编排器自动选用的还是它）。RK3506 的核是 Cortex-A7、带硬浮点，所以工具链后缀是 `hf`，⚠️ 千万别手滑装成 soft-float 的那个 `gcc-arm-linux-gnueabi`，不然咱们会在一个完全想不到的地方收获一堆链接错误。具体的环境检查咱们放到 [Ch1](01_toolchain.md) 再细讲，这里咱们只要记下一件事：一块 RK3506B 板子、一根串口线、一台装了 WSL2 的机器，就足够了。

## 启动链：链长什么样，哪里闭源、哪里开源

这一段是整本书的技术坐标系，咱们得把这段坐标系画清楚，后面所有的折腾才有了安放的地方。RK3506 从上电到咱们能在串口敲下回车，要经过的是这样一条链：

```
ROM(片上固化) → rkbin(TPL/SPL, 闭源) → U-Boot(主线, 开源) → Linux(主线, 开源) → rootfs → init
```

咱们把它当成一场接力赛来看。第一棒是芯片里烧死的 BootROM，它干不了什么大事，只负责把下一段的代码从 SPI-NAND 搬进内存、交棒。真正把内存点活的是第二棒的 rkbin。这里有个绕不开的硬现实：RK3506 的 DDR 初始化代码 Rockchip 没有开源，它就藏在 rkbin 的 TPL/SPL blob 里。在 BootROM 跳进来、任何开源代码都还没跑起来的那段时间里，DRAM 必须已经初始化好了，否则后面的一切都是空中楼阁。这也是为什么咱们在 [blobs.md](../../blobs.md) 里把这件事写得很死。rkbin 是当前唯一绕不开的闭源依赖，整个项目对 blob 的态度是“暂时用着、诚实记录、盯着消除路径”，而不是假装它不存在。

咱们可能会问：既然 U-Boot 都开源了，咱们自己写一段 DDR 初始化不就完了？咱们自己趟过一遍（内部叫方案 A），其实没走通。主线 U-Boot 里其实有 RK3506 的 SoC 级驱动，包括 sdram 初始化的框架，用它编出来的 loader 是能把 DDR 点起来的，串口打出了那行 `DDR d27ac532c4 ... fwver: v1.06`，证明 BootROM 加载了咱们的 idblock。但到了该由咱们自己的 SPL 出 banner 的地方，输出却变成了全波特率的乱码，SPL 在 DDR 之后的那一瞬间就崩了。RK3506 的 DDR init 之所以难自研，是因为它跑在整个链最前面的那段极早期（还没有 RAM、也还没有 C 运行时），全靠对 DDR PHY 寄存器的裸 poke 加一套私有的 training 算法，而这套参数 Rockchip 没给源码。偏偏这块板又没引出 JTAG，崩在 SPL 里咱们连一行打印都抓不到，只能一遍遍地改、烧、盯着满屏乱码猜。所以现状很诚实：咱们借原厂的 DDR/SPL/OP-TEE blob 把链跑通，自己的 SPL 那一段还在趟，这就是纯主线 boot 目前唯一卡住的地方。

rkbin 把 DDR 点亮、把环境搭好了之后，它就把接力棒交到了 U-Boot 手里，从这里往后就全是主线开源代码了。咱们用的 U-Boot 是主线 2026.07，Linux 用的是主线 7.1，rootfs 是 buildroot 出来的 busybox。整条链最关键的一点，是闭源与开源之间的分界线，它就画在 rkbin 之后的位置上。rkbin 之前咱们借的是原厂的 blob。过了 rkbin 这道分界（从 U-Boot 到 init），每一行的源码都能在主线仓库里翻到、能 `git bisect`、能打补丁。这也是为什么后面 Ch2 咱们会花一整章去和 rkbin 较劲：它就卡在链的咽喉上，咱们搞不定它，后面的一切全白搭。

> 这里咱们打个预防针：“纯主线 boot”目前是做不到的，卡点就在 rkbin 的这段 DDR init。自己写 SPL 去替代它的路（内部叫方案 A）还在趟，其实没走通。诚实的说法是，咱们的 U-Boot 和 kernel 是纯主线，但启动链最前段仍然借了原厂 blob。这个差距到底有多大、缺的是什么，咱们会在 [sdk-diff.md](../../sdk-diff.md) 里逐项量化、不藏着掖着。

## 一件很重要的事：主线已经准备好了

讲完了链的结构，接下来咱们要回答一个更关键的问题：整条路到底走不走得通？答案藏在 2026 年的几个事实里，每一条咱们都核实过，不是从道听途说来的。RK3506 的 pinctrl 和 clock 支持，是从 Linux 6.19 开始进的主线（Linus Walleij 那一拉）。但 6.19 已经 EOL 了，所以目标定在了更新的 7.1 上。U-Boot 那边倒是干脆，SoC 级别的支持（Jonas Karlson 的 v2 系列）已经整个合并进了主线 U-Boot，跟着 2026 版一起发了。

咱们把上面两条线索连起来，会得到一个对咱们非常有利的判断：对于咱们“用主线把 RK3506 启动起来”的目标，整个 RK-SDK 其实坍缩成了两样东西。一样是 rkbin 那颗绕不开的 DDR blob，另一样则是一块板级的设备树（`.dts`），上游主线有了 SoC 级的支持，却还没有对这块具体板子的描述。而这块板级 DT，恰恰是 rk-forge 要写、要贡献、要往上游推的东西。咱们是站在已经就绪的主线地基上，补上最后那块属于咱们这块板的拼图，而不是从零拼一堆补丁、强行去启动一颗没人管的芯片。它比咱们想象中可行，也比那些热门芯片的同质化活计有意思得多。

## 为什么是 mainline-first，不是 BSP

ATK 不是给了 BSP 吗（那套就停在 linux 6.1.118），为什么放着现成的不用，非要去啃主线？因为主线是可持续、可上游、可教、可 bisect 的，而 BSP 意味着过期、停更、黑盒。ATK 的 6.1.118 在它出货那天是新的，但主线已经走到了 7.1，后来的那些安全补丁、驱动修复、新特性，BSP 一辈子也吃不到了。更要命的是，BSP 里往往混着一堆原厂的私有改动，咱们既没法把它拿到上游去，也没法在出问题的时候干净地二分定位。咱们的态度很明确：主线是主线、BSP 是 Phase 4 的安全网，真到了主线某一条路走不通、需要兜底的时候咱们再去翻它，而不是一上来就把整个项目拴在原厂的旧版本上。

举一个咱们真实遇过的例子。原厂的 U-Boot 是从 2017 版 fork 出来的，它读 FIT 镜像的那套代码和主线完全是两回事。咱们最早把主线 U-Boot 往里装的时候，原厂的 SPL 死活不肯加载咱们的镜像，串口甩了一句 `Unsupported hash algorithm`。表面看像是 hash 算法的事，可顺着原厂的 `fit_nodes.sh` 一翻，人家自己用的也是 sha256，真因其实是原厂 fork 的 FIT 节点结构，和主线 binman 生成的对不上。这类 bug 把咱们困在了原厂的私有 fork 里：主线的 git 历史帮不上忙，原厂那套 FIT 打包逻辑其实压根没进过主线。咱们想 bisect 也进不去，因为那是 Rockchip 没开源的 2017 fork。最后咱们靠 `dumpimage` 把原厂镜像的 FIT 结构逆向出来、照着复刻，才算解决了（后来那一坨原厂 mkimage，也被咱们用纯 Python 的 [scripts/fit-pack.py](../../../src/forge/tools/fit_pack.py) 替掉了，字节级复刻它认的 `-E` 外部布局，详见后面 forge 那一章的正文）。而换成主线 U-Boot，同样的链路就透明可读了，每一步咱们都能在源码里追、能 `git blame`、能动手改。所以 mainline-first 带来的不是情怀，它换来的是出问题时咱们手里真有工具。

## 这本书怎么走

“为什么”讲完了，咱们再把怎么走交代清楚，心里也就有了一张地图。Ch1 讲的是工具链，负责把 `arm-linux-gnueabihf` 和 host 的环境理顺，这是后面所有编译的前提。Ch2 讲的是 U-Boot 和 rkbin，咱们会和那个闭源 blob 正面交锋，咱们用 binman 把启动镜像打包出来、烧进板子，亲眼看着 U-Boot 的 banner 从串口里蹦出来。Ch3 讲的是内核：在已经就绪的主线 SoC 支持上，加上咱们这块板的设备树、一路解码 bootlog，直到 earlycon 亮了、shell 也出来。

每一章的结尾，咱们都会贴一段真实的 UART 抓取，让你看到“成功长这样”的原文长什么样、一个字都不合成。不过咱们得提前交个底：全程咱们走得不算顺，RK3506 的整条链，咱们是一路翻着车过来的。rkbin 的 SPL 背后藏着三条不能违背的隐性约定。SPI-NAND 的读写加上 loader 写弱 rootfs，演成了一整部连续剧。有一阵子咱们的板子一写就 external abort，翻了半天才发现，是 reserved-memory 忘了给 OP-TEE 留对。还剩 USB 的 PHY 要调，WiFi 的 out-of-tree 驱动要移植。这些翻车咱们全都老老实实记在了 [document/pitfalls/](../../pitfalls/) 的七篇日记里，每一条都挂着对应的串口原文。翻车其实不算失败，更像是给咱们指路的路标。咱们在这本书里看到的每一段“咱们为什么这么改”，背后多半都挂着一次把咱们按在地上摩擦的教训。

## 成功长这样

说了这么多，最后咱们看一眼整条路走到头是什么样。下面这段是从咱们最近一次全链板上验证的串口日志里截出来的（[boot-sdl-2026-06211109](../../logs/boot-sdl-2026-06211109.txt)），咱们一个字都没合成：

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

咱们注意看整条链的每一个环节是怎么交接的：rkbin 的 DDR init 把 512MB 内存点亮，然后交到主线 U-Boot 2026.07 的手上，hash 校验也全过了。接着 U-Boot 自动从 SD 卡把 kernel 拉了起来——

```
Hit any key to stop autoboot: 0
MMC read: dev # 0, block # 16384, count 20480 ... 20480 blocks read: OK
## Loading kernel from FIT Image at 04000000 ...
Starting kernel ...

Linux version 7.1.0-00016-gbded0f841093 ... #1 SMP Sat Jun 20 19:20:53 CST 2026
Machine model: AES RK3506B Board
```

主线 7.1 的内核起来了，认出了咱们写的板级 DT（`AES RK3506B Board`），三核 SMP 也全部就位了。到了最后，rootfs 挂上了，init 也跑了起来：

```
EXT4-fs (mmcblk0p3): mounted filesystem ... r/w with ordered data mode.
VFS: Mounted root (ext4 filesystem) on device 179:3.
Run /sbin/init as init process
...
Welcome to rk-forge buildroot
rk3506 login: root
```

`rk3506 login:`——等你读完这本书，咱们手上的板子，能从一根空的 SPI-NAND（或一张 SD 卡）一路跑到这一行。全程咱们已经替你探过一遍了，现在换咱们带你走。给板子拍张照不过分，然后咱们 [Ch1](01_toolchain.md) 见。
