# Ch1 — 引导启动：主线 7.1 板上首启到 login

> 这一章咱们把 RK3568 ATK 板，从 BootROM 一路带到 busybox 的 `login:`。和 RK3588 卷的启动链比，RK3568 的前段短一截，原厂的 `rk356x_spl` 没有基址错配引发的 bootloop，咱们不必切主线 SPL，所以本章的力气都花在 eMMC 启动的几处板级细节上。完整的过程记录在 [notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) 里。

> 范围咱们也交代清楚：本章讲的是 MVP 首启，咱们的目标就是把链一路跑到 `login:`。内核用的设备树当天换过一代，早上出发时还是主线 EVB1 的家底，午后的大重 build 里切到了 ATK 板级，时间线的细节咱们留到后面“成功长这样”的一节里再摆。ATK 板级的八个子系统（PMIC、双 GMAC、audio、触摸、LCD、GPU、CAN、RTC）怎么移植、工程上的债怎么收，都留给了[下一章](02_peripherals)，本章咱们不展开。

## 起点：多板框架与零原厂打包工具的基线

RK3568 在咱们的三级阶梯里占中间一级：RK3506B 的 ARM32 地基之上，咱们在这块板上头一回进 AArch64，头一回让 ATF（ARM Trusted Firmware 的安全固件框架）进场，也是头一回系统地学 Linux 的标准驱动框架。再往上的 RK3588 那级，才轮到异构多核与 GPU、媒体、AI 这些产品级的课题。

本卷的主角是正点原子的 ATK-DLRK3568。它和 RK3588 卷的迅为 topeet 板一样，都是原厂 EVB 的亲戚，正点原子拿的是 Rockchip EVB1 DDR4 v1.0 参考设计（板名与参考设计出自 [board.yaml](../../../boards/rk3568-atk/board.yaml) 的板头注释），SoC 用的是 RK3568B2，内存是 4 GiB 的 LPDDR4X，存储是一颗 58.3 GiB 的 eMMC，供电走的是 RK809。这几项规格 board.yaml 的头注释里其实没有，读数来自当天串口记录的自报，SoC 型号、DRAM 容量、PMIC 型号、eMMC 的 58.3 GiB 枚举都是 log 里现成的，[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) 与 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 也各记了一份。既然是 EVB 的亲戚，主线对 EVB1 的现成支持咱们就能整份继承。

轮到咱们动 RK3568 的时候，仓库的地基已经重整过一轮了。奠基的记录在 [notes/36](../../notes/36-2026-07-22-rk3568-multiboard-and-mainline-build.md)（07-22）里，当天落了三个 commit。`d0e8724` 把单板硬编码重构成了多板框架，板注册表加上 `forge --board=<id>` 的选择层，RK3506B 那一路（板号 aes）的回归门同时通过。`9d600e9` 立起了 rk3568-atk 的脚手架，主线 v7.1 的内核直接编出了 `Image` 和 `rk3568-evb1-v10.dtb` 两样产物，咱们没打一个 patch。`d783172` 把 rkbin 的 blob 接进了 binman（U-Boot 自带的镜像打包工具，它按一份设备树格式的描述，把各段二进制摆进最终的镜像）。当时最不确定的三件事，框架能不能多板化、主线能不能编、loader 能不能甩开原厂的工具，一夜之间全过了。

loader 这一段值得咱们单独铺开，它是后来 RK3588 沿用的基线。RK3568 每次启动真正跑的是 `idbloader.img` 与 `u-boot.itb` 两颗镜像（BL31 嵌在后一颗里），全部由主线 U-Boot 自带的 binman 组包，喂给它的只有 rkbin 的闭源 blob 和两个环境变量。原厂的打包工具在启动链上一处都不出现：`boot_merger` 只产了 `MiniLoaderAll.bin` 一颗文件，那是烧写时灌进 DRAM 的一次性下载助手（RKDevTool 是 Rockchip 的烧写工具，它的 `db` 命令用这颗文件），正常启动的链条上没有它的戏份，出处是 [RKBOOT ini](../../../boards/rk3568-atk/RKBOOT-RK3568-atk.ini) 与 [package-file](../../../boards/rk3568-atk/package-file-emmc.txt) 的头注释。notes/36 给 RK3568 记的名号是“零原厂打包工具”（笔记的原话是零 vendor 工具），被拿来对照的反例正是 RK3506B，那块板的启动 loader 还得靠 boot_merger 打，RK3568 比 aes 干净了一档。

咱们要看的几行在板配置里长这样，节选自 [board.yaml](../../../boards/rk3568-atk/board.yaml) 的原文：

```yaml
uboot:
  defconfig: evb-rk3568_defconfig
  fit_source: binman                    # ATF board → binman emits idbloader.img + u-boot.itb (BL31 embedded)
  arch_override: arm                    # explicit (PR2): Rockchip u-boot ships under arch/arm/ even for arm64

rkbin:
  spl_source: rkbin                    # explicit (PR2): rk3568 uses the rkbin vendor SPL
  blobs:
    ddr: rk3568_ddr_1560MHz_v1.*.bin
    usbplug: rk356x_usbplug_v1.*.bin
    spl: rk356x_spl_v1.*.bin            # matches v1.14 (not the _nand variant)
    bl31: rk3568_bl31_v*.elf            # BL31 = ATF (RK3568 has ATF, unlike RK3506)
```

`arch_override: arm` 那行是新手最容易愣住的地方：U-Boot 的源码树把 Rockchip 全家都放在 `arch/arm/` 下面，哪怕 SoC 是 arm64 的板子，arm64 与 armhf 的区分也只落在 `CROSS_COMPILE` 上。咱们在 RK3588 卷的 [U-Boot 章](../rk3588/01_uboot)交代过同款细节，这里就不重讲了。

## 启动链全景：一级一级对着串口看

咱们把 RK3568 的启动链画出来，长这样（按成功当天的组成）：

```
BootROM
  → DDR init            ← rkbin 闭源 blob（v1.25，LPDDR4X 训练到 1560 MHz，4 GiB）
  → idbloader @0x40     ← binman 组包：DDR blob 当 TPL + 原厂 rk356x_spl v1.14
  → SPL                 ← 原厂 rk356x_spl v1.14（2017.09 底子，这条板能用）
  → ATF BL31            ← rkbin v1.46，binman 嵌进 u-boot.itb（atf-1..atf-6 六段）
  → U-Boot 2026.07-rc4  ← 主线，evb1-v10 DT
  → bootm FIT           ← kernel + DTB（BOOTCOMMAND 直载，FIT 暂存 0x08000000）
  → Linux 7.1.0         ← 主线 v7.1，SMP PREEMPT，4 × Cortex-A55
  → mmc1 HS200 eMMC     ← mmcblk1，p1/p2/p3
  → EXT4 → busybox init → login
```

链图里 `bootm FIT` 那一级的 FIT（Flattened Image Tree）是贯穿全章的词，咱们给它一句白话：这是一种按设备树结构把多段镜像打包在一起的容器格式，咱们装进去的是内核与 DTB，每一段都带一份 sha256 的校验值，bootm 装载的时候验了哈希才搬。上电后头一个动身的是 BootROM，它是片内固化的代码，咱们改不了，只能顺着它的约定来。它从 eMMC 的扇区 `0x40` 把 idbloader 读进片内 SRAM，`0x40` 是裸扇区的偏移，不占 GPT 的分区表项。写在这个位置、按 BootROM 认的头部格式摆好的这段内容，它的行话名字叫 idblock，装着它的文件就是 idbloader.img。binman 组包的一侧，TPL（U-Boot 的第一阶段，本该由它把 DRAM 初始化做起来）的位置由 rkbin 的 DDR 固件顶替，因为主线写不了 DRAM 初始化，这是 Rockchip 三块板共同的硬边界，SPL 的位置装的则是原厂的 `rk356x_spl`。

DDR 固件干活的样子，咱们在 [09:11 的串口记录](../../logs/rk3568/202607260911.txt) 开头就能看到：

```
DDR 5b48980fd7 typ 25/12/03-15:33.27,fwver: v1.25
...
LPDDR4X, 324MHz
BW=32 Col=10 Bk=8 CS0 Row=16 CS1 Row=16 CS=2 Die BW=16 Size=4096MB
...
change to: 324MHz
change to: 528MHz
change to: 780MHz
change to: 1560MHz(final freq)
```

咱们看它从 324 MHz 起步，528、780 一级级地上去，最后落在了 1560 MHz，两颗 CS 各装了 2 GiB，总共是 4096 MB 的容量。中间省略的行是各频点的驱动强度、vref 与眼图训练参数，原文在 log 的第 1 至 93 行，想细看的读者可以对着翻。

DDR 训练完就轮到 SPL 接棒了。它到底是不是原厂的那颗，串口会替咱们作证：

```
U-Boot SPL 2017.09-g606f72bd97a-240527 #lxh (May 30 2024 - 16:08:15), fwver: v1.14
...
Trying to boot from MMC2
MMC: no card present
spl: mmc init failed with error: -123
Trying to boot from MMC1
Trying fit image at 0x4000 sector
...
## Checking atf-1 0x00040000 ... sha256(77f66bc3ae...) + OK
## Checking u-boot 0x00800000 ... sha256(15454b3b95...) + OK
## Checking fdt-1 0x008b63c0 ... sha256(0525fca4c0...) + OK
## Checking atf-2 0x0005a000 ... sha256(384b87ec34...) + OK
## Checking atf-3 0x0005c000 ... sha256(fc632865ba...) + OK
## Checking atf-4 0xfdcc1000 ... sha256(5e891e12e9...) + OK
## Checking atf-5 0xfdcce000 ... sha256(821ec3fca7...) + OK
## Checking atf-6 0xfdcd0000 ... sha256(37b2f43b0d...) + OK
Jumping to U-Boot(0x00800000) via ARM Trusted Firmware(0x00040000)
Total: 125.294/251.425 ms
```

banner 里的 2017.09 与 `#lxh` 后缀把它交代得很干净：这就是 rkbin 的原厂 SPL，Rockchip 拿自家 2017.09 的老 U-Boot 编的，不是主线编出来的产物。它头一个试的是 MMC2（SD 卡槽、未插卡、报 -123），转去 MMC1 找到了 eMMC，接着从 0x4000 的扇区把 u-boot.itb 读进来，对六个 atf 段、u-boot 与 fdt 逐个地验 sha256，全过了之后才宣布交棒。有个细节值得咱们留意：原厂 SPL 认 binman 产的 FIT 布局，六段 atf 各装各的地址，这一步两边是对得上的，RK3568 能借原厂 SPL 的前提就藏在这里。

BL31 真正跑起来的心跳，咱们在紧跟着的几行里看到：

```
NOTICE:  BL31: v2.3():v2.3-948-g0a207bf3c:huan.he, fwver: v1.46
NOTICE:  BL31: Built : 16:25:04, Sep 20 2025
INFO:    GICv3 without legacy support detected.
...
WARNING: No OPTEE provided by BL2 boot loader, Booting device without OPTEE initialization. SMC`s destined for OPTEE will return SMC_UNK
ERROR:   Error initializing runtime service opteed_fast
...
INFO:    Entry point address = 0x800000
INFO:    SPSR = 0x3c9
```

OP-TEE（跑安全应用的可信执行环境、行话叫 BL32）是咱们故意省略的：rkbin 发的 bl32 是裸 `.bin`，binman 的 tee-os 节点要的却是 ELF，格式偏偏对不上，而它对跑到 login 不是必需件。log 里那行 WARNING 与 ERROR 是省略之后的正常回响，其实不是故障。这一段的取舍与 RK3588 卷完全同款，细节见 [RK3588 U-Boot 章](../rk3588/01_uboot)的 binman 一节。

再往上咱们要看的就成了存储的布局。eMMC 的 GPT 分三段，idbloader 裸放在 0x40 的位置、不占 GPT 分区，完整的分区表写在 [parameter-emmc-atk.txt](../../../boards/rk3568-atk/parameter-emmc-atk.txt) 里：

```
CMDLINE:mtdparts=:0x00002000@0x00004000(uboot),0x00020000@0x00006000(boot),0x00200000@0x00026000(rootfs)
```

咱们对着分区表念一遍，uboot 分区从 0x4000 起（4 MiB 的 u-boot.itb），boot 分区从 0x6000 起（64 MiB 的整分区 FIT），rootfs 分区从 0x26000 起（1 GiB 的 ext4）。三个分区在内核里就是 `mmcblk1` 的 p1、p2、p3，root 设备写 `/dev/mmcblk1p3` 的由来也在这里。

咱们把视野拉宽再比，差异就集中在链条的中段。RK3506B 是 ARM32 的片子，链上没有 ATF 的位置，RK3568 进到了 AArch64，BL31 就成了必需件。RK3588 的链上同样有 BL31，可它那对原厂 `rk3588_spl` v1.14 与 BL31 v1.54 出了装载基址的迁移，v1.54 把自己挪到了 0x60000，旧 SPL 交棒走的还是老地址，于是有了那场无声 bootloop，结果只能切主线 SPL。这里咱们顺带消一个歧义，rk3588_spl 与本章的 rk356x_spl 同为 v1.14，纯属两条版本线上的巧合。RK3568 的原厂 SPL 与 BL31 v1.46 没有那场迁移，交棒的地址 0x00040000 两边一致，log 里 `NOTICE: BL31` 的心跳每次都按时出现，所以这一级咱们借原厂 blob 借得心安理得。咱们再记一处小的差别：RK3588 的 u-boot.itb 里 BL31 分三段（atf-1..3），RK3568 分的是六段，段数由各自的 FIT 布局决定，不影响咱们的理解。一块板上配好的 rkbin 组合，换一块板就不能直接平移了，闭源 blob 之间的配套，只能一块板一块板地验。咱们在 RK3588 卷用一场 bootloop 交过学费，RK3568 算是配套成立的正例，配套问题的系统整理见 [pitfalls/01](../../pitfalls/01-rkbin-spl-contracts.md)。

## 首启路上的五处翻车

五处翻车的现场都出自 [notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) 的当天记录，咱们一处一处过。

### 翻车一：bootflow 在裸 FIT 分区上找不到入口

U-Boot 主线的默认 `bootcmd` 走 bootflow 扫描，咱们放手让它找启动的设备。09:11 的 log 里它扫了一圈，结果是这样：

```
Scanning for bootflows in all bootdevs
Seq  Method       State   Uclass    Part  Name                      Filename
---  -----------  ------  --------  ----  ------------------------  ----------------
...
Scanning bootdev 'mmc@fe2b0000.bootdev':
Card did not respond to voltage select! : -110
Scanning bootdev 'mmc@fe310000.bootdev':
Unknown uclass 'nvme' in label
Unknown uclass 'scsi' in label
Unknown uclass 'usb' in label
Scanning bootdev 'ethernet@fe010000.bootdev':
ethernet@fe2a0000 Waiting for PHY auto negotiation to complete......... TIMEOUT !
phy_startup() failed: -110
BOOTP broadcast 1
...
No more bootdevs
```

咱们看到它扫完之后一格分区都没列出来，最后跑到了网卡上等 BOOTP，超时了才收场。定位的推理链很短：forge 的 boot 分区是裸分区，`assemble` 阶段把 boot.img（kernel FIT）补齐后整分区写了进去，不带任何的文件系统，而 bootflow 的各种 bootmeth（extlinux、script、efi）全都要文件系统才能当文件去读，raw FIT 对它们来说是不存在的（出处是 [boot-emmc.cmd](../../../boards/rk3568-atk/fit/boot-emmc.cmd) 的头注释）。

咱们的修法是把启动脚本的入口挪个地方：boot.scr 放进 rootfs 分区（ext4、有文件系统）的 `/boot/` 下，SCRIPT bootmeth 就能在 rootfs 上命中它了。脚本的本体拢共四行，源文件就是咱们仓库里的 [boot-emmc.cmd](../../../boards/rk3568-atk/fit/boot-emmc.cmd)：

```
mmc dev 0
setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
mmc read 0x08000000 0x6000 0x20000
bootm 0x08000000
```

咱们 source 它之后，它对 boot 分区做原始的 `mmc read` 再接上 `bootm`，等于把文件系统里的入口和裸分区里的载荷接到了一起。打包脚本至今仍把 boot.scr 放进 rootfs 的 `/boot/`，镜像里两套入口从此并存（一套是这里的 boot.scr，另一套是翻车五要写的 BOOTCOMMAND 直载）。不过 autoboot 依然不通，原因咱们放到翻车五再讲。

### 翻车二：FIT 的暂存地址踩了 kernel 的 load address

咱们让 boot.scr 把 FIT 从 eMMC 读进内存，第一版的写法直接用了现成的 `${kernel_addr_r}`：

```bash
mmc read ${kernel_addr_r} 0x6000 0x20000    # ${kernel_addr_r} = 0x02000000
```

`bootm` 当场报了 `new format image overwritten` 就停了，原文记在 [notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) 修复清单的第二条。根因是 FIT 里 kernel 子镜像声明的 load address 也是 0x02000000，ITS 源文件 [rk3568-kernel.its](../../../boards/rk3568-atk/fit/rk3568-kernel.its)（ITS 就是描述 FIT 装了哪些段、各段装到哪个地址的文本源文件）里写的就是 `load = <0x02000000>`，结果两个数叠在了同一处：bootm 解 FIT 时要把 kernel 搬到它自己声明的加载地址，可咱们恰恰把整个 FIT 读在了同一地址，bootm 一搬就把还没解完的 FIT 自己盖掉了。

这一次的改法很直接，把 FIT 读到不冲突的空闲 DRAM 里去。RK3568 上 kernel 装在 0x02000000、fdt 装在 0x12000000（出处是主线 `rk3568_common.h` 的 ENV_MEM_LAYOUT_SETTINGS），咱们把暂存地址挪到 0x08000000，两边之间的空闲区，bootm 再把 kernel 从 FIT 搬去 0x02000000 的时候就盖不到 FIT 自己了：

```bash
mmc read 0x08000000 0x6000 0x20000    # FIT 暂存 0x08000000
bootm 0x08000000                       # bootm 从这里解 FIT、把 kernel 搬到 0x02000000
```

bootm 报的 `new format image overwritten` 其实没把地址重叠这件事说出来，得知道 FIT 的装载机制才看得懂，所以它的隐蔽性值得咱们单独记一笔。RK3588 那边遇到的是同一个问题，用的也是同一个 0x08000000 解法（见 [RK3588 U-Boot 章](../rk3588/01_uboot)的 autoboot 一节），两块板是各自独立验证过的。

### 翻车三：rootfs 分区装不下 Phase 2a 的全功能栈

首启用的 buildroot rootfs 是 Phase 2a 的全功能栈（rk3568 计划里 rootfs 阶段的代号，说的是 Qt6、Mesa、GStreamer 那一套），咱们展开一看是 451 MB 的体量。板配置里 rootfs 分区当时只给了 512 MiB（parameter 的 `0x00100000` 扇区），扣掉文件系统自身的开销就装不下了。

咱们改分区的路子也唯一，把 rootfs 扩到 1 GiB 就够了，而且两处得一起改，因为分区表和镜像大小是两个各自独立的数：

```
# parameter-emmc-atk.txt
0x00100000 → 0x00200000     # rootfs 分区 512 MiB → 1 GiB

# 打包 eMMC 镜像的脚本（当天的 pack-emmc）
ROOTFS_MIB 256 → 1024       # ext4 镜像大小
```

咱们在 parameter 的注释里还读到了同一段的另一个细节：rootfs 长度之所以写成固定的 0x200000，是因为 rkfw-pack 的正则解析不了原厂 parameter 惯用的 `-` 增长记号，照原样写下去产出的会是空分区、直接 panic。现在 [board.yaml](../../../boards/rk3568-atk/board.yaml) 里的 `rootfs_mib: 1024` 就是这一改定下的值。

### 翻车四：同一颗 eMMC，三级固件里换了三个名字

U-Boot 里的 `mmc dev` 按编号选设备，而编号容易凭惯性写反。RK3568 上 `mmc@fe2b0000`（sdmmc0、SD 卡槽）占的是 dev 1，`mmc@fe310000`（sdhci、eMMC）占的是 dev 0，所以 eMMC 是 dev 0 而不是 dev 1。咱们当天一度照着 SD=0 的惯性写 `mmc dev 1`，选中的其实还是 SD 卡槽那一路，经过记在 notes/40 的修复清单第四条。判据是 `rk3568.dtsi` 里的控制器地址：sdmmc0 对应的是 dwmmc@fe2b0000（就是串口里的 mmc@fe2b0000）、sdhci 对应的是 sdhci@fe310000，U-Boot 的 dev 号按探测顺序给，dev 0 落在了 sdhci 那一路上。串口里的那行就是判据本尊：

```
MMC:   mmc@fe2b0000: 1, mmc@fe310000: 0
```

再把三级固件的叫法摆到咱们眼前，同一颗 eMMC 换了三个名字：原厂 SPL 嘴里叫 MMC1（09:11 log 里 Trying to boot from MMC1 装的就是它），U-Boot 嘴里喊的是 dev 0，到内核里成了 `mmcblk1`。所以 root 要写的是 `/dev/mmcblk1p3`，而 RK3588 的 topeet 板上是 `mmcblk0p3`，两块板的编号并不一样，照搬过去内核就停在 `Waiting for root device` 了。

### 翻车五：autoboot 停在半路，收尾欠在 patch 化

过了翻车一，手动 boot 的路子已经通了，咱们在 U-Boot 提示符下敲四行就能到内核：

```bash
mmc dev 0
mmc read 0x08000000 0x6000 0x20000
setenv bootargs console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
bootm 0x08000000
```

可松手让 autoboot 自己跑的时候它又不动了。根因回看 09:11 的扫描输出就明白了，bootflow 对 eMMC（`mmc@fe310000.bootdev`）扫过去时交出的就是翻车一里的空表，dev 0 的名下没挂上任何一个分区，放在 rootfs 分区的 boot.scr 自然轮不到被找到。咱们手动敲 `mmc dev 0` 它是认的，bootflow 偏偏不扫，这说的就是主线 bootdev 在 eMMC 上的行为，咱们没有往更深挖下去。notes/40 剩余问题表的原话，说的就是 bootflow 对 dev 0 不扫 partition。

解法走的与 RK3588 是同一条路：把咱们已经手动验证过的序列直接写进 defconfig 的 `CONFIG_BOOTCOMMAND`，从而绕开了 bootflow。RK3588 写的是 load boot.scr、source 两跳，RK3568 写的却更直接，用的就是上面那四行的直载序列，出处是 notes/42 的关键改动第四条。当天下午的镜像里它已经生效，12:32 起的串口记录里看得见它的踪迹（三份 log 里的一份，下节咱们会展开）。

尾巴咱们也要如实记下：这个 defconfig 改动停留在 third_party 的工作树里（working-tree delta，clone 下来看不到的未提交改动），至今没 quilt 化成 series 在册的正式补丁（quilt 是内核圈管补丁序列的老工具，补丁进没进 series 的在册清单，就是咱们区分正式与非正式改动的界线）。仓库里 [patches 的 series](../../../boards/rk3568-atk/patches/linux/series) 在册的只有 rtl8852bs WiFi 的 0001 一发，应用的工具是 git am，0002 的适配补丁不进 series，拉驱动的 fetch 脚本会把它另行套上，BOOTCOMMAND 的改动哪一发都不在。所以本卷的口径是：上电直进 login 的事板上做到了、log 在案，工程化的收尾（补丁化、内部叫 P4）还欠着，第二人 clone 下来是复现不了这一步的，得自己把这行 defconfig 的改动补上。

## 成功长这样：三份串口记录拼出的全程

三份 log 的分工很清楚：09:11 的记录里有 DDR 训练与 SPL/BL31（上文已引），12:32 的记录里是直载 autoboot 与 FIT 装载，13:11 的记录走完了到 login 的全链。后两条记录开头几行的乱码，看着像抓坏了，其实有来历：09:11 的记录是全程按 1500000 抓的，所以从头清晰，到了 12:32，U-Boot 与内核已经切到了 115200，DDR、SPL、BL31 三级还按原厂的默认打 1500000，串口是按 115200 收的，早期那几段就成了乱码。当天晚些时候咱们用 `ddrbin_tool` 把 DDR blob 的波特率也改成了 115200，全链这才统一了（出处是 notes/42 的关键改动第七条、.bak 备份留在 rkbin 目录）。

咱们看 12:32 的 log 从 banner 往下是这样：

```
U-Boot 2026.07-rc4-00043-g5ca1a73c7d30-dirty (Jun 12 2026 - 14:45:32 +0000)

Model: Rockchip RK3568 EVB1 DDR4 V10 Board
SoC:   RK3568B2
DRAM:  4 GiB
...
MMC:   mmc@fe2b0000: 1, mmc@fe310000: 0
...
Hit any key to stop autoboot: 0
switch to partitions #0, OK
mmc0(part 0) is current device
MMC read: dev # 0, block # 24576, count 131072 ... 131072 blocks read: OK
## Loading kernel (any) from FIT Image at 08000000 ...
   Trying 'kernel' kernel subimage
     Data Size:    45652480 Bytes = 43.5 MiB
     Load Address: 0x02000000
   Verifying Hash Integrity ... sha256+ OK
## Loading fdt (any) from FIT Image at 08000000 ...
     Description:  ATK-DLRK3568 (atk-evb1-ddr4-v10) DT (bootargs set by U-Boot: root=/dev/mmcblk1pN)
     Load Address: 0x12000000
   Loading fdt from 0x0ab8a200 to 0x12000000
   Loading Kernel Image to 2000000

Starting kernel ...
```

咱们逐行核对几个要点。`Hit any key to stop autoboot: 0` 的下一行不是 `=>` 提示符，直接落到了 `switch to partitions #0` 上，说明跑的是 BOOTCOMMAND 的直载序列而不是有人在敲键盘。`MMC read` 的起点是 24576 扇区（0x6000）、长度 131072 块（64 MiB），整个 boot 分区都搬进了 0x08000000，翻车二的修复在这里生效了。FIT 里的 kernel 装到 0x02000000、fdt 装到 0x12000000，与 ITS 的声明一致。banner 末尾的 `-dirty` 也不是白来的：09:11 的 banner 还是干净的，12:32 起带上了脏标记，差别正是翻车五里那行还留在工作树里的 defconfig 改动，镜像自己把这件事报了出来。

fdt 的描述串写着 `ATK-DLRK3568 (atk-evb1-ddr4-v10)`，这里咱们得把当天的设备树时间线说明白。镜像里的 dtb 文件已经改名叫 `rk3568-atk-evb1-ddr4-v10.dtb`，而且不只是换了名：DT_NAME 与 ITS 切到 ATK 名下的同时，内容也换成了 ATK 板级的设备树，此前的镜像才一直烧 evb1-v10 的旧货，notes/42 把这一步列进了当天的关键改动。13:11 的 log 可以作证，内核报的 `Machine model` 是 `Alientek ATK-DLRK3568 Board`，四秒多的时候还有一行 `Console: switching to colour frame buffer device 100x80`，按 8x16 的字号折算正是 800x1280，ATK 那块屏当天就是亮着的。真正带着 evb1 家底、屏不亮的是早上 09:11 那一轮的旧镜像，下文毛病表里 LCD 那一行记的就是它的状态。

咱们再看 13:11 的 log 把后半程走完：

```
[    0.000000] Linux version 7.1.0-dirty (charliechen@DESKTOP-65DBAA7) (aarch64-none-linux-gnu-gcc (Arm GNU Toolchain 15.3.Rel1 (Build arm-15.149)) 15.3.1 20260627, GNU ld (Arm GNU Toolchain 15.3.Rel1 (Build arm-15.149)) 2.45.1.20260126) #8 SMP PREEMPT Sun Jul 26 13:05:43 CST 2026
[    0.000000] Machine model: Alientek ATK-DLRK3568 Board
[    0.000000] Kernel command line: console=ttyS2,115200 root=/dev/mmcblk1p3 rw rootwait
[    0.019020] smp: Brought up 1 node, 4 CPUs
...
[    3.039646] mmc1: new HS200 MMC card at address 0001
[    3.050387] mmcblk1: mmc1:0001 C9A611 58.3 GiB
[    3.064842]  mmcblk1: p1 p2 p3
...
[    4.477918] EXT4-fs (mmcblk1p3): mounted filesystem 11111111-2222-3333-4444-555555555555 r/w with ordered data mode. Quota mode: none.
[    4.491748] VFS: Mounted root (ext4 filesystem) on device 179:3.
[    4.514225] Run /sbin/init as init process
```

咱们把关键数字对一遍：主线 7.1.0（构建号 #8、当天 13:05:43 编的），四个 Cortex-A55 全部上了线。eMMC 以 HS200 的模式枚举成 mmcblk1，p1/p2/p3 与 parameter 的三段对上，rootfs 挂成了可读写的 ext4，`Run /sbin/init` 过了之后用户空间就接手了。

login 的原文咱们引在下面（log 第 508 至 523 行）：

```
Welcome to forge RK3568
forge-rk3568 login: [   14.599806] platform sdio-pwrseq: deferred probe pending: pwrseq_simple: reset control not ready
...（省略 2 行，mmc 与 hdmi-sound 的 deferred）
[   14.628940] platform 3c0800000.pcie: deferred probe pending: rockchip-dw-pcie: failed to initialize the phy
[   14.639936] rockchip-pm-domain fdd90000.power-management:power-controller: sync_state() pending due to fc800000.sata
...（省略 7 行，video-codec、rga、pcie 的 pm-domain pending 与一组没输密码的登录提示）
Welcome to forge RK3568
forge-rk3568 login: root
#
```

login 提示符出来了，几个 deferred probe 的报错还在它后面刷屏，那是当天另一批没收敛的尾巴（下节的清单里能对上大半，剩下的正文随后也有交代）。咱们敲 root 进去，`#` 提示符接住了咱们，从 BootROM 到 busybox 的整条链就此打通，MVP 的首启就此完成，时间是 2026-07-26 的午后。

## 首启当天的毛病清单，与交接时的真实状态

这里咱们得把首启当时与交接时两个时刻分开说，免得把首启日的临时毛病当成 RK3568 的最终能力。首启当天（notes/40 剩余问题表）板上实测的毛病是这样的：

| 当天的毛病 | 根因 | 当时的去向 |
|---|---|---|
| 网络只有 lo | `STMMAC_ETH`、`DWMAC_ROCKCHIP` 编成模块，busybox rootfs 没有 modprobe | kernel.config 改 `=y` 重编 |
| Qt6 没进 rootfs | rootfs.tar 还是 Qt5 时期的产物，改完 defconfig 没重跑 buildroot | 重跑 buildroot |
| autoboot 不通 | bootflow 对 eMMC 不扫分区 | BOOTCOMMAND 直载（翻车五） |
| 波特率卡在 1500000，与 bootargs 的 115200 合不上 | U-Boot defconfig 与内核 DT 的默认值双侧都是 1500000 | 双侧改 115200，DDR blob 后补 |
| LCD 不亮 | evb1-v10 的 rm67200 接线，ATK 屏另有主 | 下一章移植 panel |
| sshd 起不来 | `/var/empty` 权限不对，log 里 FAIL | rootfs overlay 修权限 |
| GPU、VPU、USB3 deferred probe | 电源域 sync_state 挂起、dwc3 初始化失败 | 后续轮次再调 |

随后咱们用一轮大重 build，从 [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 的方案到 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 的交接，把表里的毛病逐行收了一遍。改得最顺的是网络，咱们把 `STMMAC_ETH` 一线改成 `=y` 之后，eth0/eth1 双口都通了，PHY 是两颗走 RGMII 的 RTL8211F。Qt6 重跑 buildroot 之后进了 rootfs，455 MB 的体量，只是 Qt 的应用还没在板上跑过。autoboot 靠翻车五的 BOOTCOMMAND 直载通了，12:32 的 log 就是见证。波特率双侧统一到了 115200，DDR blob 的波特率由 `ddrbin_tool` 后补。LCD 也点亮了，ATK 的 panel 移植过去之后 `card0-DSI-1` 报了 connected。

交接时还挂着的，咱们也照实交代。sshd 的那一行，13:11 的 log 里它还是 FAIL，`/var/empty` 的权限没修，笔记里也没记下它的后续。GPU、VPU、USB3 的 deferred 一行，GPU 在这轮里由 Panfrost 把 Mali-G52 驱了起来（card1），VPU、USB3 连同 login 后面刷的 pcie、sata 两条 deferred（一条是 phy 没初始化起来，一条牵着电源域的 sync_state）都留在后续轮次的清单里。毛病表之外另有两条 DT/驱动层的新尾巴：音频的声卡没 probe，WiFi 的 SDIO 总线通了、851 个源文件的原厂驱动还没搬。两条都是移植那一轮新带出来的，跟表内的旧毛病不是一回事。

还有一条工程债压在这一切的上面，咱们得把它摆到明处：这些板级设备树和 panel descriptor 目前是 `third_party/src/rk3568-atk/` 里的 working-tree delta，正式的 quilt 化至今没有做。第二人 clone 下来是复现不了这些外设的，BOOTCOMMAND 的那发改动同样困在这个状态里。把这块债还上（内部叫 P4）是本卷继续往下写的前置，路线图里说的本卷是 MVP，指的就是这个边界（见[路线图](00_roadmap)）。

## 交给下一章

链路通了，板子也不只是能启动：首启那天午后的大重 build 里，EVB1 家底认不出的那些东西，双网口的 PHY 时序、屏、触摸、CAN、RTC，咱们都已经接线并在板上验过了。[下一章](02_peripherals)讲的就是那一轮移植怎么做的、欠着的工程化怎么收，其中 LCD 的 panel IC 之辨、音频的 GPIO 冲突，都是那一章的正戏。WiFi rtl8852bs 与 buildroot 的全栈（Qt6、Mesa、GStreamer、Weston），按路线图排在了更后面。

## 档案与证据

出处大多收进了下面的档案节，正文里咱们只留必要的现场标注，读者要对照原始证据的时候看这里：

- 串口记录三份：[202607260911.txt](../../logs/rk3568/202607260911.txt)（397 行，DDR 训练、SPL/BL31、bootflow 失败现场）、[202607261232.txt](../../logs/rk3568/202607261232.txt)（455 行，直载 autoboot 与 FIT 装载）、[202607261311.txt](../../logs/rk3568/202607261311.txt)（523 行，全链到 login，login 原文在 508 至 523 行）。
- 过程记录：[notes/36](../../notes/36-2026-07-22-rk3568-multiboard-and-mainline-build.md)（多板框架与 binman 接线）、[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)（首启全记录与五条修复，本章主源）、[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)（ATK DT 移植方案）、[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)（交接状态表）。
- 板配置实物：[board.yaml](../../../boards/rk3568-atk/board.yaml)、[parameter-emmc-atk.txt](../../../boards/rk3568-atk/parameter-emmc-atk.txt)、[package-file-emmc.txt](../../../boards/rk3568-atk/package-file-emmc.txt)、[RKBOOT-RK3568-atk.ini](../../../boards/rk3568-atk/RKBOOT-RK3568-atk.ini)、[rk3568-kernel.its](../../../boards/rk3568-atk/fit/rk3568-kernel.its)、[boot-emmc.cmd](../../../boards/rk3568-atk/fit/boot-emmc.cmd)、[kernel.config](../../../boards/rk3568-atk/kernel.config)、[patches/linux/series](../../../boards/rk3568-atk/patches/linux/series)。
- 版本指纹：U-Boot 2026.07-rc4-00043-g5ca1a73c7d30（pin `5ca1a73c`，board.yaml 的 sources.uboot，板上的 banner 带 `-dirty` 后缀，来由见翻车五）、Linux v7.1（板上构建号 #8，2026-07-26 13:05:43）、DDR blob v1.25（1560 MHz）、原厂 SPL v1.14、BL31 v1.46（built Sep 20 2025）、eMMC C9A611 58.3 GiB、rootfs buildroot 2026.08-git。
- 跨卷参照：[RK3588 平台章](../rk3588/00_platform.md)（启动链全图的另一份样本）、[RK3588 U-Boot 章](../rk3588/01_uboot.md)（SPL 与 BL31 配套事故、autoboot 的另一板版本）、[pitfalls/01](../../pitfalls/01-rkbin-spl-contracts.md)（rkbin 配套问题的系统整理）。
