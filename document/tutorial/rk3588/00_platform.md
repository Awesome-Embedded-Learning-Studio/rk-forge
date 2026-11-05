# 平台与启动链：RK3588，以及拔掉原厂 SDK 之后会断在哪里

> 这一卷的主角是迅为 iTOP-RK3588 EVB（topeet，咱们手上这块是 eMMC 版），它装着一颗 Rockchip 的高端 SoC。咱们给它配上主线 U-Boot 和主线 Linux，然后咱们一路跑到 Ubuntu GNOME 桌面。RK3588 的主线支持很成熟，所以难处换了形态：主线里该有的其实都有，真正的考验在咱们把 Rockchip 官方 SDK 那一套整个拔掉、换上主线源码重走一遍的时候，那时咱们才要看清哪些接缝和时序会让板子起不来，这才是要一章章排查的事。有两个词咱们得约好：主线（mainline）指 U-Boot、Linux 这些上游社区的官方仓库，原厂 SDK 指 Rockchip 官方发行的整套板级支持包（BSP），里面是魔改过的 U-Boot、内核和一套私有打包工具。这一章把这颗 SoC 和它的启动链全图铺开，后面九章咱们都照着它干活。

## 难处换了形态

RK3588 的主线驱动覆盖好得惊人：pinctrl、clock、GMAC 以太网、eMMC、VOP2 显示控制器、Panthor GPU 驱动、Hantro/rkvdec2 视频编解码、rkisp1 摄像头，甚至 NPU 的 Rocket 驱动，咱们在主线里全都能找到。这背后主要是 Collabora 的投入，那是一家长期给 Rockchip 平台做主线化的咨询公司，RK3588 是 Collabora 投入最重的旗舰。不过的话，咱们只看“有没有驱动”，会觉得这块板是最好做的。

如果是真的，那也便好（你猜我怎么哭了）

咱们真做下来，最磨人的几段其实没有一段是缺驱动。当初启动链上有一场**没有任何报错的 bootloop**（上电、复位、再上电的无限循环），根因藏在两个闭源固件的版本约定里。机制本章后面讲清楚，完整排查下一章展开。关于这个，我们卖个关子，留到下一章慢慢说。

LCD算是板子的可视化门面，也被折腾的够呛：咱们迭代了多轮镜像才出图，断点在 DSI 桥片的初始化时序，以及 VOP2 把像素时钟交给屏端的那次交接。GPU 明明有主线 Panthor 驱动，却因为固件加载时机不对，probe（内核为驱动分配设备的探测流程）始终失败，最后把固件内建进内核才解决。

咱们把这一卷的课题概括成：**主线其实都有、集成与时机才是战场**。“刷个 Armbian 就能跑”这件事其实看着轻巧，咱们要练的是从源码亲手把每一级启动链换上主线、并且知道哪里会断的功夫，所以这本教程写的是后者。

## 这颗 SoC，这块板

咱们从硬件认起。规格以迅为官方手册为准、板上数字以咱们自己的启动日志为准，两边对得上的才写成事实。

| 项目 | 规格                                                                                  | 出处                                                   |
| ---- | ------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| SoC  | Rockchip RK3588，8nm 工艺                                                             | 官方硬件指导手册 v1.2                                  |
| CPU  | 四核 Cortex-A76 + 四核 Cortex-A55，big.LITTLE（大小核架构），A76 主频 2.4GHz          | 同上                                                   |
| GPU  | Mali-G610 MP4，OpenGL ES 3.2 / Vulkan 1.2 / OpenCL 2.2                                | 同上                                                   |
| NPU  | 6 TOPS，INT4/INT8/INT16/FP16/BF16/TF32 混合运算                                       | 同上                                                   |
| VPU  | 8K@60fps 解码，硬件视频编解码器                                                       | 同上                                                   |
| 内存 | SoC 兼容 LPDDR4/4X/5。本板实测 LPDDR4X 2112MHz，4 通道各 4096MB，共 16GiB             | 手册标核心板基线 4GB，本板配置以启动日志为准           |
| 存储 | 本板实测 eMMC 116GiB（内核报 `METORA`），HS400 Enhanced Strobe（eMMC 的高速传输档位） | 本板启动日志                                           |
| 板   | 迅为 iTOP-RK3588 EVB（topeet，eMMC 版），仓库代号 `rk3588-topeet`                     | [board.yaml](../../../boards/rk3588-topeet/board.yaml) |

大小核的实测拓扑咱们在内核日志里看得一清二楚：`Brought up 1 node, 8 CPUs`，各簇的启动日志咱们对过，CPU 0-3 其实是 A55、CPU 4-7 是 A76。这颗 SoC 的中断控制器是带 ITS 的 GICv3，ITS 把设备中断直接投递到对应的 CPU 核，日志里 `GICv3: GICD_CTLR.DS=0, SCR_EL3.FIQ=1` 那行就是它在报配置、咱们查中断时对着它看就行。咱们在这颗 SoC 上除了 CPU 还能看到 NPU（神经网络加速器）、VPU 这些异构算力单元，它们的驱动状态差异其实很大，咱们到章末（这块板现在到哪一步了）再逐项交代。

笔者板子上有这些外设，大伙看个乐子就好了

| 外设     | 型号 / 接法                                                             |
| -------- | ----------------------------------------------------------------------- |
| 电源管理 | PMIC（电源管理芯片）RK806，走 SPI，大小核与 NPU 核压由 rk8602/rk8603 管 |
| 有线网   | GMAC0，RGMII，PHY（物理层收发器）是 RTL8211F                            |
| USB      | USB2 host ×2，WiFi/BT 另共用一组 USB2.0                                 |
| 显示     | 10.1 寸 1024×600 屏，MIPI DSI 接口经 TC358775 桥片转成 LVDS 接屏        |
| 触摸     | GT911，挂 I2C2                                                          |
| WiFi/BT  | RTL8723DU，USB combo 芯片（免设备树节点）                               |
| 调试串口 | UART2，基址 `0xfeb50000`，全链 115200                                   |

调试串口咱们多说两句，后面全卷咱们都得靠它。Rockchip 上游默认是 1500000 波特率这件事咱们得知道，这块板调试时咱们把三处统一过：DDR 固件的波特率咱们用 `ddrbin_tool` 改，U-Boot 的 `CONFIG_BAUDRATE` 咱们用补丁改，内核侧控制台咱们走 `ttyFIQ0`（从 SDK 内核移植过来的 FIQ 调试控制台，挂在快速中断上、内核恐慌时咱们也抢得到打印通道），三处咱们都定到 115200。三处配置咱们要一起改、漏一处对应阶段就给咱们满屏乱码，咱们就真漏过一次、当时 U-Boot 阶段的输出全成了乱码，这个教训咱们下一章讲 U-Boot 时再展开。

手册对烧写和救砖用的两个下载模式给过官方说法，咱们照着记：咱们按住 vol+ 再上电、让板子进 **Loader 模式**，这时候 bootloader 还能响应、咱们可以单烧分区，调试时咱们省心不少。咱们按住 BOOT 键再上电、让板子进 **MaskRom 模式**，走的是最底层（BootROM）的裸下载，存储里没有合法镜像时咱们也进得来，板子刷坏了咱们也得靠它救回来。咱们烧写用的工具是 rockusb（Rockchip 的 USB 下载协议），它走的就是 Loader 模式这一层。

## 主线都有，和"能起来"之间隔着三层

RK3588 在主线是 Collabora 投入最重的旗舰，SoC 级的描述和驱动其实全在树里，可主线有驱动和这块板能起来之间却隔着好几层、每一层咱们都可能栽在上面：

1. **启动前段仍然是闭源的**。DDR 初始化和 BL31（ARM Trusted Firmware 里常驻最高特权级的那部分，负责安全世界和电源管理服务，下文详述）在 RK 平台上没有源码，只能用 rkbin 仓库里的预编译固件。这两个固件之间还有版本约定要守——正是本章后面那场 bootloop 的根源。
2. **板级设备树还是要自己写**。主线有的是 SoC 级 dtsi 和 EVB 参考板的 dts（dtsi 描述 SoC 本身的硬件，dts 描述具体某块板），topeet 这块板的主线描述得从 SDK 的 5.10 设备树移植过来，产出 `rk3588-topeet.dts`——这份板级描述的移植是内核一章的主要工作。
3. **主线有驱动不等于主线行为和原厂 SDK 一致**。最典型的两处：GPU，原厂 SDK 用 Arm 私有的 mali_kbase 驱动，主线用 Panthor，不是同一个驱动，特性和调优未必对齐。RGA（2D 图形加速器）起初咱们以为主线没有驱动，后来在 7.3.1 的匹配表里找到了 RGA2/3，NPU 章把它的双核点亮了，咱们当初的判断是过期的。

咱们仓库里的两组补丁，其实对应的就是上面说的差距：linux 在册二十七发、patches/uboot 十发，它们其实全是把这块板接到主线的接线活儿，咱们没有一个是拿去给主线补缺驱动的。

## 启动链全图：从 BootROM 到 systemd

这是整卷的技术坐标系。RK3588 从上电到 GNOME 桌面这一路要走的链，咱们得一级一级看清楚。

上电后第一个动身的其实是 BootROM，它是片内固化的一段代码、咱们谁都改不了，所以它只能按固定的媒体顺序去找，结果从 eMMC 扇区 `0x40` 里把 idbloader.img（binman 打包的）搬进了片内内存。咱们把这颗镜像分成两半看，其实里头装着两级：

- **TPL**，rkbin 的 DDR 固件、负责 DRAM 训练。他会调整底层的 RAM 芯片的工作频率等等。说白了就是让 RAM 干活干的痛快来，不是别别扭扭的怀疑是不是片子出问题了性能这叼差。
- **SPL**，主线 U-Boot 编出来的那颗，当二级加载器使，管从 eMMC 把 u-boot.itb 读进来、验完完整性再往下交棒，下一节咱们细看它

接下来其实轮到 SPL 接棒，咱们看它从 uboot 分区（扇区 `0x4000`）读出 u-boot.itb、对里面每个节点验 sha256。咱们再把 u-boot.itb 打开数一数，其实里头装着三样：

- **BL31/ATF**，rkbin 固件、落在 `0x00060000`、常驻 EL3
- **u-boot proper**，落在 `0x00800000`
- **fdt**，设备树

其实三样里头 BL31 第一个跑起来，咱们看它上来就把中断控制器备好，然后降到非安全世界、把控制权交到 u-boot proper 手里了。主线 U-Boot（2026.07-rc4、pin `5ca1a73c`）走 bootflow 扫到 rootfs 分区上的 `/boot/boot.scr`，这个脚本把 boot 分区里的 kernel FIT 裸读到 `0x08000000`，咱们接着看 bootm 把控制权交给内核。咱们看主线 Linux 带着 `root=/dev/mmcblk0p3` 把 ext4 根文件系统挂起来，然后咱们看到 systemd 接手、GNOME 给咱们亮屏，到这里咱们整条链就算跑通了。

咱们把整条链当接力赛看，每一棒的职责、加载地址、开源还是闭源这几点，咱们都值得一级级讲。

### 第一棒 BootROM：只会一件事

咱们动不了芯片出厂时就烧死在片内 ROM 里的那段代码，咱们只能顺着它的规范来。上电那一刻 DRAM 对咱们来说还不可用，所以它只会按固定的媒体顺序去找一个合法的 **idblock**，那是 Rockchip 私有的镜像格式，头部带芯片标签和校验这套约定咱们得对上，BootROM 只认这个格式、所以咱们造镜像也得照着格式来。咱们这块板是 eMMC 排在第一位（板配置的 parameter 分区表注释里写明了这个顺序），所以它从 eMMC 扇区 `0x40` 开始，第一段启动代码就由它搬进片内 SRAM、咱们链的第一跳有了落点。咱们要注意 `0x40` 是裸扇区偏移、不占 GPT 分区表项。存储里没有它认得的镜像、或者咱们按住了 BOOT 键，所以它就落到 USB 下载模式、等主机来喂下一棒，上一节咱们碰到的 MaskRom 模式就是这么来的。

### 第二棒 idbloader.img：DDR 训练 + 主线 SPL

idbloader.img 其实是 binman 拼出来的两级镜像，拼装格式是 Rockchip 私有的 idblock，在文件系统里咱们找不到它。binman 是 U-Boot 官方的镜像打包工具，用一份描述文件声明镜像里各段二进制的布局，产出咱们可以直接裸写到存储上的镜像。

咱们把镜像分成两半看：前半是 **TPL**，U-Boot 术语里排在 SPL 前面的第一级，落到这块板上就是 rkbin 的 DDR 固件（版本 v1.21）。咱们看它一上来就要面对“还没有内存、还没有 C 运行时”的极早期，对 DDR PHY 做裸寄存器操作这套活儿咱们都看在眼里，外加一整套咱们拿不到源码的私有训练算法，最终替咱们把 4 通道 LPDDR4X 点到了 2112MHz。串口开场那几行就是它给咱们打的：

```
DDR ... fwver: v1.21
LPDDR4X, 2112MHz
channel[0] BW=16 Col=10 Bk=8 CS0 Row=17 CS1 Row=17 CS=2 Die BW=16 Size=4096MB
channel[1] ... channel[2] ... channel[3] ...
```

省略号的地方其实是 channel[1] 到 channel[3]，四通道各 4096MB 的同构输出咱们就不整段贴了。为什么这一段咱们要借闭源？Rockchip 没把 DDR 训练的参数和算法的源码给咱们，而它偏偏跑在整个链最前面、崩了连一行打印都抓不到的地方。咱们绕不开这一点：这是 RK 平台的硬现实，咱们仓库里的三块板在这点上一个样。

咱们看镜像后半的 **SPL**，全称其实是 Second Program Loader。它排的是 U-Boot 装载流程里的第一级，负责把真正的 U-Boot 本体装进内存并校验。在链上咱们拿到的就是主线编出来的 `u-boot-spl.bin`。咱们拿到的这个主线 SPL，其实不是理所当然的起步选择：起步用的是原厂的 SPL，也就是 Rockchip 拿自家 2017.09 的老 U-Boot 编出来的那颗 `rk3588_spl`，至于咱们当初为什么非换它不可，原因咱们到本章讲版本约定的地方细说。SPL 起来后咱们看它从 uboot 分区把 `u-boot.itb` 整个读进来，起点是扇区 `0x4000`（对应主线 U-Boot 的 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR`），接着咱们看它对 FIT 里每个节点验 sha256，FIT 是一种镜像容器格式、下一节咱们再细看它的结构，等咱们确认全过、它才继续往下装载：

```
## Checking hash(es) for Image atf-1 ... sha256+ OK
## Checking hash(es) for Image u-boot ... sha256+ OK
## Checking hash(es) for Image fdt-1  ... sha256+ OK
## Checking hash(es) for Image atf-2 ... sha256+ OK
## Checking hash(es) for Image atf-3 ... sha256+ OK
```

### 第三棒 u-boot.itb：BL31 常驻 EL3

这一棒也是 binman 给咱们打好的镜像，容器是 FIT（一种把多个镜像和设备树按配置打包的容器格式、也是 U-Boot 生态的标准），咱们用 dumpimage（FIT 配套的解包工具）解开看结构：

```
Image 0 (u-boot):  Load 0x00800000  Entry 0x00800000  (818288 B)
Image 1 (atf-1):   Load 0x00060000                     (149020 B)  ← BL31 v1.54
Image 2 (atf-2):   Load 0x000f0000                     (24576 B)
Image 3 (atf-3):   Load 0xff100000                     (36864 B)
+ fdt-1 (u-boot.dtb, 203520 B)
```

atf-1 就是 rkbin 的 BL31（`rk3588_bl31_v1.54.elf`）。ATF 指的是 ARM Trusted Firmware，那是 ARM 官方的安全固件框架，BL31 就是其中常驻 EL3 的运行时部分。EL3 是 ARMv8 架构里的最高特权异常级、比操作系统还要高一层，安全世界切换和底层电源管理这些事都归它监管、咱们后面到处会碰到它。咱们看 BL31 起来之后把中断控制器初始化好、然后降权到非安全世界、把入口交到 `0x00800000` 的 U-Boot 本体：

```
NOTICE:  BL31: v2.3 ... fwver: v1.54
INFO:    GICv3 without legacy support detected.
INFO:    ARM GICv3 driver initialized in EL3
INFO:    Entry point address = 0x800000
INFO:    SPSR = 0x3c9
```

这颗 BL31 是整条链里活得最久的成员：从上电一直常驻到关机。内核的 PSCI 调用（ARM 标准的电源管理接口，开核、CPU 休眠、调频都走它）咱们看到的每一次调用，其实都靠 SMC 指令陷进 EL3 由它处理，咱们到外设那章做 cpufreq 调频时会再次感到它的存在。atf-2/atf-3 是这个 FIT 布局里的另两个 ATF 槽位，验签也随布局一起走、咱们 dump 出来就能看到它们。咱们再认识一下 OP-TEE（Open Portable Trusted Execution Environment，跑安全应用的可信执行环境、也就是 BL32），咱们在链里把它**省略**了：rkbin 的 bl32 是裸 .bin 文件、binman 的 tee-os 节点要的却是 ELF，而且不跑安全应用时它对启动到桌面不是必需件。

### 第四棒 U-Boot 本体与内核：boot.scr 的接力

咱们看主线 U-Boot 2026.07-rc4 起来后停在 `Hit any key to stop autoboot`，超时后走 bootflow（U-Boot 的自动启动流程，依次在各个存储设备上尝试可启动的镜像）。这里有个这块板特有的机关：boot 分区是**裸分区**、kernel FIT 整个写进去、不落文件系统，所以 bootflow 的文件系统类启动方法没法当文件去读它。解法是让 bootflow 的 SCRIPT 方法在 rootfs 分区（ext4）上找到 `/boot/boot.scr`，剩下的事咱们交给这个脚本，它替咱们裸读 boot 分区，再靠 `bootm` 把控制权交给内核、咱们链的后半段就此接上。脚本其实很简单：拢共就四行，咱们挑 `mmc read` 和 `bootm` 这两行关键的看：

```
mmc dev 0
setenv bootargs console=ttyFIQ0 root=/dev/mmcblk0p3 rw rootwait
mmc read 0x08000000 0x6000 0x20000
bootm 0x08000000
```

`mmc read` 那行咱们从 boot 分区扇区 `0x6000` 起读 `0x20000` 个扇区到 `0x08000000`。咱们把 FIT 装到这个地址、避开 `kernel_addr_r`（`0x02000000`），是因为 bootm 拷贝内核子镜像时会写内核自己的加载地址，FIT 暂存在那里其实就会自己覆盖自己。内核起来挂 `mmcblk0p3` 的 ext4 根文件系统（rootfs），然后咱们就能看到 systemd 接手，最后 GNOME 给咱们亮出来。

### eMMC 上的整体布局

| 扇区      | 内容                                     | 大小                       |
| --------- | ---------------------------------------- | -------------------------- |
| `0x40`    | idbloader.img（裸写，非 GPT 分区）       | —                          |
| `0x4000`  | uboot：u-boot.itb                        | 4 MiB                      |
| `0x6000`  | boot：boot.img（kernel FIT，整分区裸写） | 64 MiB                     |
| `0x26000` | rootfs：ext4（Ubuntu GNOME）             | 分区 8 GiB，镜像本身 3 GiB |

整条打包链其实全部由主线工具产出：idbloader.img 和 u-boot.itb 都出自 `evb-rk3588_defconfig` 自带的 binman，SDK 的打包脚本咱们一行都不用。这就是 RK3588 给咱们的主线红利。

## 闭源与开源的分界线

咱们把整条链按一个标准过一遍：每一级能不能在主线仓库里翻到源码。

| 链上级别              | 开源状态                  | 说明                                  |
| --------------------- | ------------------------- | ------------------------------------- |
| BootROM               | 闭（固化）                | 无所谓开源，反正改不了                |
| DDR init（TPL）       | **闭**（rkbin 固件）      | 训练算法无源码，RK 平台硬现实         |
| SPL                   | **开**（主线 U-Boot SPL） | 为什么不能用原厂的，见下文版本约定    |
| BL31（ATF）           | **闭**（rkbin 固件）      | EL3 + PSCI，常驻到关机                |
| u-boot.itb 打包       | 开（binman）              | 主线工具，布局可读可改                |
| U-Boot proper         | 开（主线 2026.07-rc4）    | `evb-rk3588_defconfig` + 咱们十个补丁 |
| kernel FIT / boot.scr | 开                        | 主线 mkimage 随便用，SPL 管不着它     |
| Linux                 | 开（主线，pin v7.3.1）    | 设备树是咱们移植的                    |
| rootfs                | Ubuntu 26.04              | GNOME 桌面，rootfs 章                 |

所以咱们诚实地数一遍，**残留的闭源依赖其实就两个：DDR init 和 BL31**，都来自公开的 rockchip-linux/rkbin 仓（submodule 引入），咱们人人都能取用、只是拿不到源码。咱们把闭源依赖数完就到这儿了，原厂 SDK 的 U-Boot 整套都被咱们替换掉了，SDK 自带的私有打包工具（mkimage 魔改版、afptool、rkImageMaker），也被仓库自己的纯 Python 工具消掉了。

## rkbin 的固件家族：一个一个认

rkbin 其实是 Rockchip 官方放在 git 上的预编译固件仓（`third_party/rkbin`、submodule 引入），咱们拿到的只有编译结果、没有源码。咱们要用的 RK3588 固件都躺在 `bin/rk35/` 里，这块板的取用清单就写在 board.yaml 的 `rkbin:` 段。咱们把每个文件都讲清楚，谁在链上哪一级、哪些有主线替代、哪些咱们绕不开：

| 固件          | 文件（板配置里的取法）                                      | 在哪一级                             | 干什么                     | 主线能替吗                                   |
| ------------- | ----------------------------------------------------------- | ------------------------------------ | -------------------------- | -------------------------------------------- |
| DDR init      | `rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.*.bin`（实测 v1.21） | idbloader 的 TPL，链上第一段可执行码 | DRAM 训练                  | **不能**                                     |
| SPL           | `rk3588_spl_v1.14.bin`（原厂编译的 U-Boot SPL 2017.09）     | idbloader 的第二段                   | 装载并验签 u-boot.itb      | **能，且已经替了**（`spl_source: mainline`） |
| BL31 / ATF    | `rk3588_bl31_v*.elf`（v1.54）                               | u-boot.itb 内，EL3                   | 安全世界、PSCI/SMC         | **不能**                                     |
| BL32 / OP-TEE | `rk3588_bl32_v*.bin`                                        | 本链未用                             | 可信执行环境               | 直接省略（非必需，格式也不合 binman）        |
| usbplug       | `rk3588_usbplug_v1.*.bin`（实测 v1.11）                     | 不在正常启动链                       | USB 下载协议，给烧写工具用 | 无需替代，它就是工具                         |

有三个点咱们容易混，这里咱们单独说清：

- **DDR 固件是一颗“combo”件。**文件名里 `lp4_2112MHz_lp5_2400MHz` 的意思是同一颗固件同时带 LP4 和 LP5 两套配置，上电时它自己探测颗粒类型选路。本板是 LPDDR4X，吃到的是其中 2112MHz 的档位。板配置里留了降档备选（`lp4_1848/lp5_2112`），万一训练不稳咱们可以换低频档。
- **正常启动的 idbloader，和烧写用的 MiniLoaderAll，是两个东西。**烧写配置 RKBOOT ini 用 boot_merger 把 DDR + usbplug + SPL 拼成 `MiniLoaderAll.bin`，它是一次性下载助手：烧写时靠它把板子带进下载模式，它携带 Rockchip USB 下载协议和 RK3588 的芯片标签。每次上电 BootROM 从 `0x40` 加载的 idbloader 则是 binman 产的主线版本，里面没有原厂的下载协议，所以烧写镜像 update.img 里还得留一个 MiniLoaderAll 纯当烧写助手。两个 loader 用的是同一批公开 rkbin 固件，角色不同，咱们别混。顺带一份考据：RKBOOT ini 里 `NEWIDB=true`、`471_RC4_OFF=true`、`RC4_OFF=true` 这几个开关控制 idblock 头的格式与加密位，还有一段 RK3588 独有的 `[BOOT1_PARAM]`（八个 WORD，rk3568 的 RKBOOT 就没有这段），下一章打包时咱们会在 ini 注释里看到它们。
- **换成主线 SPL，免掉了旧负担，换来一条新约定。**原厂 SPL（就是前面表格里那颗 `rk3588_spl_v1.14.bin`）是闭源的，它会单方面定下不少隐性约束：旧一代 SoC 上踩过芯片标签写法不匹配、OP-TEE hash 校验通不过、必须用原厂魔改 mkimage 打包这类问题，根源都是闭源 SPL 改不动。RK3588 换成主线 SPL 之后，验签和装载逻辑是主线源码，咱们能读能改，还能用 git bisect（按提交二分定位问题），原厂魔改 mkimage 那一环也从链上消失了。免了旧负担，换来一条新约定：**SPL 与 BL31 必须同代**。这就是下一节要展开的内容。

## 版本约定：一场没有报错的 bootloop

板子到手后咱们最早遇到的问题就是它。这里咱们讲机制和排查的结果，具体的排查步骤咱们下一章展开。

咱们刚起步时，链的前段照搬的是已在别的板上验证过的方案，咱们在 idblock 里放原厂的 rkbin SPL，后面咱们接的就是主线 U-Boot。同样的组合咱们在 RK3568 板上跑通过，没理由到咱们这块 RK3588 上就不行。结果一上电，咱们看到链上每一级都在串口里报喜，唯独该 BL31 报的 NOTICE banner 其实从未出现，结果板子无声复位、循环往复，完整的现场咱们下一章从头摆。

这场循环其实全程没有一行报错。每一环的交接都声称成功，然后板子在 BL31 该接棒的地方无声复位，咱们连 U-Boot 的早期调试串口都没来得及看到它打出一个字。

诊断的关键就一条：bootlog 里有没有 `NOTICE:  BL31:` 这行。咱们知道 BL31 起来时 ATF 会主动打这行 banner，可上面这段循环里其实**没有**它。这说明断点在 SPL 把控制权交给 BL31 的那一步，U-Boot 本体和内核那会儿其实都还没轮到出场，所以咱们得从固件间的交接约定里找原因。

根因是 rkbin 内部的版本约定。原厂的 `rk3588_spl` v1.14（基于 U-Boot 2017.09）**早于** BL31 v1.54：BL31 v1.54 把 `bl31_base` 基址迁到了 `0x60000`，而旧版 SPL 还按旧基址去交接。所以两代固件各说各话、BL31 压根没被叫起来，咱们眼看着 CPU 复位重启、循环往复。咱们不禁要问，同样的组合为什么在 RK3568 上就没事了呢？咱们看 `rk356x_spl`：它没有经历这轮基址迁移、新旧约定恰好一致、板子也就躲过去了。这个隐患阴就阴在咱们拿别板的经验往上套上面，换一颗 SoC 之后 rkbin 内部的私有约定就换了一套，咱们手里的经验也就不能平移了。

解法在板配置里其实就一行：`spl_source: mainline`。咱们换上主线 U-Boot 自己编出来的 `u-boot-spl.bin`，idblock 里放的就不再是原厂的 `rk3588_spl`。主线 SPL 与 BL31 v1.54 同代、基址约定也就一致了。这其实也是 U-Boot 官方给 RK3588 定下的标准流程，拢共三样东西咱们都换上了主线：

- **rkbin DDR 固件当 TPL**
- **主线 SPL**
- **binman 打包**

咱们换上之后串口里那行 `NOTICE:  BL31: ... fwver: v1.54` 终于出现了，困扰咱们的 bootloop 就此断链。原厂 SPL 那颗文件咱们在板配置里还留着（烧写配置和兜底用），但在启动链上它其实已经出局。

这场 bootloop 给整卷定下了基调：RK3588 的问题不在“缺驱动”，在闭源件之间的私有约定、在流程之间的时序缝隙。后面 LCD 的像素时钟交接、GPU 固件的加载时机，咱们都会看到它们是同一类问题的不同切面。

## 全卷路线：十章一条主线

这一章咱们用来开场，后面九章其实按移植顺序排，一条线串下来：咱们起步把链跑通，接着咱们把外设一块块点亮，然后咱们把迭代效率提上去，最后两章咱们用来收官全卷。

- **U-Boot 一章**：那场无声 bootloop 的完整排查过程，binman 打包细节，Loader 模式烧写。链的前段在这一章定型。
- **内核一章**：主线 Linux（板配置固定在 v7.3.1，最初的点亮在 7.1 上完成，随后升级）加 topeet 板级设备树——从原厂 5.10 内核的 `topeet-rk3588-linux.dts` 移植到主线，补丁序列怎么排，首次启动长什么样。
- **LCD 一章**：全卷耗时最长的一段排查。TC358775 这颗 DSI→LVDS 桥片的初始化时序、VOP2 死锁、GT911 触摸。
- **GPU 一章**：Panthor 驱动，Mali-G610 的固件为什么必须内建进内核（加载时机问题），一路到 renderD128。
- **rootfs 一章**：基于 ubuntu-base 裸根文件系统装好 GNOME 桌面，再打包进 eMMC。
- **网络一章**：GMAC 网卡，加 tftp（经网络拉内核）+ nfs（经网络挂载根文件系统）的免烧录迭代方式——内核和 rootfs 都走网络，改一次烧一次 eMMC 的日子到此为止。
- **外设一章**：WiFi（RTL8723DU，主线 rtw88 驱动，已在板上验证）和 cpufreq 调频。
- **NPU 一章**：原厂 GPL 驱动移植进主线，加一个 MIT 许可的自研运行时换掉闭源用户态，九个模型跟原厂库逐字节对拍，多媒体核（RGA3、JPEG、H.264）也一并点亮。
- **GPU 用户态一章**：QEMU 模拟机里的采样合成研究线，从桌面满负载黑屏打到真壁纸像素级上屏，全卷的方法论在这里收拢。

每章的里程碑都有对应的工程日志和原始串口 log，咱们挂在 `document/notes/` 与 `document/logs/rk3588/` 下。教程里出现的每一段“成功长这样”，咱们都从这些 log 里截、一个字都不合成。

## 成功长这样

```
DDR ... fwver: v1.21
LPDDR4X, 2112MHz
...
U-Boot SPL 2026.07-rc4 ...
## Checking hash(es) for Image atf-1 ... sha256+ OK
## Checking hash(es) for Image u-boot ... sha256+ OK
NOTICE:  BL31: v2.3 ... fwver: v1.54
...
U-Boot 2026.07-rc4 ...
Model: Rockchip RK3588 EVB1 V10 Board
SoC:   RK3588
DRAM:  16 GiB
```

每一行都对应一级交接的成功：DDR 固件 v1.21 帮咱们把 16GiB 点亮，主线 SPL（2026.07-rc4）给咱们把验签全过了，BL31 v1.54 的 NOTICE 打出来了（那场 bootloop 已经过去），主线 U-Boot 接棒向咱们报到。内核侧咱们同样逐项看：`Brought up 1 node, 8 CPUs` 告诉咱们八核齐了，`panthor ... Mali-G610 id 0xa867` 让咱们看到 GPU 认到了，`mmcblk0: mmc0:0001 METORA 116 GiB` 加 `new HS400 Enhanced strobe MMC card` 说明 eMMC 跑在了满速上，最后咱们看到 systemd 起来接管，GNOME 给咱们亮在 1024×600 的屏上。

## 这块板现在到哪一步了

卷尾咱们把这块板的现状如实盘一遍，咱们对照各章成果单看。

咱们数点亮的：

- 显示与触摸（LCD 章）
- Panthor GPU（GPU 章）
- GNOME 桌面（rootfs 章）
- GMAC 有线网，加 TFTP+NFS 免烧录迭代（网络章）
- WiFi 与 cpufreq（外设章）
- NPU 与自研运行时，九个模型逐字节对拍，多媒体核逐核并发（NPU 章）
- eMMC、调试串口、USB2 host 这些一路在用的基础件

仿真线上还有一笔咱们单独记：GPU 用户态的采样合成研究线在 QEMU 模拟机里收官，真壁纸像素级上了屏，但它证明的是软件控制流，不算板上的点亮，板上依据仍是 GPU 章的内建固件（GPU 用户态章）。

没做的咱们也照实说。蓝牙、摄像头（rkisp1）咱们还没接板级，规划咱们记在 index。VPU 的编码侧、音频、RTC、SD 卡、PCIe 这批接口咱们整卷没碰，VPU 的解码副实例倒是在 NPU 章一并验了。

下一章咱们就从那场无声的 bootloop 开始：原厂 SPL 与 BL31 的版本约定怎么对不上，主线 SPL 怎么换上去，换完之后 binman 怎么打包、Loader 模式怎么烧写。
