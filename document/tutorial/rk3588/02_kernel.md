# Linux 内核移植：把原厂 SDK 的设备树翻译成主线语法，一路追到 v7.3.1

> [上一章](01_uboot.md) 把主线 U-Boot 稳在了 `=>` 提示符，还顺手点亮了 rockusb Loader 模式。那咱们这一章就往底座上放正主：主线 Linux。RK3588 在主线享受的是旗舰待遇，SoC 级的设备树、驱动一应俱全，所以咱们真正要干的只有一件事，就是把迅为原厂 SDK 5.10 里的板级 dts 翻译成主线语法，最后咱们给它起名叫 `rk3588-topeet`。事情咱们听着不多，路上其实有两场硬仗：一场看着像串口控制台（console）挂了，咱们查下来真凶是 CPU 调压器。另一场是收官前的 v7.3.1 rebase（把补丁序列重新落到新内核版本上）。另外咱们还得交代一句，这块板有个咱们领教过的狠脾气，有些 bug 咱们看不到报错，直接就无声卡死（hard-lock）了，所以咱们要在本章末尾把抓无声卡死的取证装备搭起来，LCD 章的 VOP2 硬锁就靠它破案。

版本口径咱们在这儿交代清楚，平台章讲的版本约定在这里落地：bringup（板子点亮初调）的里程碑，大多数是在 v7.1 上取得的，v7.3.1 是最后的收官升级。本章咱们按时间线走，咱们每走一步都注明当时的内核版本，v7.3.1 板验通过的部分就按通过写。

## 起点：主线是旗舰待遇，缺的只是这块板的 dts

咱们盘点一下家底。主线 Linux 对 RK3588 的支持是 Collabora 长期投入的重点，[board.yaml](../../../boards/rk3588-topeet/board.yaml) 的注释里就是这么定位的。SoC 级的 `rk3588.dtsi` 全套在树里，clk、pinctrl、sdhci、GMAC、VOP2、Panthor GPU 这些驱动全是主线的，板级 dts 咱们也数出一堆，evb1-v10、tiger-haikou 咱们都数在里头，toybrick、rock-5b 也收了。咱们还看到 7.3 在加新板，vicharak-axon、vaaman2 这些新面孔进来了，youyeetoo-yy3588 也进来了。这跟 RK3506B 那卷正好倒了个个儿：那边是“有驱动、连 SoC 级 dtsi 都没有”（[boot 教程第 3 章](../boot/03_kernel.md) 里咱们是这么记的），咱们这边是“什么都有，就是没有 topeet 这块板”。

所以 bringup 的第一阶段咱们干脆不写设备树，直接拿主线的 `rk3588-evb1-v10.dtb` 当 MVP（最小可用版本）DT 用（[kernel.config](../../../boards/rk3588-topeet/kernel.config) 头注释记录了这个阶段）。topeet 这块板本质是 EVB 的亲戚，串口、eMMC 这些大件位置咱们比对过都相同，所以 MVP 阶段够咱们用。真正要补的，是把原厂 5.10 SDK 里的 `topeet-rk3588-linux.dts` 移植成主线的 `rk3588-topeet.dts`，这件事咱们落成补丁 [0002](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch)，一共 817 行板级 dts、外加一行 Makefile 接线就交付了。

咱们把 RK3506B 和 topeet 的起点摆在一起看，分工一目了然：

| | RK3506B（boot 卷） | RK3588 topeet（本卷） |
|---|---|---|
| SoC 级 dtsi | 主线没有，要自己补 | `rk3588.dtsi` 主线全量在树 |
| 驱动 | clk/pinctrl 有，缺板级驱动场景 | 全主线，一行不用写 |
| 板级 dts | 自己写（参照原厂稀疏描述） | 从原厂 SDK 5.10 全量翻译 |
| 咱们写的内核代码 | sfc DLL 调谐移植 | FIQ debugger、rk860x、I²C 恢复的移植 |
| 工作重心 | 补描述、补驱动能力 | 翻译语法、对齐行为、抓无声死 |

版本与构建的配置全在 [board.yaml](../../../boards/rk3588-topeet/board.yaml) 的 kernel 段里，base pin 定在 `v7.3.1`（`sources.linux.ref` 同步指到 kernel.org 的 stable 仓），`dtb_name: rk3588-topeet`，`base_defconfig: arch/arm64/configs/defconfig`。板级差异咱们再叠一个 `kernel.config` fragment，它是叠在 base 之上追加配置用的片段文件，这套策略咱们下一节细讲。

## 方法论：原厂 dts 的三堆分拣

原厂 dts 咱们要搬进主线，但咱们不整块复制、也不逐行重写，所以分拣成三堆，每堆的处理办法就写在下面。咱们这套方法论的原材料是 notes/50 的首次移植记录和 0002 这发补丁本身，[notes/68](../../notes/68-2026-08-26-rk3588-real-dtb-full-port.md)、[notes/69](../../notes/69-2026-08-27-rk3588-real-dtb-ubuntu-merge.md) 后来又在仿真线上把同一份真板 DTB 给咱们完整跑通了，给咱们补了一条跨板教训。

**咱们第一堆的处理：原样保留。** 电压树这类纯硬件描述咱们查过主线语法一直没有变过，原厂怎么写主线就怎么收。rk806 PMIC 的完整 regulator 树，就是咱们从 `rk3588-fet3588-c.dtsi` 原样复制的，因为咱们查过原厂的 `topeet-rk3588-linux.dts` 之后发现，topeet 的供电拓扑跟 Forlinx OK3588-C 完全一致（单颗 rk806 挂 spi2、CPU/NPU 外置调压器），主线里已经有人把这套拓扑写规范了，那咱们就直接用。eMMC 的总线宽度、HS400 增强选通这些属性也属于这一堆。

**咱们第二堆的处理：翻译。** 语义还在、写法变了的那些部分，咱们挑几条实打实的差异：

- **compatible 字符串**。原厂 SDK 里 topeet 的板级 compatible 是 `rockchip,rk3588-evb3-lp5-v10`，这是 BSP 概念，主线不认。咱们的做法是起干净的 `topeet` 名字，第二级照例挂 `rockchip,rk3588`。U-Boot 的 rockchip 面板链就是按 compatible 匹配板子的，认领凭据就是这第二级。
- **中断细胞数**（interrupt cell，设备树里描述一条中断所占的 32 位单元个数）。主线 RK3588 的 GIC 用第四个 affinity 细胞。0002 里 fiq-debugger 节点的中断写法是 `interrupts = <GIC_SPI 423 IRQ_TYPE_LEVEL_LOW 0>`，末尾那个 0 就是第四细胞。这条差异在 notes/69 里咬过咱们一口：给 DTB 动态嫁接节点时中断写死三细胞，rk3568 上全绿、rk3588 上内核直接判畸形报 `IRQ index 0 not found`。两板同代码不同结果时，咱们就去数 binding 的细胞数。
- **原厂引用的 label 和 phandle**。原厂 dts 里引用的时钟、pinctrl 标签都要在主线 dtsi 里重新对一遍名，因为两棵树的节点组织和命名不完全一样。

**咱们第三堆的处理：换主线等价物、或者干脆删。** 原厂私有绑定咱们不能带走，咱们带走了也没人认。这块板上最大的三个是这些：

- **fiq-debugger**。原厂的调试口方案是私有的 `rockchip,fiq-debugger` 节点独占 UART2，主线没有对应驱动。咱们的选择不是换，是把原厂的那套 FIQ debugger 驱动移植进主线（补丁 0003，后面细讲）。
- **reboot-mode**。原厂的 `rk3588s.dtsi` 里有 `reboot loader` 进下载模式的 reboot-mode 节点，主线 `rk3588-base.dtsi` 里压根没有，得自己补（补丁 0035，跟上一章点亮的 rockusb 是一个功能的两半）。
- **显示路由**。原厂用私有属性 `&route_dsi0` 描述显示通路，主线走 OF-graph，语义等价但写法完全不同。这块留给 LCD 章细说，这里只点一句：原厂私有绑定的东西，翻译的目标永远是“主线等价物”，不是“主线兼容的原厂写法”。

### 同一份 DTB 的第二条验证线

咱们翻译出来的 `rk3588-topeet` 设备树后来还多了一条验证线：仿真。仓库里的 rk3588-lite 仿真目标把真板 DTB（不是为仿真另写一份）完整跑到了 shell，三断言咱们跑出了 PASS，还外加了一套 SOAK 存活浸泡机制，咱们去掉自动关机，让 shell 每 5 秒给咱们回一拍心跳，跑满了才算数（[notes/68](../../notes/68-2026-08-26-rk3588-real-dtb-full-port.md) 咱们记了）：真板 DTS、8 核异构，MTTCG 多线程下 120 秒 24/24 拍全到了。这场浸泡里还出过一次值得记的误诊：真板和 rk3588-lite 仿真板同在约 45 秒掉拍，咱们一度归罪 MTTCG 异构竞态，复查了才发现，真凶其实是喂拍代码自己把节奏越拉越稀，所以两板同位置掉拍就是测试代码的指纹，咱们给基础设施下判断之前要排除测试自身的 bug。断言绿和系统稳咱们得分成两回事看，这个教训后来直接影响了板侧的取证设计（本章末节）。

## 关键节点怎么落：PMIC、调压器、eMMC、串口

咱们把分拣方法论落到具体节点上，挑四个最有代表性的过一遍。下面的内容都以 0002 补丁正文为准。

咱们从电压树的根看起：整棵树从 `vcc12v_dcin` 出发，是 12V 直流输入的 fixed regulator（固定电压电源的设备树节点），而且一直常开，所以板上的大件都从这两级取电。然后第一级咱们降到 `vcc5v0_sys`，拿它供全板的 5V 系统电，也同样是常开的。板级 dts 的惯例是把根和各级都建成 fixed regulator 节点，咱们把 `always-on`/`boot-on` 标清楚，然后下面的 PMIC 和外置调压器再一层层挂 `vin-supply` 引用上去。

**rk806 PMIC（spi2）咱们从这颗说起**。单颗 rk806 咱们做成 `pmic@0` 挂在 spi2 下，spi 时钟咱们看就是 1MHz，pinctrl 咱们走 `spi2m2` 组。咱们再看它的供电输入，vcc1 到 vcca 十四路里大多数咱们挂到 `vcc5v0_sys`，不过的话 vcc13/vcc14 挂的是 `vcc_1v1_nldo_s3`，那个 1.1V 是板载 LDO 供给的、PMIC 自己并不出这一路。原因注释里写明了：单 rk806 的板子没有 PMIC 片上的 1.1V NLDO 输出，所以得板子自己补。咱们查到原厂板缺一路片上 LDO，就把这个硬件事实换成了主线语法的 fixed regulator 节点，处理思路倒是第二堆的标准做法。

**CPU/NPU 外置调压器（i2c0/i2c1）咱们照原厂收**。这三颗其实都是 Rockchip 自家的 buck（降压变换器），咱们挨个看：i2c0 上 `0x42` 是 RK8602，供的是 CPU big0 簇，`0x43` 咱们放的是 RK8603，供的是 big1 簇，i2c1 上 `0x42` 咱们又放了一颗 RK8602，供的是 NPU。节点咱们摘录如下（0002 正文、big0 那颗）：

```dts
&i2c0 {
	status = "okay";
	pinctrl-0 = <&i2c0m2_xfer>;
	resets = <&cru SRST_I2C0>, <&cru SRST_P_I2C0>;
	reset-names = "i2c", "apb";

	vdd_cpu_big0_s0: vdd_cpu_big0_mem_s0: regulator@42 {
		compatible = "rockchip,rk8602";
		reg = <0x42>;
		regulator-compatible = "rk860x-reg";
		regulator-name = "vdd_cpu_big0_s0";
		regulator-min-microvolt = <550000>;
		regulator-max-microvolt = <1050000>;
		regulator-ramp-delay = <2300>;
		rockchip,suspend-voltage-selector = <1>;
		vin-supply = <&vcc5v0_sys>;
		...
	};
};
```

要注意 compatible 咱们只写精确的 `rockchip,rk8602`，fallback（给驱动兜底认领的第二串兼容名）咱们不写，为什么写不得，下一节咱们用一场病来讲。`resets` 那两行把 I²C 控制器的 functional 和 APB 两个 reset domain 交给了内核，其实就是后来那场病的药引子，下一节咱们也会回到它。CPU 八个核的 `cpu-supply`/`mem-supply` 引用按 big0/big1/little 三簇分别接好，big 簇的 cpu 电和 mem 电由同一颗 RK8602 的双标签提供，一颗芯片咱们挂两个名，cpu-supply 和 mem-supply 咱们各引一个。

**eMMC（sdhci）咱们原样搬进主线**。这个节点咱们跑的是八位总线，HS400 增强选通咱们开了，而且不可拔。`aliases` 里咱们写 `mmc0 = &sdhci`，就是为后面 root 设备号的确定性服务。

**串口（uart2）咱们单独说**。这是全板最特殊的一个节点：`&uart2 { status = "disabled"; }`。咱们并不是不用串口，其实恰恰相反，它就是全板在用的 console。disabled 是咱们对 DesignWare 8250 驱动说的话：fiq-debugger 要独占这个 UART，所以 8250 驱动绝不能碰它，内核里也就永远不会出现 ttyS2 了。console 的本体是顶层那个 `fiq_debugger: fiq-debugger` 节点，咱们配 `rockchip,serial-id = <2>` 和 `rockchip,irq-mode-enable = <1>`，也就是原厂板跑的 IRQ 模式，波特率咱们定 115200。

dts 里还住着几位别的房客，咱们本章不展开只报名字：i2c2 上的 GT911 触摸（LCD 章的另一半戏），显示管线的 dsi0/面板/背光电源轨（LCD 章），GMAC0 的 RTL8211F PHY（网络章）。板级 DT 是全卷的地图，每一章咱们回来翻它都有新的房间。

## 内核配置：base defconfig + fragment

咱们的内核配置走“主线 base + 板级增量”两层：base 咱们直接用 `arch/arm64/configs/defconfig`，它已经帮咱们拉起了 ARCH_ROCKCHIP、pinctrl/clk 这一片基础，SERIAL_8250、MMC_SDHCI、EXT4 这些也都在了。板级差异咱们全部写进 [kernel.config](../../../boards/rk3588-topeet/kernel.config) 这个 fragment，构建时咱们把两份合并。这样 base 升级时 fragment 的每一行咱们都还留着“为什么开”的注释，就不会烂在一个巨大的自定义 defconfig 里。咱们挑本章相关的几组说：

**FIQ debugger 全家桶咱们头一组说**。`CONFIG_FIQ_DEBUGGER*` 咱们一连开了五个，外加了一发 `CONFIG_ROCKCHIP_FIQ_DEBUGGER`。配套纪律写在注释里：8250 驱动咱们保留着（别的 UART 还要用），但 uart2 在板级 DT 里咱们写成了 disabled，咱们永远不许它绑成 ttyS2。fragment 的原文长这样：

```
CONFIG_SERIAL_8250=y
CONFIG_SERIAL_8250_CONSOLE=y
CONFIG_SERIAL_8250_DW=y
CONFIG_FIQ_DEBUGGER=y
CONFIG_FIQ_DEBUGGER_NO_SLEEP=y
CONFIG_FIQ_DEBUGGER_CONSOLE=y
CONFIG_FIQ_DEBUGGER_CONSOLE_DEFAULT_ENABLE=y
CONFIG_FIQ_DEBUGGER_TRUST_ZONE=y
CONFIG_RK_CONSOLE_THREAD=y
CONFIG_ROCKCHIP_FIQ_DEBUGGER=y
```

**RK860X 与 FAN53555 咱们一开一关**。`CONFIG_REGULATOR_RK860X=y`，同时咱们显式写上 `# CONFIG_REGULATOR_FAN53555 is not set`。为什么要关掉一个主线驱动，这是下一节那场病的主角，配置立场咱们搁在这儿。

**取证栈咱们全开在 fragment 里**。`CONFIG_PSTORE/PSTORE_CONSOLE/PSTORE_RAM` 帮咱们把 panic 记录和滚动 console 留在保留内存里，soft/hard lockup 检测器、hung-task、workqueue watchdog 咱们全开且触发即 panic，`CONFIG_PANIC_TIMEOUT=10` 咱们让它 panic 后 10 秒自动重启，`CONFIG_DW_WATCHDOG` 咱们给 systemd 喂硬件看门狗。这套装备怎么用，咱们在本章末节见。

**reboot-mode 咱们只配一行**。`CONFIG_SYSCON_REBOOT_MODE=y`，配的是 0035 的 reboot-mode 节点。上一章讲过这个功能的两半：U-Boot 侧 0004/0006 读 `0xfd588080` 分流，内核侧就是这组配置加 0035 的 DT 节点，咱们敲一句 `reboot loader`，板子就重启进 rockusb 了。

咱们还有一条贯穿全部的纪律：fragment 里全 `=y`、零模块。这是 busybox 没有 modprobe 逼出来的（`CONFIG_RTW88` 的注释里记着菜单开关的教训），咱们后来在 v7.3.1 rebase 时还白赚了一笔红利，下下节咱们细讲。

至于 `CONFIG_DRM_PANTHOR`（GPU 固件内嵌的两行配置咱们也留在 fragment 里）、GMAC 强制 `=y`、rtw88 无线、DVFS 调频，分别归 GPU、网络、外设三章的戏份，咱们把配置留在 fragment 里不挪窝，本章咱们不展开。

## 首次启动：波特率、root 设备号、dtb 三件事

U-Boot 把 kernel FIT 交给内核之前的链路，上一章咱们都铺好了（boot.scr、`mmc read 0x08000000 0x6000 0x20000`、bootm）。咱们要让内核真跑到 systemd 还有三个板级细节要敲定，否则咱们会分别卡在波特率乱码、等根设备、DT 不匹配上，全过程咱们记在 [notes/50](../../notes/50-2026-07-27-rk3588-first-boot-baud-root-dt.md) 里：

1. **串口波特率全链 115200**。原厂默认 1500000，topeet 这块板全链 115200：DDR blob 侧用 rkbin 的 `ddrbin_tool` 改参数，U-Boot 侧 `CONFIG_BAUDRATE=115200`（上一章的 0002），内核侧 console 参数带 `115200`。三方任何一方不对齐，串口看到的都是乱码，而且乱码长得跟"板子挂了"一模一样。
2. **root=/dev/mmcblk0p3**。topeet 的 eMMC 在内核里枚举成 mmcblk0，而咱们上一块 RK3568-atk 是 mmcblk1。照旧经验写 `mmcblk1p3`，内核永远停在 `Waiting for root device`。U-Boot 里 eMMC 恒为 `mmc 0`，两边说的同一块存储，编号体系不一样而已。DT 里 `aliases` 的 `mmc0 = &sdhci` 就是给这个枚举兜底。
3. **dtb 换成 rk3588-topeet**。MVP 阶段的 evb1-v10 DT 到此退休。

咱们把这些细节对齐是在 2026 年 7 月 27 日，当轮 update.img 的 MD5 咱们记的是 `1d972c21`，板子随即第一次 boot 到了 Ubuntu systemd：hostname 是 `rk3588-topeet`，默认目标咱们看到 graphical.target，串口 115200 全程都是可读的。驱动 probe 的全清单咱们抄在这里：

- 8 个 CPU（A55×4 + A76×4）、16GB 内存
- eMMC HS400、PMIC rk806
- 调压器 fan53555（当时误领 RK860X）
- GMAC0 RGMII、GPU Panthor Mali-G610、USB host

不过咱们要注意，“误领 RK860X”是事后回看才敢下的判语，notes/50 里咱们的原话记作 “rk8602(fan53555)”，隐患那时其实就已经埋下、只是当时还没发作出来。

首次启动当天的 log 咱们没有归档原件。归档里最早的全量启动 log 咱们翻到了，是咱们 8 月 1 日早晨这轮的 [202608011826.txt](../../logs/rk3588/202608011826.txt)，咱们那时还在 #13 号内核、ttyS2 console 时期：

```
[    0.000000] Linux version 7.1.0-00002-g6c8532e28925-dirty ... #13 SMP PREEMPT Sat Aug  1 12:10:59 CST 2026
[    0.000000] Machine model: Topeet RK3588 Board (iTOP-RK3588)
[    0.000000] Kernel command line: console=ttyS2,115200 root=/dev/mmcblk0p3 rw rootwait drm_kms_helper.fbdev_emulation=0
...
[    3.188466] VFS: Mounted root (ext4 filesystem) on device 179:3.
...
Welcome to Ubuntu 26.04 LTS!
[    4.048553] systemd[1]: Queued start job for default target graphical.target.
```

咱们逐行核对：`Machine model: Topeet RK3588 Board (iTOP-RK3588)` 说明咱们亲手翻译的设备树被内核认了，`Mounted root ... on device 179:3` 里 179 是 mmcblk 的主设备号、3 就是 mmcblk0p3，然后 Ubuntu 26.04 的 systemd 顶着 graphical.target 起来了。earlycon 参数咱们配的是 `earlycon=uart8250,mmio32,0xfeb50000`，这是后来 console 切到 ttyFIQ0 时才进 bootargs 的（上面这段首启 cmdline 里还没有它），交接给真正的 console 之前它保证最早期的打印不丢。

## 一场误诊带出一场真病：ttyFIQ 与 rk860x 的 I²C 卡死

首次启动跑通、GNOME 桌面也点亮（notes/48 咱们记了、GPU 章细讲）之后，console 从 ttyS2 切到原厂式的 ttyFIQ0，病就来了。咱们在 notes/51 里记了一段难得的完整病历，其中就包括一次被纠正的误诊。

### 症状：console 换成 ttyFIQ0 之后，板子"挂死"

原厂的调试口是 ttyFIQ0，是 FIQ debugger 暴露出来的。咱们照原厂架构把整套东西移植过来（补丁 [0003](../../../boards/rk3588-topeet/patches/linux/0003-soc-rockchip-port-vendor-FIQ-debugger-to-Linux-7.1.patch)），移植量咱们数过是 `drivers/soc/rockchip/fiq_debugger/` 整目录 16 个文件、3990 行、含 RK UART 后端和 TrustZone SiP ABI 适配层，原厂 5.10 用到的已删除上游 API 咱们全部换成了 7.1 的等价物，像栈回溯、kmsg 迭代、IRQ 统计、TTY 签名这些咱们都换了。换上之后症状就来了：系统咱们进得去，但咱们在 ttyFIQ0 上无法输入，过一会儿咱们就看到乱码，整块板子在咱们眼里就像挂死。启动末尾同时冒出了 CPU4/CPU6 调压失败的报错。

### 误诊与纠正

咱们第一反应，容易把矛头指向刚换的 console：ttyFIQ0 是不是没注册成功？log 咱们一查，注册路径其实全通了（咱们翻的是 [202608012117.txt](../../logs/rk3588/202608012117.txt)）：

```
[    0.553407] Registered FIQ tty driver
[    0.788953] fiq_debugger_probe: could not install nmi irq handler
[    0.795679] printk: legacy console [ttyFIQ0] enabled
```

中间那行 `could not install nmi irq handler` 咱们一开始看着也吓人，其实是正常路径：原厂板级配置 `rockchip,irq-mode-enable = <1>` 本来就跑 IRQ 模式（cmdline 里 `irqchip.gicv3_pseudo_nmi=0`），FIQ debugger 咱们看到在 NMI 不可用时退回了 IRQ handler，这是原厂的既定行为。console 注册了、使能了，咱们确认病不在它身上。

真凶咱们是在 log 末尾找到的，咱们接着往下看：

```
[   11.095227] cpu cpu6: _set_opp_voltage: failed to set voltage (925000 925000 1000000 mV): -110
[   11.095235] cpu cpu6: Failed to set regulator voltages: -110
[   11.095238] cpufreq: __target_index: Failed to change cpu frequency: -110
[   14.171224] cpu cpu4: _set_opp_voltage: failed to set voltage (987500 987500 1000000 mV): -110
```

还有更早的三行 log，咱们当时没把它们当回事：

```
[    1.178913] fan53555-regulator 1-0042: FAN53555 Option[10] Rev[1] Detected!
[    1.179404] fan53555-regulator 0-0042: FAN53555 Option[10] Rev[1] Detected!
[    1.180107] fan53555-regulator 0-0043: FAN53555 Option[10] Rev[1] Detected!
```

### 根因链：错误驱动 probe 成功，比 probe 失败更危险

咱们把三行 `FAN53555 Detected` 和 DT 对上，事情就清楚了。板上那三颗 RK8602/RK8603（i2c0 的 0x42/0x43、i2c1 的 0x42）本该由原厂的独立驱动 `rk860x-regulator` 管，主线 v7.1 里咱们找不到它，通用的 fan53555 驱动却认领了 RK8602。更糟的是旧版板级 DTS 学原厂把 RK8603 写成 `"rockchip,rk8603", "rockchip,rk8602"` 的 fallback compatible，于是连 RK8603 也被 fan53555 当 RK8602 认走了。CPU 调频咱们知道要改电压，fan53555 就用它自己的语义去敲 RK860X 的 I²C 寄存器，这笔传输（transaction）却超时了，咱们拿到的返回值是 `-ETIMEDOUT`（-110）。

结果还有第二层。咱们查到主线 RK3x I²C 驱动超时后不做原厂那套恢复，从设备拉死 SCL 的状态位检测（`REG_INT_SLV_HDSCL`）咱们在主线里找不到，functional 和 APB 的复位咱们也等不到。咱们要是碰上从设备拉住 SCL，控制器就可能持续僵死（wedged）到咱们毫无办法。而挂在这颗僵死的 I²C 控制器上的，偏偏是 CPU 大核调压器、调频改压全走它。于是五花八门的外在表现就都出现了，调频失败、console 输入失去响应、系统整个停住全都到齐了。console 咱们核对下来只是受害者，凶手倒是另有其人。

### 修复：一次合并，一个候选

修复咱们全部落进补丁 [0004](../../../boards/rk3588-topeet/patches/linux/0004-regulator-rk860x-and-i2c-timeout-recovery.patch)，五件事咱们一次做完：

1. 原厂的 `rk860x-regulator.c` 移植到主线 7.1（只改 I²C probe API 和已删除头文件的适配）。
2. kernel.config 关 FAN53555、开 RK860X，杜绝双驱动竞争。
3. DTS 用精确 compatible，不再写 fallback。
4. i2c0/i2c1 节点补 `i2c`/`apb` 两组 reset（就是上一节 DT 里那两行的来历）。
5. RK3x I²C 超时路径移植原厂的 IPD/state 日志、SLV_HDSCL 检测、双 reset domain 复位和 bus timing 重算。

咱们在 2026 年 8 月 1 日烧板验证（候选镜像 SHA-256 咱们记作 `134228df...`）：系统正常进入了，ttyFIQ0 持续输入咱们再没碰上挂死，板验后 `dmesg` 里 RK860X/cpufreq 的 `-110` 咱们看着全部消失。烧板前咱们过了四道静态闸门，notes/51 里有记录：一是咱们从 upstream v7.1 的干净树顺序 `git am` 0001–0004，无冲突、全量编译通过了。二是咱们核对 `.config`：RK860X=y、FAN53555 未设置，都对上了。三是咱们查 `vmlinux`：含 `rk860x_regulator_probe`、`rk3x_i2c_xfer_common` 等新符号，fan53555 的符号咱们没在里面找到。四是 `rk3588-topeet.dtb` 的 SHA-256 咱们在工作树和干净回放树上比对完全相同，FIT 咱们封入当轮产物，update.img 的打包回读自检（round-trip）咱们也跑通了。一轮咱们只保留一个有证据的候选，这套闸门咱们跑下来就把“烧一次就过”从运气变成了纪律。

板验后 `dmesg` 残留的三条报错，咱们核对过都不在本故障域：FIQ debugger 探测互斥的备用 IRQ 打过两次 `-ENXIO`（uart_irq console 实际已注册，咱们保持原厂的 IRQ 模式，不为清日志伪造不存在的 IRQ），外加一条 cfg80211 早期加载 regulatory.db 的 `-2`（咱们留给无线章节）。

这里咱们还有个后续要讲解明白。0007（[0007](../../../boards/rk3588-topeet/patches/linux/0007-i2c-rk3x-port-RK3588-vendor-v5-auto-stop-state-machi.patch)）把原厂 I²C v5 的 auto-stop 状态机也移植了过来，瞄准的是 DVFS 调压传输（transaction）里 START-wait 状态的卡死，`IPD 0x10` 卡住不放咱们见过。不过的话，它和 0008（GT911 轮询）咱们做成了一对耦合实验，候选镜像咱们没能可靠跑到 login，所以咱们有意把两个补丁从 series 里摘掉了，文件咱们只作失败证据留档（series 文件的注释原话）。活下来的超时恢复是 0004 里那套聚焦的版本。另外 notes/51 末尾的诚实纠偏咱们也要照录：8 月 1 日的板验只证明当轮启动和输入恢复正常，“RK860X 移植消除了所有随机挂死”这个更强的命题咱们证明不了，因为后续咱们仍遇到过间歇性挂死，咱们不能把不同故障合并成一个“已解决”。同期的触摸也还在闹别扭：Goodix probe 复位后 I²C 读超时 -110，但用户态 `i2ctransfer` 咱们能读到 `911`，重点在 INT/RST GPIO 时序而不是全局 I²C，触摸的后续调查咱们交给 LCD 章接手。这两桩没结的案子，本章末节咱们搭起 ramoops、lockup 检测器和硬件看门狗来接。

notes/51 里留下的教训，咱们原样抄给读者：

- console 最后一条日志附近出现挂死，不等于 console 驱动是根因。咱们要验证注册路径，再去其他 subsystem 找确定错误。
- compatible fallback 不是无害兼容。RK8603 fallback 到 RK8602 让错误驱动成功 probe，比 probe 失败更危险。
- 原厂同板 SDK 的价值不只在 DTS，还有 timeout/recovery 这类低概率硬件状态机处理。主线 API 可以适配，语义不能删。
- 反复烧板前必须做干净的补丁重放（patch replay）、全量链接、FIT 哈希、update.img round-trip，自始至终只保留一个有证据的候选。

## 追 stable：v7.1 → v7.3.1 rebase

咱们把时间线快进到 11 月。v7.1 线在 commit `ga7dad280` 收官（板验咱们验过），当天咱们拍板跟上最新 stable：v7.3.1（ls-remote 咱们核实过没有 7.3.2/7.4）。全记录咱们放在 [notes/122](../../notes/122-2026-11-01-rk3588-kernel-v7.3.1-rebase.md) 里，本章后半场的主戏咱们就在这里开演。

### 预审：changelog 全扫

rebase 之前咱们把 7.2、7.3 两个大版本的 changelog 完整扫了一遍，逐条对照咱们 24 发补丁触达的子系统，预审的判断是“重头补丁零重写、最多动几个 hunk”。hunk 就是 diff 里的一段改动块。事后兑现得出奇地准：20 发重放下来，实际只动了两处。

### 补丁序列：24 → 20

咱们收缩的过程是这样的：咱们删掉的是 0013 到 0017 这 5 发，它们本来就是 v7.2 内容的 backport（把新版修复搬回旧版内核的补丁，schedutil 的 sg_cpu 发布 `f0a3f042293a`、OPP 的 add/lookup 竞争 `f5e1cc9a284b`、rtw88 三连），内核一升级它们就被上游吃掉了，咱们自己再背着就是重复。咱们加的是 0035 reboot-mode 这 1 发，就是为了配合上一章刚点亮的 rockusb。咱们算下来 24 − 5 + 1 = 20。series 文件里那五行注释掉的名字和 upstream commit 号咱们都留着，作为 v7.1 时代 backport 的存档证据。

### 真正动了的两处

**0001（面板驱动）：咱们遇到的是 API 改名**。v7.2 起 `of_drm_get_panel_orientation()` 改名为 `drm_of_get_panel_orientation()`（签名同形、只是搬到了 drm_of.h），咱们改了调用点、补了 include，结果就是纯改名、无语义差。面板驱动本身是 LCD 章的内容，这里咱们只记 rebase 的改动。

**0002（板级 DT）：咱们重织了 Makefile hunk**。dts Makefile 是字母序的单行列表，咱们的行插在 tiger-haikou 与 toybrick 之间。v7.3 咱们看到在 turing 与 rk3588s-coolpi 之间塞进了几块新板：vicharak-axon、vaaman2、youyeetoo-yy3588，补丁尾部的上下文于是失效了。咱们重织后 topeet 的插入位没变，前后邻居咱们没换、还是 tiger-haikou 与 toybrick。

其余的补丁（FIQ、RK860X、GT911、VOP2 dclk、DVFS、DSU、AFBC、virtio、PD_GMAC、GMAC 等）咱们零改动，直接落到了 v7.3.1。这印证了咱们的预审：7.2/7.3 没动咱们的重头区域。kernel.config 侧的增量只有一行 `+CONFIG_SYSCON_REBOOT_MODE=y`（配 0035），合并后咱们把 PSEUDO_NMI、ROOT_NFS、DWMAC_ROCKCHIP、DRM_PANEL_TOPEET_DSI、ARM_ROCKCHIP_CPUFREQ、RTW88_8723DU 等关键符号逐个对着 `.config` 审过，咱们看着全部是 =y。

### 白捡与两颗雷

升级里白赚的咱们列一下（零动作）：

- panthor 的 GEM shrinking 加了一波修复
- RK3568 SGMII BMCR 修复、RKVDEC m2m 安全修复
- HCLK_VO1 显式使能、一批新 rk3588 板 DTS

头两处（panthor 与 SGMII）分别给 GPU 章和网络章直接发了红利，咱们白捡。

过程中咱们踩到两颗雷，都值得咱们记下来：

**dtc 不吃 DTS cell 里的算术表达式**。0035 里的 `mode-ums = <REBOOT_FLAG + 12>;` 咱们一写就语法错，dt-binding 头文件咱们又找不到现成宏，最后咱们用字面量 `<0x5242C30C>` 加注释交代来历。同一场里咱们还学到：往 dts 追加 SoC 级节点必须包进 `/ { }`，顶层裸写 `syscon@…` 咱们也写出了语法错，咱们的第一版就死在这。

**咱们碰上的 kernel.org 直连 0 字节挂死**。depth-1 的浅克隆咱们碰到的是服务端 pack 生成阶段一个字节都不给、无超时无报错，而 forge 的重试咱们查过只在进程失败时触发，挂死就会永远等下去了。咱们的解法是 WSL mirrored 模式下走 Windows 侧代理（`https_proxy=http://127.0.0.1:7897 git clone ...`），5 分钟咱们就收工了。forge 的进程环境白名单故意不含 https_proxy（防渗漏），所以咱们的姿势是裸 git 拉完、forge 认树即跳过。

### 零模块纪律的红利与板验

咱们前面说的“fragment 全 =y、零模块”在这里兑现了：rootfs 树内没有 `/lib/modules` 依赖，TFTP 拉什么内核咱们就跑什么内核，NFS rootfs 咱们也不需要任何同步动作。v7.3.1 的构建咱们验过（`Linux version 7.3.1-00020-g8a8c79486a31`、Image 51MB），20/20 重放咱们核对过，forge apply 原子链无回滚（`79a90760` 对应 v7.3.1、`8a8c7948` 是重放后的树），关键符号审计咱们 15/15 全部通过，板侧验证咱们走 TFTP+NFS 免烧录，引擎细节是网络章的正题、这里咱们只当验证手段用。U-Boot 串口咱们打断 autoboot 后：

```
setenv ipaddr 192.168.50.99
setenv serverip 192.168.50.5
tftp ${scriptaddr} boot-tftp.scr
source ${scriptaddr}
```

2026 年 11 月 1 日深夜咱们的板验通过，一轮过（用户确认了）。验收线按 notes/122 的记录：串口出现 `Linux version 7.3.1-00020-g8a8c79486a31`，`VFS: Mounted root (nfs filesystem)`，进 shell 后 `uname -r` 咱们对上了，显示管线回归咱们也验过（LCD 亮 GNOME），咱们敲 `reboot loader`，板子进了 rockusb。

这轮验证用的货架是 `out/rk3588-topeet/tftpboot/`：Image、rk3588-topeet.dtb、boot-tftp.scr 三件套（旧的 boot.img 和原厂 SDK 时代的产物咱们留档在同目录）。scr 的内容就是上面那套引导逻辑的固化：bootargs 在 `console=ttyFIQ0 root=/dev/nfs nfsroot=.../out/rk3588-topeet/rootfs,vers=3,tcp` 之外，咱们还加了静态 ip 七段，然后咱们依次 `tftpboot ${kernel_addr_r} Image`、`tftpboot ${fdt_addr_r} rk3588-topeet.dtb`，最后咱们 `booti` 引导。源文件咱们放在 [boot-tftp.cmd](../../../boards/rk3588-topeet/fit/boot-tftp.cmd)，改动后咱们用 `mkimage -A arm64 -O linux -T script -C none -d` 重新生成 scr。eMMC 侧的 boot.img 咱们也已用 fit 重包为 v7.3.1，下次烧录自然就带上了。咱们还遗留一条诚实记录，0023（virtio 的 sim 侧适配）咱们在 7.3.1 上未验、那是仿真线的资产，下次 sim 跑时咱们再核。

## 内核侧补丁总表

本章出场的和没出场但住同一目录的补丁，咱们按 series 顺序把归属说清楚（[series 文件](../../../boards/rk3588-topeet/patches/linux/series)里每发都有决策注释）：

| 补丁 | 动什么 | 归属 |
|---|---|---|
| [0001](../../../boards/rk3588-topeet/patches/linux/0001-drm-panel-topeet-dsi-driver.patch) 面板驱动 | OOT DRM panel 驱动，回放原厂初始化字节序列 | LCD 章 |
| [0002](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch) 板级 DT | rk3588-topeet.dts 全量（本章主角）+ Makefile 接线 | 本章 |
| [0003](../../../boards/rk3588-topeet/patches/linux/0003-soc-rockchip-port-vendor-FIQ-debugger-to-Linux-7.1.patch) FIQ debugger | 原厂调试口全套移植，ttyFIQ0 拥有 UART2 | 本章 |
| [0004](../../../boards/rk3588-topeet/patches/linux/0004-regulator-rk860x-and-i2c-timeout-recovery.patch) rk860x + I²C 恢复 | RK8602/RK8603 调压 + RK3x 超时恢复 | 本章 |
| 0005/0006/0008/0010 GT911 | 触摸 probe 时序与轴映射（0008 已随耦合实验退役） | LCD 章 |
| [0007](../../../boards/rk3588-topeet/patches/linux/0007-i2c-rk3x-port-RK3588-vendor-v5-auto-stop-state-machi.patch) I²C v5 状态机 | 耦合实验失败证据，不在 series 里 | 本章（教训） |
| 0009/0020/0021 VOP2 | dclk 交接、AFBC modifier、10bpc 格式 | LCD 章 |
| 0011/0012/0018/0019 DVFS | 原厂调频事务移植、probe 修复、DSU/L3 耦合 | 外设章 |
| 0013–0017（已删） | v7.2 backport，升级被上游吃掉 | 存档 |
| 0024–0028 GMAC | PD_GMAC 常开、PHY reset、时钟、delay line | 网络章 |
| 0035 reboot-mode | pmu0_grf 的 syscon-reboot-mode 节点，上一章 rockusb 的内核半边 | 本章 |

另有一批 TEMP 前缀的诊断补丁（0022、0026、0029–0032）在各次结案后退役，0033/0034 的内容已分别折叠进 0009 和 0001，文件咱们都留了档。series 里被注释掉的名字和理由，就是咱们补丁序列的决策史。

## 无声硬锁：为看不见的死准备取证

本章的方法论咱们压轴来讲。notes/51 末尾留了个咱们没关死的门：随机挂死没有被彻底归因。而 RK3588 上的随机挂死咱们领教过，狠就狠在咱们一个报错都收不到、直接无声死掉。ttyFIQ0 跑的是 IRQ 模式（原厂行为、`irqchip.gicv3_pseudo_nmi=0`），挂死发生时连 debugger 的触发串咱们都收不到响应。咱们手里的证据说明故障至少深入到了三者之一：

- 某 CPU 长时间关本地中断
- GIC/UART 中断不再投递
- 全局互锁或 SoC 级硬锁

不过的话，这三者咱们手里的证据区分不了，但足以帮咱们排除“系统还能调度、只是终端卡住”的温和解释。

既然死前一个字咱们都打不出来，那咱们就让板子自己把遗书写在掉电不丢的地方。装备咱们分三层搭，[notes/53](../../notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md) 里咱们有记录，配置咱们全放在 kernel.config 的 Persistent lockup diagnostics 段：

**咱们装备的第一层是 ramoops/pstore**，它是内核把崩溃日志存进一块预留内存的机制。咱们在保留内存里开一块 ramoops 窗口，咱们用 `CONFIG_PSTORE_RAM` 把 panic 记录和滚动 console 存进去，这块内存咱们让它跨 watchdog 暖重启保留，断电咱们的记录就没了。窗口位置有个主线特有的教训咱们吃过：咱们最初照原厂用 `0x110000` 低地址窗口，但主线的 TPL/ddrbin 启动链在内核挂 pstore 之前就把那片内存清了，于是咱们把窗口搬到 `0x10000000`。板级 DT 里咱们定型成这样（0002 正文）：

```dts
reserved-memory {
	ramoops: ramoops@10000000 {
		compatible = "ramoops";
		reg = <0x0 0x10000000 0x0 0x000e0000>;
		record-size = <0x00020000>;
		console-size = <0x00080000>;
	};
};
```

record-size 咱们给每条 panic 记录 128KiB，console-size 咱们给滚动 console 留 512KiB。启动 log 里咱们能看到内核认领它：

```
[    0.000000] OF: reserved mem: 0x0000000010000000..0x00000000100dffff (896 KiB) map non-reusable ramoops@10000000
```

**咱们的第二层是不依赖 pseudo-NMI 的检测器**。soft lockup 加中断风暴检测、buddy hardlockup 检测器（咱们让一颗 CPU 由仍在运行的伙伴 CPU 代查）、60 秒 hung-task、workqueue watchdog，咱们让它们全部触发即 panic，再配 `PANIC_TIMEOUT=10` 咱们让它到点自动重启。buddy 检测器咱们选来做保底，咱们是有实测依据的：kernel.config 里 2026-08-16 那段注释记录了 perf-NMI 作为唯一检测器时，一次 280 秒压力下的 wedge 咱们没拿到 hardlockup 报告（最后是 RCU stall 抓到的），而 PMU PPI 的 NMI 声称咱们在板上验证不了，于是咱们把 `HARDLOCKUP_DETECTOR_PREFER_BUDDY` 回补为底线。顺带一个配置陷阱咱们记着：`CONFIG_ARM64_PSEUDO_NMI=y` 单开不够，这个运行时开关咱们查过默认是关的，内核命令行咱们得显式带 `irqchip.gicv3_pseudo_nmi=1`（8 月中旬的调试轮 log 里咱们能看到它）。机制边界咱们要照实讲：如果所有 CPU、GIC 或整颗 SoC 同时停摆，任何软件检测器都没有执行的机会，“没有 detector 报告”咱们也就不能读成“没有挂死”。

**咱们的第三层是硬件看门狗兜底**。Ubuntu rootfs 里咱们固化 `RuntimeWatchdogSec=30s`，systemd 帮咱们持续喂的，是 RK3588 `feaf0000` 的 DesignWare watchdog。全局停摆时约 30 秒后咱们能等到暖重启，重启后咱们要做的第一件事就是读 pstore：

```sh
find /sys/fs/pstore /var/lib/systemd/pstore -maxdepth 2 -type f -print 2>/dev/null
for f in /sys/fs/pstore/* /var/lib/systemd/pstore/*; do
	[ -f "$f" ] && { echo "===== $f ====="; cat "$f"; }
done
journalctl -b -1 -k --no-pager | tail -n 300
```

取证的姿势也有讲究（notes/53 的原话值得咱们原样转述给读者）：挂死发生时咱们不要急着断电，咱们等上 30 到 45 秒再判断它是否自动暖重启。45 秒后咱们要是看到板子仍不重启，说明硬件看门狗在那个冻结状态下也没能帮咱们把系统复位，这时咱们改按 reset 做暖复位再读 pstore，咱们不要急着拔电，因为 pstore 咱们知道只在暖重启后幸存。还有一个咱们觉得反直觉的解读规则：如果自动重启了、pstore 里却只有最后一段 printk 而没有栈，空手而归本身就成了咱们的证据，因为冻结覆盖了所有还能运行检测器的 CPU 和中断路径，咱们的故障域又收窄了一圈。

咱们这套装备在 8 月 16 日凌晨抓到过一次教科书级的现场，当时咱们跑的是 v7.1 #10 内核、DVFS 调试时期，log 咱们存在 [202608160026.txt](../../logs/rk3588/202608160026.txt) 里：

```
[    3.747873] rk3x-i2c fd880000.i2c: timeout, ipd: 0x1b, state: 2
[    4.771866] rk3x-i2c fd880000.i2c: timeout, ipd: 0x10, state: 1
[   16.247863] watchdog: CPU2: Watchdog detected hard LOCKUP on cpu 3
[   16.247877] Modules linked in:
[   16.247882] Sending NMI from CPU 2 to CPUs 3:
[   16.251863] watchdog: CPU4: Watchdog detected hard LOCKUP on cpu 5
[   16.251871] Kernel panic - not syncing: Hard LOCKUP
[   16.781616] CPU: 4 UID: 0 PID: 0 Comm: swapper/4 Not tainted 7.1.0-00016-gdd0dd76d38c3 #10 PREEMPT
[   16.790651] Hardware name: Topeet RK3588 Board (iTOP-RK3588) (DT)
...
[   16.882852]  cpuidle_enter_state+0x164/0x360 (P)
...
[   18.122181] cpu cpu0: cur_freq: 1608000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
[   18.129910] cpu cpu4: cur_freq: 2208000 Hz, volt_vdd: 987500 uV, volt_mem: 987500 uV
[   18.137638] cpu cpu6: cur_freq: 1800000 Hz, volt_vdd: 850000 uV, volt_mem: 850000 uV
[   18.147468] Rebooting in 10 seconds..
```

咱们读下来，遗书信息量很大：buddy 检测器（栈里的 `watchdog_buddy_check_hardlockup`）由 CPU2/CPU4 代查报出 CPU3/CPU5 硬锁，panic 栈里停摆的 CPU 停在 `cpuidle_enter_state`，末尾三行是 DVFS 补丁挂的 panic notifier 把三个簇最后的频率电压打了出来，咱们眼看它 10 秒后自动重启，ramoops 咱们留着重启后取证。咱们后来破 LCD 章那场 VOP2 硬锁，读到的现场就是这套组合留下来的 pstore。

## 成功长这样

v7.1 线收官那轮的 log 咱们存在 [finish/1.txt](../../logs/rk3588/finish/1.txt)（2026 年 11 月 1 日、commit `ga7dad280`、eMMC 根、ttyFIQ0 console）：

```
[    0.000000] Linux version 7.1.0-00024-ga7dad2806329 ... #60 SMP PREEMPT Sun Nov  1 21:22:37 CST 2026
[    0.000000] Machine model: Topeet RK3588 Board (iTOP-RK3588)
[    0.000000] Kernel command line: console=ttyFIQ0 root=/dev/mmcblk0p3 rw rootwait
...
[    0.056256] Registered FIQ tty driver
...
rk3588-topeet login: root
```

`console=ttyFIQ0` 说明 0003 的调试口栈和 0004 的调压器修复都在位（ttyFIQ0 能交互的前提是 I²C 不再卡死），咱们看到结尾停在 `rk3588-topeet login:`，`root` 是咱们敲进去的用户名，shell 是 log 收档之后才起来的。当晚咱们再进一步，v7.3.1 咱们经 TFTP+NFS 板验一轮过，咱们把内核线收官。

这一章到尾声了，板子咱们已经从 BootROM 带进了 Ubuntu 的 shell。但桌面还是黑着的，LCD 从 DSI 到 LVDS 的显示管线咱们留给 LCD 章了，TC358775 桥 IC、GT911 触摸也都留给 LCD 章了，要用本章取证装备破案的 VOP2 硬锁咱们同样留给 LCD 章，咱们 LCD 章见。
