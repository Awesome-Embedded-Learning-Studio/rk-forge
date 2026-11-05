# U-Boot 移植：无声 bootloop 与 rockusb Loader 模式

> [上一章](00_platform.md) 把 RK3588 的平台拓扑、启动链和 rkbin 的闭源固件（blob）家族摆完了，咱们这一章就从链条的第一段可动手处开工，动的是主线 U-Boot。主线对 RK3588 是重点照顾的旗舰（Collabora 长期投入），`evb-rk3588_defconfig`、EVB 设备树、binman 打包全都现成了，板级咱们几乎不用从零写。咱们真正要对付的其实是两件事。头一件是 bootloop：咱们把原厂 SDK 那整套拔掉、换上主线重新走链的时候，串口上连一个字的输出都没有，板子的反应就是无休止的循环复位。另一件是主线里早已写好、却没人启用的 rockusb Loader 模式，咱们把它点亮了，往后烧录的迭代才不用每次都退回 MaskROM。本章落在 U-Boot 侧的补丁共十发（0001 到 0010）。它们全部都在迅为 iTOP-RK3588 EVB 的板子上验证通过了，用的就是 topeet 的 eMMC 版。

## 起点：主线给了什么，补什么

咱们把家底盘一盘。主线 U-Boot 是 2026.07-rc4（源码固定在了某一版提交上，具体的位置见章末档案），它对 RK3588 已经备好了三样东西：

- `evb-rk3588_defconfig`：Rockchip EVB 的板级配置，主线 CI 持续在测。topeet 这块板本质是 EVB 的亲戚，设备树 `rk3588-evb1-v10` 直接可用，串口走 UART2（`CONFIG_DEBUG_UART_BASE=0xFEB50000`）。
- binman 打包支持：一次 `make all` 就能产出 `idbloader.img` 和 `u-boot.itb`，RK3588 的镜像布局（idblock、多段 ATF 装载）binman 都懂。
- rockusb 的完整实现（`cmd/rockusb.c` + `f_rockusb.c`）：Rockchip 私有的 USB 烧写协议，主线代码写得齐齐的，只是 defconfig 没开。这是本章后半场的主角。

这里有个容易绊人的细节，咱们得留心：U-Boot 的源码树把 Rockchip 板子放在了 `arch/arm/` 下面，哪怕它是 arm64 的 SoC。所以咱们在 [board.yaml](../../../boards/rk3588-topeet/board.yaml) 里看到了一行 `arch_override: arm`，这行配置干的事，就是把咱们“arm64 板就该在 arch/arm64 找”的直觉，给显式盖掉了。

咱们要补的板级差异拢共有五件事（咱们行文里的四位编号都是补丁文件的序号、文件在仓库 [patches/uboot/](../../../boards/rk3588-topeet/patches/uboot/series) 下、每发的完整说明在章末总表）：

1. autoboot 只认 eMMC（0001 砍 boot_targets、0003 写死 bootcmd）。
2. 串口波特率对齐全链 115200（0002 改 defconfig 的波特率）。
3. OTG 口定成外设模式给 gadget 用（0005 改 OTG 的设备树）。
4. `reboot loader` 与音量上键两条 Loader 模式入口（0004 开 rockusb 配置、0006 补 BOOT_LOADER 分支、0007 接活音量键检测）。
5. 让 Rockchip 的烧写工具把这个 rockusb 设备认成 LOADER 而不是 MASKROM（0008 改 PID、0009 改 bcdUSB、0010 补 BOS 应答）。

这十发补丁不是散装的。它们按 [series 文件](../../../boards/rk3588-topeet/patches/uboot/series)的顺序，从固定基线的干净主线树上用 `git am` 逐发重放（可二分、可回溯），构建时 forge（这个仓库自己的构建流水线）会把 rkbin 的 BL31 和 DDR blob，通过环境变量的方式喂给 binman。rkbin 就是 Rockchip 官方那个预编译闭源固件的仓库，它的 blob 家族上一章介绍过了。这样的话，咱们任何时候从仓库出发，都能一条命令复现出跟板上跑的完全一致的 U-Boot，所以板上的验证结果咱们才敢放心写给读者。

咱们这边是“板级都有、要对齐差异”，工作量小了，但翻车的花样一点没少，接下来的小节咱们一个个对付。

## binman 打包：idbloader.img 与 u-boot.itb 是怎么来的

RK3588 的启动链，上一章咱们已经画过全景了，这里只看 U-Boot 侧产出的两段镜像。binman（U-Boot 自带的镜像打包工具，按一份设备树描述把各段二进制摆进最终镜像）在 `make all` 时吃两个环境变量：`BL31` 指向 rkbin 的 `rk3588_bl31_v1.54.elf`，`ROCKCHIP_TPL` 指向 rkbin 的 DDR 训练固件（`rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.21.bin`）。产出的两段如下，咱们一段段拆：

**`idbloader.img`（约 202KB）**：咱们看看它的构成。它的前半段是 DDR blob 充当的 TPL，也就是 U-Boot 的第一阶段，RK3588 上这个位置由厂商的 DDR 训练固件顶替，原因是主线写不了 DRAM 的初始化。接在后头的是主线 SPL，SPL（Secondary Program Loader）是 U-Boot 的第二阶段，它的活儿就是把 U-Boot 本体从存储搬进内存。镜像整体被 BootROM 从 eMMC 的扇区 0x40 原始读入，写在这个位置、按 BootROM 认的头部格式摆好的这段内容，就是常说的 idblock。

**`u-boot.itb`（约 1.18MB）**：它装的是 FIT 格式（Flattened Image Tree，一种按设备树结构打包多段镜像的格式）。咱们拿 `dumpimage` 把它解开看，结构是这样的：

```
Image 0 (u-boot):  Load 0x00800000  Entry 0x00800000  (818288 B)
Image 1 (atf-1):   Load 0x00060000                     (149020 B)
Image 2 (atf-2):   Load 0x000f0000                     (24576 B)
Image 3 (atf-3):   Load 0xff100000                     (36864 B)
+ fdt-1 (u-boot.dtb, 203520 B)
```

BL31（ARM Trusted Firmware 的常驻部分，跑在 EL3 的安全世界固件）被 binman 按装载地址分成了三段，`atf-1/2/3` 就是这么来的，主体装在了 0x60000。**BL31 是内嵌在 u-boot.itb 里的**，RK3506B 方案 B（boot 卷里的另一种启动链方案）借原厂 SPL 从外面加载的路数，在这儿是行不通的。这也解释了 board.yaml 里 `fit_source: binman` 那句注释“pack-fit must NOT re-pack”，u-boot.itb 是 binman 按 Rockchip 的 ATF 装载布局生成的，普通的 mkimage 打不出这样的布局，SPL 加载它时按 `conf` 把三段 atf 和 u-boot 各装各的地址，交棒就完成了。pack-fit 的 mkimage 路线是给没有 ATF 阶段的板子（RK3506B）用的，咱们要是拿它重打 u-boot.itb，这套布局就打丢了。

这里咱们要诚实交代一个情况：TEE 是可信执行环境（OP-TEE，也就是所谓的 BL32），在咱们的链上是**故意省略**掉的。rkbin 发的 bl32 是裸 .bin，而 binman 的 tee-os 节点要的是 ELF，所以格式对不上。OP-TEE 对咱们跑通主线启动来说不是必需的，板上 log 里 ATF 也明说了：

```
WARNING: No OPTEE provided by BL2 boot loader, Booting device without OPTEE initialization. SMC`s destined for OPTEE will return SMC_UNK
```

咱们再看 RKBOOT-RK3588-topeet.ini，boot_merger 拿它产出的就是 `MiniLoaderAll.bin`（约 558KB）。它的内容一共三段，`FlashData` 装的是 DDR blob、`FlashBoot` 装的是 SPL，外加一段 usbplug（下载模式用的协议固件）。**BL31 段是没有的**，ini 的注释写得很明白：BL31 住在 u-boot.itb 里面，所以这个下载 loader 只需要 ddr+usbplug+spl。它的角色咱们也要分清：MiniLoaderAll 是**一次性的下载助手**（rkdeveloptool/RKDevTool 的 `db` 命令把它灌进 DRAM，板子这就进了下载模式），并不是每次启动都跑的固件。每次启动时 BootROM 从 0x40 读的 idbloader，是主线的那一套。两条产物路线在 SPL 的选择上必须一致，下一节要讲的事故正是出在这个选择上的。

咱们把本章收工时整条链上谁在跑、从哪来的分工，列成了一张表放在这里，后面各章都会回头对照的：

| 启动级 | 跑的是什么 | 来源 | 开源与否 |
|---|---|---|---|
| BootROM | 芯片内部固件 | 出厂烧死 | 闭源（不可换） |
| TPL / DDR init | `rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.21.bin` | rkbin | 闭源 blob |
| SPL | 主线 U-Boot SPL（2026.07-rc4） | 咱们的 uboot 树 | 开源 |
| BL31 / ATF | `rk3588_bl31_v1.54.elf`，binman 嵌进 u-boot.itb | rkbin | 闭源 blob |
| U-Boot proper | 主线 + 十发板级补丁 | 咱们的 uboot 树 | 开源 |

表里的分工咱们要看仔细：主线 SPL 是开源的，但它依赖的 DDR 训练和 ATF 还是 rkbin 的闭源 blob。这是当前所有把主线放在第一位的 Rockchip 板共有的诚实边界，上一章讲过的“主线纯度”的问题，在这里具体化成了两颗文件。

## 第 0 关：串口一无所有的 bootloop

### 症状

咱们把第一版 update.img 烧进 eMMC，上电之后的串口，看到的是这样一场循环：咱们看到 DDR 训练好好的、16GB 点亮，rkbin 的那颗 `rk3588_spl` v1.14 也正常起来了，u-boot.itb 从 uboot 分区读了出来，咱们看它把五个节点逐个验完 sha256、全数通过，咱们又看到它打出 `Jumping to U-Boot(0x00800000) via ARM Trusted Firmware(0x00060000)`。结果主线 U-Boot 2026.07 一个 banner 都没出，板子立即复位、回到 DDR、把同一套流程再跑了一遍，咱们挂着一整夜，结果数到二十三次以上它还在原地转圈。

磨人的地方在于：出事的瞬间**一个字都打不出来**。报错、panic、banner 的输出统统没有，然后板子就沉默着重启了。无声的崩溃是没法“看报错”的，咱们只能靠分段排查去逼近现场。

### 方法论：听每一级的心跳

启动链上的每一级固件，活着的标志是它各自的那行串口输出。咱们把它们列成了一张一级一条的心跳表，谁的心跳出现了，就证明谁真正跑到了那里：

| 心跳输出 | 谁打的 | 证明谁活着 |
|---|---|---|
| `DDR ... fwver: v1.21` | DDR blob | BootROM 读到了 idblock，DRAM 训练完成 |
| `U-Boot SPL 2017.09 ...` | SPL | SPL 起来了，串口和基本时钟能用 |
| `## Checking hash ... OK` | SPL | u-boot.itb 读到了，校验过了 |
| `Jumping to U-Boot(0x00800000) via ARM Trusted Firmware(0x00060000)` | SPL | SPL 宣布交棒给 ATF |
| `NOTICE:  BL31: ...` | ATF | **BL31 真的跑起来了** |
| `U-Boot 2026.07-rc4 ...` | U-Boot proper | 交到非安全世界，正主登场 |

排查无声 bootloop 的手法就是：找到心跳表上**最后出现的那一行**，死的就是它的下一级。咱们要注意 `Jumping to U-Boot via ATF` 只是 SPL 打的一句宣言，离 ATF 活着的证据还差着一跳。这句宣言和真正的心跳差了一层，这正是本案最要紧的地方。bootlog 停在了“宣言”的那一行上，`NOTICE: BL31` 这行是从头到尾都没有出现过的，所以死的就是 **SPL 交给 ATF 的那一跳**。

这个方法咱们在后面的章节还会反复用到（内核章抓无声死机的取证装备、LCD 章的 VOP2 死机都是它的变体）：无声不等于无线索，每一级的心跳就是咱们的分界线。

### 根因：原厂 SPL 与 BL31 不同代

当时的组合是这样的：@0x40 的 idblock 里塞着的，是 rkbin 公开的 `rk3588_spl_v1.14`，而它就是原厂编译的 U-Boot SPL 2017.09，而 u-boot.itb 里 binman 嵌的是 BL31，具体的文件就是 `rk3588_bl31_v1.54.elf`。根因的完整推理记录在[工程日志第 49 篇](../../notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)里，咱们在这里把它说清楚：

- rkbin 的 `rk3588_spl_v1.14` 出厂**早于** BL31 v1.54。
- BL31 v1.54 这一代把自身的装载基址迁到了 0x60000，旧 SPL 的交棒逻辑还是按它当年配套的老基址去的。
- 于是 BL31 根本没被执行，安全世界没搭起来，自然也没有 `NOTICE: BL31`，板子复位重来，循环 23 次以上。

最骗人的一点是对照板给的假安全感：RK3568-atk 用“rkbin 的原厂 SPL 加主线 U-Boot”的组合在板上跑得好好的，咱们把这套组合照搬到 RK3588 上就翻了车。原因是 rkbin 的 `rk356x_spl` 没有这次基址迁移，而 `rk3588_spl` 是有的。**别把一块板的 rkbin 组合经验平移到另一块**，闭源 blob 的版本配套关系咱们只能逐板去验证。这跟 RK3506B 那卷 [rkbin 配套问题的 pitfalls 笔记](../../pitfalls/01-rkbin-spl-contracts.md) 里芯片标签、OP-TEE 哈希校验、FIT 布局三件事是同一类问题：rkbin 单方面定死的这类配套不会写进任何文档，所以咱们遇到了再对齐，或者就提前把它们逐项核对好了。

定位阶段的实验设计也值得咱们记上一笔。当时链上的嫌疑人有三个：原厂 SPL、主线 U-Boot 自身，还有排在最后的 BL31。判别实验的设计原则是**一次只换一级、其余全不动**，咱们当时的做法，是把 @0x40 的 idblock 换成主线 binman 的 `idbloader.img`，DDR blob 是不动的，SPL 从原厂换成了主线。如果 banner 出来了，凶手就是被换掉的那一级。如果换完之后咱们看到的还是 bootloop，嫌疑就得移交给主线 U-Boot 自身了。这是二分法在启动链上的应用，跟心跳表配合着用：心跳表告诉你死的是哪一级，判别实验告诉你换了它行不行。最终的修复（下一小节），正是这次的“换 SPL”实验换出来的结果。

### 解法：spl_source=mainline

修法落在 board.yaml 的 rkbin 段上，咱们加的就是那一行 `spl_source: mainline`。效果是 pack-loader 不再用 rkbin 的 `rk3588_spl_v1.14`，改用 build-uboot 刚编出来的 `u-boot-spl.bin`（主线 SPL，跟 BL31 v1.54 是同代配套的）。无论 idblock 走 boot_merger 打包、还是直接把 binman 的 `idbloader.img` 写到 0x40，里面的 SPL 都是主线编译出来的，DDR blob 仍是 rkbin 的。

修复后的链，咱们从头到尾念一遍：BootROM 读的是 idblock（rkbin DDR init 加上**主线 SPL**），idblock 交棒给 BL31 v1.54（这时 `NOTICE: BL31` 就出现了），最后就落到了 U-Boot proper 上。其实翻 U-Boot 官方文档就知道，RK3588 的推荐流程本来就是这个形态：**rkbin DDR 当 TPL + 主线 SPL + binman**，跟咱们现在的链一模一样。绕的这段弯路的教训浓缩成一句：SPL 与 BL31 必须同代，诊断就看 bootlog 里 `NOTICE: BL31:` 的有无。

修复之后 rkbin 段的全貌长这样（节选自 board.yaml），读者复现时逐行对齐即可：

```yaml
rkbin:
  blob_subdir: bin/rk35
  spl_source: mainline                  # CRITICAL: vendor rk3588_spl v1.14 + BL31 v1.54 base mismatch → bootloop; mainline SPL matches BL31 v1.54
  blobs:
    ddr: rk3588_ddr_lp4_2112MHz_lp5_2400MHz_v1.*.bin   # LP4+LP5 combo; glob picks rkbin default. DDR-fail → switch to lp4_1848/lp5_2112 glob.
    usbplug: rk3588_usbplug_v1.*.bin
    spl: rk3588_spl_v1.*.bin            # matches v1.14 (unused under spl_source=mainline, but resolved for loader ini / fallback)
    bl31: rk3588_bl31_v*.elf            # ATF, embedded into u-boot.itb by binman
```

`spl_source: mainline` 那行注释里写着整个事故的名字（base mismatch，一路演变成了 bootloop），这行字是踩过的人给下一个动这行的人留的话，一点都不是事后补的装饰。DDR 的 glob 也留了后手：万一某个批次的内存训练不过，备选降频档是 lp4_1848/lp5_2112 的组合包，咱们把 glob 换掉就行，脚本是不用动的。

## 串口波特率与 autoboot

bootloop 过了之后，U-Boot 能停在提示符了，接下来咱们把它调成本章收工该有的样子：串口全程可读、上电自动进内核。用到的补丁有三个，外加一次咱们自己挖出来的回归。

### 115200 的来龙去脉（0002：一行 defconfig 改波特率）

上游 `evb-rk3588_defconfig` 里默认的 `CONFIG_BAUDRATE=1500000`，是 Rockchip EVB 的习惯值。topeet 板的串口链路全链都是 115200：DDR blob 用 rkbin 的 `ddrbin_tool` 改了参数（`uart baudrate=115200`，这个工具认的只有 115200/1500000 两档），内核侧的 console 也定在 115200，内核那章配内核命令行的时候，咱们会再对上这个数。U-Boot 要是停在了 1500000，BL31 交班之后的串口就是满屏乱码，看着像挂了，其实板子活得好好的。

咱们要动的 0002 就是一行 defconfig：`CONFIG_BAUDRATE=115200`。

这个补丁本身是乏善可陈的，值钱的是它诞生的过程。最初这行改动是源码树里一处**没提交的 dirty 改动**（git 里还没落成提交的散改），后来做别的补丁时一句 `git reset --hard` 把它冲掉了，defconfig 就悄悄回到了 1500000，重编之后咱们把它部署到板子上，BL31 之后打出来的全是乱码。当时的诊断手法值得咱们记下来：

```
$ strings u-boot.itb | grep baudrate=
baudrate=1500000        ← 该是 115200，镜像自己招了
```

咱们不用串口猜，问镜像就行了。这个教训也够直白的：third_party 树里任何没提交的 dirty 改动，咱们要么 stash、要么落成补丁，跑 `git reset --hard` 之前也得看一眼 `git status` 的输出。这行 115200 从此以正经补丁的身份活在 series 里。

### boot_targets 收窄（0001）与直接 bootcmd（0003）

背景咱们得交代清楚：这块板的 boot 分区是**裸分区**。forge 是把 kernel FIT（boot.img）整分区写进 eMMC 的，文件系统是完全不带的，所以 U-Boot 没法把它当文件加载，只能靠放在 rootfs 分区（ext4）里的 boot.scr 做跳板：boot.scr 被 source 之后，由它对 boot 分区做原始的 `mmc read` 再接上 `bootm`。这个设计写在 boot-emmc.cmd 的头注释里。

autoboot 的第一发补丁是 0001，把 boot_targets 砍到了只剩 eMMC。默认的 `boot_targets` 来自 `rockchip-common.h` 的宏，展开之后 `"mmc1 mmc0 nvme scsi usb pxe dhcp spi"` 这一串就出现了。这块板走到尾巴上的 pxe/dhcp 就过不去，bootflow 卡在了 BOOTP 超时上干等。BOOTP 等待窗口里自协商跟超时的次序咱们当时没查下去，见到的错误码是 -110/-4。咱们在 `evb_rk3588.h` 里把它砍到只剩 `"mmc0"`，这里的写法有个讲究：`#define BOOT_TARGETS "mmc0"` 必须放在 `#include <configs/rk3588_common.h>` **之前**，靠 rockchip-common.h 里的 `#ifndef` 保护采纳这个值，这套 `#ifndef` 采纳写法是 Rockchip 板的通用惯用法。

镜像烧好之后咱们上电验证，结果是**不够**的。bootflow 是不卡 BOOTP 了，但串口里 `bootflow scan` 扫完报的是 “No more bootdevs”，扫出来的 bootflow 是 0 个，script bootmeth 还是命不中的，是 mmc 0:3 上的 boot.scr，咱们又落回了提示符。0001 只砍了超时，命中问题是没有解决的。哪一层不匹配咱们没有继续深挖，咱们就直接上第二发：0003（把启动命令写死进 defconfig），把已经手动验证能跑的序列固化成 `CONFIG_BOOTCOMMAND`。在那之前每次上电咱们都得在提示符下手动敲这两句：

```
=> load mmc 0:3 ${scriptaddr} /boot/boot.scr
=> source ${scriptaddr}
```

0003 做的事，就是把咱们手动敲的那两句固化下来：

```
CONFIG_BOOTCOMMAND="load mmc 0:3 ${scriptaddr} /boot/boot.scr; source ${scriptaddr}"
```

`scriptaddr=0x00c00000`（rk3588_common.h 的默认值）。bootstd 原本的默认 bootcmd 是 `bootflow scan -lb`，defconfig 显式设了 `CONFIG_BOOTCOMMAND` 就把它盖掉了（依赖的是 `USE_BOOTCOMMAND=y`，这个默认是开着的）。至此 0001 在咱们手里就成了摆设，但留着是无害的，boot_targets 收窄本身仍是正确的防御。

boot.scr（源文件 boot-emmc.cmd）干的事，咱们在串口里看到的是这样的：

```
mmc dev 0
setenv bootargs console=ttyFIQ0 root=/dev/mmcblk0p3 rw rootwait
mmc read 0x08000000 0x6000 0x20000
bootm 0x08000000
```

有两个数字值得咱们记下来。`0x6000` 是 boot 分区的起始扇区，`0x20000` 是 64MiB 的分区长度，这套布局的出处是 parameter-emmc-topeet.txt（idbloader 裸放在 0x40，uboot 的分区在 0x4000，boot 的分区在 0x6000，rootfs 的分区在 0x26000）。`0x08000000` 是 kernel FIT 的暂存地址，咱们特意不用 `kernel_addr_r`（0x02000000）：FIT 若装在 0x02000000，bootm 把内核子镜像往它自己的加载地址拷的时候，会把还没解完的 FIT 覆盖掉，那就直接崩了。这个地址的选择，跟 RK3506B 那卷讲的 bootm 自覆盖，是同一个知识点的 RK3588 版。

还有一处板级差异容易被 RK3568 的经验带偏，其实就出在 root 设备号上。topeet 的 eMMC 在内核里枚举成 `mmcblk0`，root 设备写的是 `/dev/mmcblk0p3`，而 RK3568-atk 对应的是 `mmcblk1p3`。要是咱们照 RK3568 的旧经验写 `mmcblk1p3`，内核就会永远停在 `Waiting for root device` 不动了。U-Boot 侧的 eMMC 恒为 `mmc 0`，两边说的其实是同一块存储，只是编号体系不一样而已。

0001、0002、0003 都齐活了，autoboot 就一路自动跑到 systemd 了，不用咱们再手动 `source`。

## rockusb Loader 模式：主线自带，只是没启用

接下去是后半场的主戏，咱们把话题挪到烧写迭代的速度上。

### 为什么要 Loader 模式

Rockchip 的板子进 USB 烧写状态有三条路：MaskROM（BootROM 原生的下载模式，板上什么固件都不需要）、Loader 模式（板上的固件自己起一个 rockusb 服务，等 PC 来烧）、以及系统跑起来之后的用户态工具。原厂 SDK 时代最常用的迭代姿势是 Loader 模式：按住音量上键上电，烧写工具认出的是“LOADER 设备”，咱们就能单分区烧写（只换 uboot 或只换 boot），不用整包重刷了。讯为官方手册《iTOP-3588 开发板快速烧写手册 v1.7》写的进法就是这个手势：按住 VOL+ 不松手，咱们再按电源上电，等工具提示发现新设备了再松手。

咱们换到主线栈这边，原本的 Loader 模式就没有了：MaskROM 还在（那是 BootROM 的硬件行为，跟固件倒是无关），但是 Loader 模式需要固件主动配合，主线的 defconfig 没开它。两条路的差别，咱们从 PC 侧的命令序列一眼就能看出来。走 MaskROM 迭代一轮 U-Boot 是这样的：

```
rkdeveloptool db MiniLoaderAll.bin        # 先灌下载 loader 进 DRAM（每次上电都得来一遍）
rkdeveloptool wl 64 out/rk3588-topeet/idbloader.img
rkdeveloptool wl 16384 out/rk3588-topeet/u-boot.itb
rkdeveloptool rd
```

走 Loader 模式的话，板子自己的固件就在 USB 上蹲着，`db` 那一步就整个消失了，插上线就能直接 `wl` 了。次数多了，这就是几十秒和几秒的差别，而且是咱们每天要重复几十次的动作。于是咱们决定：把主线 U-Boot 里的 rockusb 开出来。

预研核实过的事实让人踏实：**主线 U-Boot 的 rockusb 实现是完整的**（`cmd/rockusb.c` + `f_rockusb.c`），原厂的烧写协议都实现了，缺的只是配置和几处兼容性。但是把主线 rockusb“开出来”这件事背后藏着的，是一条五层深的启用链，咱们一层一层看。

### 第一层：gadget 开关与那颗编译空壳雷（0004/0005）

第一发是 0004（rockusb 的 defconfig 补丁），把 gadget（USB 设备模式的协议栈，板子在它上面充当被电脑操作的“设备”）栈打开了。五行配置与主线 `generic-rk3588_defconfig` 自带的 gadget delta 完全相同（同 SoC 的现成模板，咱们逐行对照核实过了）：`USB_GADGET`、`USB_GADGET_DOWNLOAD`、`USB_FUNCTION_ROCKUSB`、`CMD_ROCKUSB`，还捎带了 `CMD_USB_MASS_STORAGE`（BOOT_UMS 分支要用）。

这五行里埋着的，是第一颗 Kconfig 交互式的雷：开了 `USB_GADGET_DOWNLOAD`，`USB_FUNCTION_FASTBOOT` 就默认翻成了 y，拖出来一个**没有默认值**的 hex 符号 `FASTBOOT_BUF_ADDR`，于是 syncconfig 就停下来等人工输入了。后台构建任务的 stdin 是空管道，它就一直那么等下去了。主 make 挂了 8 分钟，CPU 的执行时间是零，产物的 mtime 也一直没动，这就是它卡在交互提问上的直接证据。所以 defconfig 里那行 `# CONFIG_USB_FUNCTION_FASTBOOT is not set` 是一条实打实的功能行，“差五行”实际差的是六行。教训是具体的：后台构建要是挂死了，咱们拿 `ps -o time` 看进程，再查 syncconfig/oldconfig 这一类的工具，八成是它在跟咱们交互提问。

0004 里隐藏最深的一行是 `CONFIG_ROCKCHIP_BOOT_MODE_REG=0xfd588080`。这个符号的默认值是 0，而 boot_mode.c 的写法是 `#if (CONFIG_ROCKCHIP_BOOT_MODE_REG == 0)` 时把 `setup_boot_mode()` 整个编译成空壳。也就是说不开它的话，后面所有按重启模式分流的 case（FASTBOOT/UMS）从来都是死代码，主线自己的 rk3588 板（jaguar/tiger）全是显式 `=0x0`，把它掐死的。0xfd588080 这个值是咱们从原厂的 rk3588_defconfig 里取的，对应的就是“重启模式寄存器”的物理地址，后面咱们在内核侧还要回来找它的。

0005（OTG 口的设备树补丁）解决的是物理层，咱们要回答的问题只有一个，rockusb gadget 到底该跑在哪个 USB 口上？咱们要给的答案是 OTG 口，但是 dts 里得把 `usb_host0_xhci` 定成 `dr_mode="peripheral"`、`maximum-speed="high-speed"`、`phys=<&u2phy0_otg>`。原因是 RK3588 那颗组合 USB3/usbdp PHY 天生就没有外设模式的支持，gadget 只能走 USB2 的 OTG phy，速度就封顶在 high-speed 了。这个形态咱们照的是主线 u-boot 自家 `rk3588-generic.dts` 的写法。好处是实操层面的零额外成本，跟 MaskROM 烧录的是同一个口、同一根线。

### 第二层：reboot loader 的两半（0006 + 内核侧 0035）

原厂有个好用的小功能：咱们在 Linux 里 `reboot loader`，板子重启之后就不进系统了，直接就蹲进了 Loader 模式等烧写。主线 `setup_boot_mode()` 的 switch 里 FASTBOOT 和 BOOT_UMS 两个 case 都在，唯独 BOOT_LOADER 被砍了。0006（补回 BOOT_LOADER 分支的补丁）照邻居的形态补回：

```c
case BOOT_LOADER:
	debug("%s: enter rockusb!\n", __func__);
	env_set("preboot", "setenv preboot; rockusb 0 mmc 0");
	break;
```

机制是这样的：内核重启前把一个魔数写进 0xfd588080，U-Boot 在启动早期又把魔数读了出来，分流也就看这个值了。所以这功能天然有**两半**，U-Boot 的这一半是 0006，内核的那一半是给 topeet 设备树补 `pmu0_grf@fd588000` 加 reboot-mode 子节点（偏移取的是 `offset=<0x80>` 也就是 fd588000+0x80=0xfd588080），这个地址跟 0004 读的那个寄存器是同一个。那是内核补丁序列里的 0035，到内核那章咱们还会再见到它。主线 `rk3588-base.dtsi` 里压根就没有这个节点的位置，必须咱们自己补，原厂的 rk3588s.dtsi 是原型。

用户态的触发还有个小弯：systemctl 和 busybox 的 reboot 都不透传 mode 字符串，咱们得用裸系统调用才行（板上 Python 一行流就是干这个的）：

```python
# RESTART2 = 0xa1b2c3d4, arg = "loader"
import ctypes; libc = ctypes.CDLL(None)
libc.reboot(ctypes.c_int(0xfee1dead), ctypes.c_int(672274793),
            ctypes.c_int(0xa1b2c3d4), ctypes.c_char_p(b"loader"))
```

（咱们还有个保底方案，走的是 `devmem 0xfd588080 32 0x5242C301` 直接写寄存器再普通 reboot 的路子，不依赖内核的节点）

### 第三层：preboot 设了，却没人执行（0007）

到这里链路看着是齐了，其实埋着一颗最阴的雷。而且当时的验证记录一度宣告“验证通过”，后来才查明那是个误判：那晚确认的只是烧录链路通了，`reboot loader` 本身是从没真正工作过的。这段排查值得咱们慢慢讲，因为它说的“环境变量设了，不等于有人执行”就是最标准的教材。

0006 的实现是 `env_set("preboot", "... rockusb 0 mmc 0")`，往 preboot 环境变量里塞了一条命令。但是 preboot 这个变量是 U-Boot 的 main_loop() 在进 autoboot 流程前执行的特殊钩子，而 main.c 里执行它的代码包在 `IS_ENABLED(CONFIG_USE_PREBOOT)` 里。这个符号不开的话，main_loop 是根本不看 preboot 的。咱们看 evb-rk3588_defconfig，从头到尾都没设过它的。于是 0006 的 BOOT_LOADER 分支一直在给一个永不被执行的变量赋值，`reboot loader` 在这一环上是从未真正工作过的。

头两轮咱们把镜像烧进板子去验证，音量键的配置都配齐了，可按 vol-up 上电却是正常开机、不进 Loader 的。根因是排查到这里才定位出来的：`CONFIG_USE_PREBOOT` 压根没开。定位讲究的是三处证据都落在实处：产物 .config 里该符号确实是 n、`main.c` 里执行 preboot 的代码确实包在 `IS_ENABLED(CONFIG_USE_PREBOOT)` 门槛里，defconfig 是从来没设过它的。三处都对上了，咱们才敢认这个定位。修复进了 0007（音量键补丁）的 v3，defconfig 里补上了 `CONFIG_USE_PREBOOT=y`。到了这一步，`reboot loader` 与按键的两条路都同走 preboot 这辆车了，车才真的发动了起来。

留给读者的一道自查题：如果你的补丁往 `preboot`、`bootcmd`、`bootdelay` 这类“元变量”里写东西的话，咱们就得确认消费它的代码路径在编译配置下真实存在。变量写进去了还不算完，得有真的代码来消费它。

### 第四层：音量上键进 Loader（0007）

Loader 模式的入口本来该有个物理按键。咱们把一个干扰项排除掉，就是板上的那个“Loader/Recovery 拨码开关”，它是救不了咱们的。板上验证是定性过的：按住它复位之后，串口连 DDR blob 的 banner 都没出来，BootROM 压根没加载 idblock 就直接进了 USB 下载。它是 BootROM 级的硬件 strap（芯片引脚采样），任何固件（原厂的也罢主线的也罢）都拦不住它，而它通向的是 MaskRom 不是 Loader。配套的逆向也做了：反编译 DDR blob，数了 138 条 movz/movk 加全部字面量，SARADC 和 GPIO 的地址一次都没出现，DDR blob 物理上读不了任何按键，它在整个流程里只是 TPL 侧的下载中继，做不了决策。

所以按键之路只剩一条，原厂留了另一个入口给咱们：音量上键。它挂在 SARADC（一种逐次逼近型的模数转换器，Rockchip 拿它做按键电压梯）的通道 1（ch1）上，四键梯的最底一档，电压是低于 17mV 的，在 1.8V 满量程下的 ADC 原始读数约 39。主线 U-Boot 本来就有 `rockchip_dnl_key_pressed()` 这个现成的开机按键检测，0007 做了四件事把它接活：

1. **窗口从 30 放宽到 128**：上游写死的 30 会把 raw 39 的音量上键裁掉，128 放进来，同时离上一档（音量下键，417mV，约 raw 949）还有 7 倍余量，不会误触。
2. **设备查找补 compatible 匹配**：rk3588 的设备树节点叫 `adc@fec10000`，`saradc` 只剩标签名，代码里那个只认名字前缀的匹配永远找不到设备，梯子根本没被采样。
3. **命中后改道 Loader**：上游的默认行为是热复位进 BootROM 的下载（那是 MaskRom），改成跟 0006 的 BOOT_LOADER 一样给 preboot 塞 `rockusb 0 mmc 0`。
4. **随行配置**：`CONFIG_ADC`、`CONFIG_SARADC_ROCKCHIP`、`CONFIG_USE_PREBOOT`（上一层的修复就在这发里）、`CONFIG_CMD_ADC`（板面诊断命令，`adc single adc@fec10000 1` 能实测梯子原始值）。

saradc 节点的 dts 写法，咱们照的是主线的 rk3588-rock-5b-u-boot.dtsi。原厂手册里的“按住 VOL+ 上电进 Loader”的手势，就这样在主线栈上原样复活了。

### 第五层：让烧写工具认出 LOADER（0008/0009/0010）

按键修好了、rockusb 也能起了，咱们在串口里就能看到：

```
download key pressed, entering Loader mode (rockusb)
```

然后是长久的安静。注意 rockusb 的服务循环是不打字的，静默蹲守是它的正常状态，别把它当成死机了。但是 PC 侧的 RKDevTool，这时候把设备标成的是“MASKROM设备”。协议明明是在正常服务的，为什么身份就不对呢？接下来咱们用三发补丁一层一层修身份，每一层都是工具的一个新判定维度，排查全程咱们收在[音量键排查全记录（notes/loader/002）](../../notes/loader/002-2026-11-02-volup-loader-mode-saga.md)里。

**0008（PID 补丁）**管的是身份的第一层，RKDevTool 靠的就是 VID:PID 来认设备。rockusb 的 Kconfig 默认 PID 0x350b，但它是 BootROM 给 MaskRom 模式用的 PID。原厂那个被工具叫作 LOADER 的 usbplug 固件，用的是 2207:300a。这个值是咱们从 `out/MiniLoaderAll.bin` 偏移 0x26846 处的设备描述符里翻出来验证过的。补上的这一行 `CONFIG_USB_GADGET_PRODUCT_NUM=0x300a`，让工具立刻改口认成了 LOADER。但是 Windows 读到 300a、绑上 rockusb.sys 之后驱动启动报 code 10（STATUS_NO_SUCH_DEVICE），还有下一层要咱们去修。

**0009（bcdUSB 补丁）**管的是设备的分类：Rockchip 全家的烧写工具（RKDevTool、upgrade_tool、rkdeveloptool）要区分 MaskRom 和 Loader 设备，看的是 bcdUSB（USB 设备描述符里报告规范版本的字段），0x0201 就代表的是 Loader。这个判定不是咱们逆向猜出来的，原厂 composite.c 的注释原话就写着 `Rockchip upgrade tool use bcdUSB (0x0201) field distinguishing maskrom or loader device`。而主线 composite 驱动在 USB2 路径上无条件把 bcdUSB 强制成 0x0200，于是就算 PID 换对了（0008），工具按 0x0200 一判的话，又把设备标回了 MaskRom。咱们的补丁让 rockusb 函数在 USB2 上保持 0x0201。板上验证进了一步：设备认成 LOADER 了，但是 Windows 的驱动还是起不来，报的还是 code 10。

**0010（BOS 补丁）**补的是能力应答：bcdUSB 报 0x0201 就背上了应答 BOS 描述符的义务（BOS 的全称是 Binary Device Object Store，USB 2.1 起规范里就有的设备能力汇总描述符）。Windows 8 及以上的系统在枚举时就会发 GET_DESCRIPTOR(BOS)，主线的代码却只在 SuperSpeed 链路上应答它，USB2 的链路上就直接 STALL，rockusb.sys 启动期的这个请求失败，就是 code 10 的根因。原厂 composite.c 里带着一模一样的绕过方案注释，说明原厂当年也在同一块石头上绊过的。咱们的补丁让 rockusb 在 USB2 上也答 BOS，但只回一个 12 字节、bmAttributes=0、什么都不声称的 USB2-Extension cap，不谎报 LPM/BESL 这些 gadget 交付不了的能力。这里还有个比单纯复刻原厂多想了一步的细节：主线 `bos_desc()` 的 SuperSpeed cap 组挂在 `gadget_is_superspeed()` 上，而这个函数判的是**驱动能力**（dwc3 天生支持 SuperSpeed），看不出来链路此刻跑的是高速还是低速，直接放行的话，就会在 high-speed 的链路上谎报 SS 能力。0010 就被咱们改成了按链路速度分流。

这三发的身份补丁，是一轮轮把镜像烧进板子验证逼出来的，每轮都死在一个新的层上：头一回是被 USE_PREBOOT 挡在了门外（第三层的那颗雷），过了这关又被标成了“MASKROM设备”（PID 的问题），换对了 PID 又碰上 code 10（bcdUSB 的问题），补上 BOS 才算了结。咱们单独看哪一层都想不到，连起来看就是一件事：把一个 USB 设备装扮成原厂工具生态认的 Loader，工具的每一道检查（执行开关、身份、分类、能力应答）都得过，一项都少不了。

### 烧写侧：Loader 模式下烧什么

咱们点亮 Loader 模式之后，PC 侧的烧写姿势是这样的（RKDevTool 的图形界面认了 LOADER 设备之后就单分区烧写，命令行走的是 rkdeveloptool）：

```
rkdeveloptool ld                              # 列出 Maskrom/Loader 设备
rkdeveloptool wl 64 out/rk3588-topeet/idbloader.img    # LBA 64 = 0x40，BootROM 读的 idbloader
rkdeveloptool wl 16384 out/rk3588-topeet/u-boot.itb    # LBA 16384 = 0x4000，uboot 分区
```

迭代 U-Boot 就是这两发 `wl` 的事，几秒钟就凑齐了一轮，不用整包的重刷，咱们也不用回 MaskRom 走 `db`。两个 LBA 也不是随便挑的：64 就是 0x40（BootROM 读 idblock 的固定扇区），16384 对上的就是 0x4000，正对主线 U-Boot 的 `CONFIG_SYS_MMCSD_RAW_MODE_U_BOOT_SECTOR=0x4000`。SPL 在 eMMC 的原始模式里就是按这个扇区找 u-boot.itb 的，parameter-emmc-topeet.txt 的注释里逐项写着这套扇区对应关系。全盘镜像的话用 `wlx <分区名>` 按名写就行了。网络那章的 tftp+nfs 免烧录引擎是更快的内核迭代姿势，但是 U-Boot 自身的迭代只能靠烧写，这就是本章把 Loader 模式当主戏打的理由。

有一个已知的边界，咱们诚实记在这里：主线的 f_rockusb 还有若干原厂的私有命令没实现（比如 READ_FLASH_INFO 会回 cb_not_support），本次的 RKDevTool 认设备加烧写流程没碰上它们。日后要是有哪个升级动作卡住了，按报错抓包补上最小的命令就行。

## U-Boot 侧补丁序列总表

十发补丁按 series 的顺序排（series 文件里有每发的决策注释），各自的情况咱们逐发看：

| 补丁 | 动什么 | 为什么存在 |
|---|---|---|
| 0001 boot-targets | `evb_rk3588.h` 里 `BOOT_TARGETS="mmc0"` | 默认 boot_targets 尾巴上的 pxe/dhcp 把 autoboot 卡死在 BOOTP 超时（GMAC PHY 自协商坏，-110/-4），砍到只剩 eMMC。部署到板端验证证明只砍超时不够，0003 上位后此补丁成为摆设但无害 |
| 0002 baud | defconfig `CONFIG_BAUDRATE=115200` | 上游默认 1500000，与 topeet 全链 115200（DDR blob + 内核 console）打架，BL31 交班后满屏乱码 |
| 0003 bootcommand | `CONFIG_BOOTCOMMAND` 直载 boot.scr | bootstd 默认 `bootflow scan -lb` 在板上命不中 mmc 0:3 的 boot.scr，把已验证的手动序列写死，autoboot 直通内核 |
| 0004 rockusb defconfig | gadget 五行 + FASTBOOT 显式关 + `BOOT_MODE_REG=0xfd588080` | 打开主线 rockusb。BOOT_MODE_REG 默认 0 会把 `setup_boot_mode()` 编译成空壳，重启模式分流全是死代码。FASTBOOT 那行是防 syncconfig 交互挂死 |
| 0005 OTG dts | `usb_host0_xhci` 定成 peripheral + USB2 phy | 组合 usbdp PHY 无外设模式，gadget 只能走 u2phy0_otg，封顶 high-speed，与 MaskRom 烧录同口同线 |
| 0006 BOOT_LOADER | boot_mode.c 补 BOOT_LOADER case | 主线把 `reboot loader` 的分支砍了，照邻居 FASTBOOT/UMS 补回，preboot 进 rockusb。内核侧另一半是 0035 的 reboot-mode 节点 |
| 0007 vol-up 按键 | ADC 三件套 + `USE_PREBOOT` + 按键窗口 30→128 + compatible 匹配 + dnl 改道 Loader | 音量上键进 Loader。USE_PREBOOT 不开则 main_loop 不执行 preboot，0006 从未生效，误判的修复就在这发里 |
| 0008 PID | `USB_GADGET_PRODUCT_NUM=0x300a` | 0x350b 是 BootROM MaskRom 模式的 PID，RKDevTool 按 VID:PID 认设备会标“MASKROM设备”。300a 从 MiniLoaderAll.bin 的描述符里验证而来 |
| 0009 bcdUSB | composite.c 对 rockusb 保持 0x0201 | Rockchip 工具按 bcdUSB 分 MaskRom/Loader（原厂注释原话），主线在 USB2 强制 0x0200 会把身份改回 MaskRom |
| 0010 BOS | composite.c 在 USB2 链路也答 BOS | 0x0201 有应答 BOS 的义务，Windows 8+ 枚举即问，STALL 会让 rockusb.sys 起不来（code 10）。BOS 内容只回不声称任何能力的 12 字节 cap，按链路速度分流 |

跟内核那章的呼应：U-Boot 这十发主打的是“配置与对齐”，真正的板级新代码（topeet 设备树从原厂 5.10 SDK 移植主线、PMIC、显示管线）都在内核侧的补丁序列里。0004/0006 在内核世界的另一半，就是 reboot-mode 节点的那一发 0035。咱们把两份 series 放在一起读，看的就是“一个功能横跨 U-Boot 与内核”的时候补丁该怎么拆。

## 成功长这样

收工的板子，从上电到把内核交出去的全程，串口里是这样的（截自章末档案里的收工 bootlog，咱们一个字都没合成）：

```
U-Boot SPL 2026.07-rc4-00043-g5ca1a73c7d30-dirty (Jun 12 2026 - 14:45:32 +0000)
Trying to boot from MMC1
## Checking hash(es) for config config-1 ... OK
## Checking hash(es) for Image atf-1 ... sha256+ OK
## Checking hash(es) for Image u-boot ... sha256+ OK
NOTICE:  BL31: v2.3():v2.3-964-g8319968f5:derrick.huang, fwver: v1.54
...
U-Boot 2026.07-rc4-00046-g9423cafd1d54 (Jul 31 2026 - 13:57:03 +0000)

Model: Rockchip RK3588 EVB1 V10 Board
SoC:   RK3588
DRAM:  16 GiB
MMC:   mmc@fe2e0000: 0
Hit any key to stop autoboot: 0
1895 bytes read in 12 ms (153.3 KiB/s)
## Executing script at 00c00000
switch to partitions #0, OK
mmc0(part 0) is current device
MMC read: dev # 0, block # 24576, count 131072 ... 131072 blocks read: OK
## Loading kernel (any) from FIT Image at 08000000 ...
```

咱们逐行来核对。开头那行 `U-Boot SPL 2026.07-rc4` 是主线自己的 SPL，bootloop 那部分的修复正在生效。`NOTICE: BL31 ... fwver: v1.54` 是那颗当时死活不肯出现的心跳，现在每次上电都打得出来了。`DRAM: 16 GiB` 是 rkbin DDR blob 点的四通道 LPDDR4X。`Hit any key to stop autoboot: 0` 这行打出来之后是没人去按键的，接管的是 `CONFIG_BOOTCOMMAND`，读进来的 1895 字节正是 boot.scr，而 `00c00000` 就是 scriptaddr，MMC 从 24576（0x6000）扇区读出的 131072 块（64MiB），把裸 boot 分区整段搬进了 0x08000000，bootm 再把内核从 FIT 里放了出来。而这一切跑在板上的，是十发补丁之后还多了 rockusb 能力的 U-Boot：咱们按住音量上键上电，它随时就可以变成一个等着烧写的 LOADER 设备。

底座稳了，下一章要往上面放正主了：主线 Linux v7.3.1，topeet 的板级设备树怎么从原厂 5.10 SDK 一路搬进主线，首次启动又会卡在哪里？咱们下一章见。

## 档案与证据

正文为了可读，把构建指纹和过程记录的指针从论述里拿掉了，咱们需要对照原始证据的时候看这里：

- U-Boot 源码基线：2026.07-rc4，pin 在提交 `5ca1a73c`（board.yaml 的 `sources.uboot` 段），十发补丁从这个基线重放。
- autoboot 三补丁（0001/0002/0003）齐活那轮 update.img 的 MD5 前缀：`8520c77f`。
- 触发 bootloop 的第一版镜像里，u-boot.itb 中 u-boot 本体（Image 0，818288 B）的 sha256 前缀是 `e0f0a73688`（dumpimage 记录，见 bootloop-analysis）。
- bootloop 原始 log：[202607271337.txt](../../logs/rk3588/202607271337.txt)（212 行），逐级分析见 `logs/rk3588/bootloop-analysis.md`。
- 收工 bootlog：[202608011826.txt](../../logs/rk3588/202608011826.txt)（“成功长这样”一节的出处）。
- USE_PREBOOT 误判与音量键排查全记录：`notes/loader/001-2026-11-02-ddrbin-dnl-re.md`（§8）与 `notes/loader/002-2026-11-02-volup-loader-mode-saga.md`。
- 其余过程记录：`notes/43`（波特率与 autoboot）、`notes/49`（bootloop 根因）、`notes/50`（首次启动的 root 设备号与波特率）、`notes/123`（rockusb 启用链预研）。
