# Linux 内核移植：把原厂 SDK 的设备树翻译成主线语法，一路追到 v7.3.1

> [上一章](01_uboot.md) 把主线 U-Boot 稳在了 `=>` 提示符，还顺手点亮了 rockusb Loader 模式，rockusb 是瑞芯微的 USB 下载模式。这一章咱们往底座上装的是主线 Linux。RK3588 在主线享受的是旗舰待遇，SoC 级的设备树、驱动一应俱全，所以咱们真正要干的只有一件事：把迅为原厂 SDK 5.10 里的板级 dts 翻译成主线语法，最后咱们尊重厂商，毕竟没啥太多的工作量，继续沿用了 `rk3588-topeet`的名字。接下来是两个活：一场看着像串口控制台挂了，咱们查下来真凶是 CPU 调压器，另一场是收官前的补丁重放（rebase，咱们把整套补丁重新落到新内核版本上）。这块板还有个狠脾气要跟咱们交代：有些 bug 咱们一个报错都收不到，直接就把板子无声卡死（hard-lock）了，所以本章末尾咱们会把抓无声卡死的取证装备搭起来，LCD 章那场 VOP2（RK3588 显示控制器）硬锁咱们就靠它破案。

版本口径咱们在这儿交代清楚。点亮初调（bringup）的里程碑，大多数是在 v7.1 上取得的，v7.3.1 是咱们最后的收官升级。本章咱们按时间线走，每一步咱们都注明当时的内核版本，v7.3.1 板验通过的部分咱们就按通过写。

## 起点：主线是旗舰待遇，缺的只是这块板的板级描述

主线 Linux 对 RK3588 的支持，是 Collabora（一家长期给 ARM 生态做主线移植的公司）的重点项目，板卡配置文件 board.yaml 的头注释就是这么定位的，注释原话咱们抄在这里：`mainline-first (Collabora flagship: Panthor G610, Hantro+rkvdec2, RGA, RKCIF/rkisp1, mainline NPU "Rocket")`，咱们翻过来讲就是：整个平台主打主线，视频编解码、图像加速、摄像头、GPU、NPU 这些大件的维护，主线都替咱们包了。SoC 级的 `rk3588.dtsi` 全套是主线树里自带的，时钟、引脚复用、存储控制器、千兆网卡、显示、GPU 这些驱动也全是主线的，社区板卡的板级 dts 主线同样收了一大把。唯独 topeet 这块板的板级描述，咱们在主线里还找不到。这块板的移植量，跟连 SoC 级描述都要自己补的板子比起来，咱们这个不是一个量级：底子对咱们全是现成的，咱们缺的只有板级这一层。

所以点亮初调的第一阶段咱们干脆不写设备树，直接拿主线的 `rk3588-evb1-v10.dtb`（Rockchip 官方参考板的设备树），把它当最小可用版本的设备树用。

> 这一招笔者贼喜欢用，当初入门的时候玩imx6ull，也是先拿一个看起来能用的设备树试试，哪个驱动挂了补哪个。咱们这里的思路没有差太多。

kernel.config 的头注释记录了这个阶段，

> `mainline rk3588-evb1-v10.dtb is the MVP DT`。

topeet 这块板本质是 EVB 的亲戚，串口、eMMC 这些大件的位置咱们比对过都相同，最小可用阶段对咱们够用。这是好事啊，起码我们不用做特别多的事情了，但问题就出在这里。

笔者厂商用的板子吧，内核5.10，兄弟们，现在是7.3.1了，0s猜出直接CV能不能用，那肯定是不能的。（所以提醒各位用AI玩的，麻烦prompt必须带一个：先审查一下API变更清单。。。你知道牢Agent一些贼喜欢蒙蒙干活然后被API变更直接踹死的）

## 方法论：原厂 dts 的三堆分拣

原厂 dts 咱们要搬进主线，但咱们不整块复制、也不逐行重写，所以分拣成三堆，每堆的处理办法写在下面。这套方法的原料就是咱们首次移植那轮的实际操作：翻译出来的设备树，咱们后来又在仿真线上（用 QEMU 虚拟板跑的验证线）完整跑通了一遍，还添了一条跨板教训：设备树里描述中断的写法，两代芯片的要求是不一样的，咱们在下面第二堆里细说。

**咱们第一堆的处理是原样保留。** 电压树这类纯硬件描述咱们查过，主线语法是一直没变的，原厂的写法咱们照单全收。rk806 电源管理芯片（PMIC）的完整调压器树，咱们就是从原厂配套文件 `rk3588-fet3588-c.dtsi`（飞凌 FET3588-C 核心板的设备树）原样复制过来的，因为咱们比对原厂的 `topeet-rk3588-linux.dts` 之后确认，topeet 的供电拓扑跟飞凌 OK3588-C 完全一致：单颗 rk806 挂 spi2，CPU 和 NPU 用的是外置调压器。主线里已经有人把这套拓扑写规范了，那咱们就直接用。eMMC 的总线宽度、HS400 增强选通（eMMC 的高速总线模式）这些属性，咱们也归在这一堆。

**咱们第二堆的处理是翻译。** 语义还在、写法变了的那些部分，咱们挑几条实打实的差异：

- **compatible 字符串**。原厂 SDK 里 topeet 的板级 compatible 是 `rockchip,rk3588-evb3-lp5-v10`，这是原厂 BSP（板级支持包）的概念，主线不认。咱们的做法是起干净的 `topeet` 名字，第二级照例挂 `rockchip,rk3588`。U-Boot 的 rockchip 面板链就是按 compatible 匹配板子的，咱们认领板子的凭据就是这第二级。
- **中断的写法**（设备树里一条中断占几个 32 位单元，术语叫 interrupt cell）。主线 RK3588 的中断控制器（GIC，把硬件中断分发给各 CPU 的部件）要求第四个单元写中断亲缘性。咱们设备树里 fiq-debugger 节点的中断写法是 `interrupts = <GIC_SPI 423 IRQ_TYPE_LEVEL_LOW 0>`，末尾那个 0 就是第四个单元。这条差异真咬过咱们一口：咱们往设备树动态嫁接节点时把中断写死成三个单元，同样的代码，在早前跑通的 RK3568 仿真板上全绿，搬到 RK3588 仿真板上，内核直接判畸形，报 `IRQ index 0 not found`。两块板同代码不同结果的时候，咱们就去数绑定文档要求的单元数。
- **原厂引用的 label 和 phandle**。原厂 dts 里引用的时钟、引脚配置标签，咱们都要在主线 dtsi 里重新对一遍名，因为两棵树的节点组织和命名不完全一样。

**咱们第三堆的处理是换主线等价物、或者干脆删。** 原厂私有绑定咱们不能带走，带走了也没人认。这块板上最大的三个是这些：

- **fiq-debugger**。原厂的调试口方案是私有的 `rockchip,fiq-debugger` 节点独占 UART2，主线没有对应的驱动。第三堆的常规处理是换，这项咱们的选择是整体搬：咱们把原厂这套 FIQ 调试器驱动整个移植进主线，后面细讲。FIQ 咱们知道是 ARM 的快速中断（Fast Interrupt），级别比普通中断还高一层，原厂拿它来做调试口。
- **reboot-mode**。原厂的 `rk3588s.dtsi` 里有 `reboot loader` 进下载模式的 reboot-mode 节点，主线 `rk3588-base.dtsi` 里压根没有，咱们得自己补，这个节点是后来 v7.3.1 重放那批才落地的。它跟上一章 U-Boot 里点亮的 rockusb（下载模式）是同一个功能的两半。
- **显示路由**。原厂用私有属性 `&route_dsi0` 描述显示通路，主线走的是 OF-graph（用端口和端点连成图来描述数据通路的写法），语义等价但写法完全不同。

### 同一份设备树的第二条验证线

咱们翻译出来的 `rk3588-topeet` 设备树后来还多了一条验证线：仿真。咱们在仓库里的 rk3588-lite 仿真目标（QEMU 里的一块虚拟板）上，把真板设备树原样跑到了 shell，咱们提前定好的开机断言全部通过。断言的覆盖面，在咱们这里只到进 shell 为止，所以咱们后来又补了一套长稳浸泡（SOAK）：去掉自动关机，让 shell 每 5 秒给咱们回一拍心跳，咱们跑满约定时长才算数。真板设备树、8 核异构、开 MTTCG（QEMU 用多线程并行模拟各颗 CPU）的条件下，120 秒的浸泡 24/24 拍全到了。

这场浸泡里还出过一次值得记的误诊：真板和仿真板同在约 45 秒掉拍，咱们一度归罪于 MTTCG 的异构竞态，咱们复查之后才发现，两板掉拍的位置是一致的、单独手测也全部通过，真凶咱们找到了：喂拍代码自己把节奏越拉越稀。两板掉在同一个位置的现象，就是测试代码自己的指纹。咱们在下判断之前，得把测试自身的 bug 排除掉。断言绿和系统稳咱们得分成两回事看，这个教训后来直接影响了板侧的取证设计（本章末节）。

## 关键节点怎么落：PMIC、调压器、eMMC、串口

咱们把分拣方法论落到具体节点上，挑四个最有代表性的过一遍。下面的内容，都以咱们翻译后的板级设备树原文为准。

咱们从电压树的根看起：整棵树从 `vcc12v_dcin` 出发，是 12V 直流输入的 fixed regulator（固定电压电源的设备树节点），而且一直常开，所以板上的大件都从这两级取电。第一级咱们降到 `vcc5v0_sys`，拿它供全板的 5V 系统电，也同样是常开的。板级 dts 的惯例是把根和各级都建成 fixed regulator 节点，`always-on`/`boot-on` 咱们标清楚，然后下面的 PMIC 和外置调压器再一层层挂 `vin-supply` 引用上去。这两级电压的原文咱们摘出来看：

```dts
vcc12v_dcin: regulator-vcc12v-dcin {
	compatible = "regulator-fixed";
	regulator-name = "vcc12v_dcin";
	regulator-always-on;
	regulator-boot-on;
	regulator-min-microvolt = <12000000>;
	regulator-max-microvolt = <12000000>;
};

vcc5v0_sys: regulator-vcc5v0-sys {
	compatible = "regulator-fixed";
	regulator-name = "vcc5v0_sys";
	regulator-always-on;
	regulator-boot-on;
	regulator-min-microvolt = <5000000>;
	regulator-max-microvolt = <5000000>;
	vin-supply = <&vcc12v_dcin>;
};
```

`compatible = "regulator-fixed"` 是"固定电压电源"的类型标识，`regulator-always-on` 和 `regulator-boot-on` 就是常开、上电即开，`vin-supply = <&vcc12v_dcin>` 这一句写的是 vcc5v0_sys 的输入接在 12V 那级下面——12V 转 5V 这层关系，在设备树里就是这么表达出来的。

**rk806 PMIC（spi2）咱们从这颗说起。** 单颗 rk806 咱们做成 `pmic@0` 挂在 spi2 下，spi 时钟咱们看下来就是 1MHz，引脚复用咱们走 `spi2m2` 组。再看它的供电输入，vcc1 到 vcca 十四路里大多数咱们挂到 `vcc5v0_sys`，vcc13/vcc14 挂的是 `vcc_1v1_nldo_s3`，那个 1.1V 是板载 LDO（低压差线性稳压器）给的，PMIC 自己出不了这一路。原因注释里写明了：单 rk806 的板子没有 PMIC 片上的 1.1V 输出，所以得由板子自己补。咱们查到原厂板缺这一路片上电源，就把这个硬件事实换成了主线语法的 fixed regulator 节点，处理思路是第二堆的标准做法。挂 PMIC 的那条总线和芯片本体，原文长这样：

```dts
&spi2 {
	status = "okay";
	assigned-clocks = <&cru CLK_SPI2>;
	assigned-clock-rates = <200000000>;
	pinctrl-names = "default";
	pinctrl-0 = <&spi2m2_cs0 &spi2m2_pins>;
	num-cs = <1>;

	pmic@0 {
		compatible = "rockchip,rk806";
		spi-max-frequency = <1000000>;
		reg = <0x0>;
		...
	};
};
```

spi2 是 RK3588 的第 2 号 SPI 串行总线控制器，PMIC 就挂在这条总线上当从设备。`spi-max-frequency = <1000000>` 就是咱们说的 1MHz 时钟；rk806 这颗芯片负责管板上十几路电压，节点内部的完整调压器树，就是咱们前面说的"照单全收"那一整块。

**CPU/NPU 外置调压器（i2c0/i2c1）咱们照原厂收。** 这三颗都是 Rockchip 自家的 buck（降压变换器）：i2c0 上 `0x42` 咱们放的是 RK8602，供的是 CPU big0 簇，`0x43` 咱们放的是 RK8603，供的是 big1 簇，i2c1 上 `0x42` 咱们又放了一颗 RK8602，供的是 NPU。这三颗管的正是 CPU 三簇：big0、big1 是四颗 A76 大核分成的两簇，little 对着的是四颗 A55 小核。节点咱们摘录如下（big0 那颗）：

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

compatible 咱们要注意，只写精确的 `rockchip,rk8602`，兜底兼容名咱们不写，也就是 fallback：给驱动兜底认领的第二串 compatible。为什么写不得，后面误诊部分咱们用一场病来讲。`resets` 那两行是咱们把 I²C 控制器的功能复位和 APB 总线复位两个复位域交给了内核，其实就是后来那场病的药引子，误诊部分咱们回到它。CPU 八个核的 `cpu-supply`/`mem-supply` 引用，咱们按 big0/big1/little 三簇分别接好，big 簇的核电和内存电由同一颗芯片的双标签提供（big0 用的是 RK8602：big1 用的是 RK8603）：一颗芯片咱们挂两个名字，cpu-supply 和 mem-supply 咱们各引一个。

**eMMC（sdhci）咱们原样搬进主线。** 这个节点咱们跑的是八位总线，HS400 增强选通咱们开了，而且不可拔。`aliases` 里咱们写 `mmc0 = &sdhci`，为的是后面 root 设备号的确定性。节点原文咱们摘出来：

```dts
&sdhci {
	bus-width = <8>;
	mmc-hs400-1_8v;
	mmc-hs400-enhanced-strobe;
	no-sdio;
	no-sd;
	non-removable;
	status = "okay";
};
```

sdhci 是 RK3588 的 eMMC 控制器，SDHCI 是"SD 主机控制器接口"的缩写，一套通用的存储控制器标准。`bus-width = <8>` 是八位总线，`mmc-hs400-*` 那两行是 HS400 高速模式和它的增强选通，`non-removable` 就是"不可拔"——eMMC 焊在板上，不像 SD 卡能拔。

**串口（uart2）咱们单独说。** 这是全板最特殊的一个节点：`&uart2 { status = "disabled"; }`。全板在用的控制台恰恰就是这个串口。disabled 是咱们说给内核通用串口驱动（DesignWare 8250）听的：FIQ 调试器要独占这个 UART，所以 8250 驱动绝不能碰它，等咱们把控制台切到 ttyFIQ0 之后，内核里就看不到 ttyS2 了（首启那阵它还是控制台的事，后面首启部分的日志里有）。控制台的本体是顶层那个 `fiq_debugger: fiq-debugger` 节点，咱们配 `rockchip,serial-id = <2>` 和 `rockchip,irq-mode-enable = <1>`，跑的是原厂板的 IRQ 模式（调试口用普通中断收发数据），波特率咱们定 115200。两个节点咱们摘出来看：

```dts
&uart2 {
	status = "disabled";
};
```

uart2 是 RK3588 的第 2 号串口（UART），板子的调试串口就是它。`status = "disabled"` 就是那句说给 8250 驱动听的话——这个 UART 不许它碰。

控制台本体的完整节点是：

```dts
fiq_debugger: fiq-debugger {
	compatible = "rockchip,fiq-debugger";
	rockchip,serial-id = <2>;
	rockchip,wake-irq = <0>;
	/* Vendor board mode: FIQ debugger backend using the UART IRQ. */
	rockchip,irq-mode-enable = <1>;
	rockchip,baudrate = <115200>;
	/* Mainline RK3588 GIC uses the fourth affinity cell. */
	interrupts = <GIC_SPI 423 IRQ_TYPE_LEVEL_LOW 0>;
	pinctrl-names = "default";
	pinctrl-0 = <&uart2m0_xfer>;
	status = "okay";
};
```

`rockchip,serial-id = <2>` 是"我用的是 2 号串口"，`rockchip,irq-mode-enable = <1>` 是 IRQ 模式，`rockchip,baudrate = <115200>` 是波特率。那行英文注释 `Mainline RK3588 GIC uses the fourth affinity cell` 说的是 `interrupts` 末尾那个 0——就是前面方法论里讲的第四个中断单元（中断亲缘性）。

dts 里还住着几位别的房客，多数本章不展开只报名字：i2c2 上的 GT911 触摸（LCD 章的另一半内容），显示管线的 dsi0、面板和背光电源轨（LCD 章）。GMAC0 咱们摘出来看一眼，因为下一节启动成功的清单里它还要露脸：

```dts
&gmac0 {
	clock_in_out = "output";
	phy-handle = <&rgmii_phy0>;
	phy-mode = "rgmii-rxid";
	pinctrl-names = "default";
	pinctrl-0 = <&gmac0_miim
		     &gmac0_tx_bus2
		     &gmac0_rx_bus2
		     &gmac0_rgmii_clk
		     &gmac0_rgmii_bus>;
	tx_delay = <0x44>;
	rx_delay = <0x00>;
	status = "okay";
};
```

gmac0 是 RK3588 的千兆以太网控制器，GMAC 是"千兆媒体访问控制器"的缩写，就是 SoC 里负责收发网络包的部件。这段把它打开，接到板上的 RTL8211F 网卡芯片（PHY，负责把数字信号变成网线电平）上，走 RGMII 接口（控制器和网卡芯片之间的一种高速连接）。详细复位和时序归网络章。往后每一章咱们回来翻 dts，都能找到自己要住的房间。

## 内核配置：主线底座加板级片段

咱们的内核配置分两层：主线底座加板级增量。底座咱们直接用 `arch/arm64/configs/defconfig`，它带来了什么，kernel.config 的头注释里有原话：`Merged onto arch/arm64/configs/defconfig (pulls ARCH_ROCKCHIP + pinctrl/clk + SERIAL_8250 + MMC_SDHCI + EXT4 + the bulk of RK3588 drivers)`。咱们翻过来讲，底座替咱们拉起了平台支持、时钟、引脚、串口、存储、ext4 这一片基础。板级差异咱们全部写进 kernel.config 这个配置片段，构建时咱们把两份合并。底座升级时咱们也不怕，片段的每一行咱们都留着“为什么开”的注释，咱们也不会让它烂在一个巨大的自定义 defconfig 里。本章相关的几组，咱们挑出来说：

**FIQ 调试器的配置咱们一组全开。** `CONFIG_FIQ_DEBUGGER*` 咱们一连开了五个，外加咱们又补一发 `CONFIG_ROCKCHIP_FIQ_DEBUGGER`。配套纪律咱们写在片段注释里，原话咱们抄在这里：`uart2 itself is disabled in the board DT and must never bind to ttyS2`。翻译过来就是：uart2 在板级设备树里已经停用了，咱们绝不允许它绑成 ttyS2。8250 驱动本身咱们保留，别的 UART 还要用。片段的原文长这样：

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

**RK860X 与 FAN53555 咱们一开一关。** 这一发咱们开 `CONFIG_REGULATOR_RK860X=y`，同时咱们显式写上 `# CONFIG_REGULATOR_FAN53555 is not set`。为什么咱们要关掉一个主线驱动？片段注释给咱们留了原话：`Do not let the generic FAN53555 driver claim these Rockchip regulators`。咱们翻译过来，就是不许通用驱动认领这几颗 Rockchip 调压器的。这是后面那场病的主角，配置立场咱们搁在这儿。

**取证栈咱们全开在片段里。** `CONFIG_PSTORE/PSTORE_CONSOLE/PSTORE_RAM` 帮咱们把内核恐慌（panic，内核崩溃时的紧急记录流程）记录和滚动控制台留在保留内存里，软锁检测、硬锁检测、僵死任务检测、工作队列看门狗咱们全开且触发即内核恐慌，`CONFIG_PANIC_TIMEOUT=10` 咱们让板子恐慌后 10 秒自动重启，`CONFIG_DW_WATCHDOG` 咱们给 systemd 喂硬件看门狗。这套装备怎么用，咱们在本章末节见。

**reboot-mode 咱们只配一行。** 这一行咱们配 `CONFIG_SYSCON_REBOOT_MODE=y`，对应的就是设备树里那个 reboot-mode 节点。上一章讲过这个功能的两半：U-Boot 侧读 `0xfd588080` 分流，内核侧就是咱们这组配置加设备树节点，咱们敲一句 `reboot loader`，板子就重启进 rockusb 了。

咱们还有一条贯穿全部的纪律：片段里全 `=y`、零模块。这是 busybox（根文件系统用的精简工具集）没有 modprobe（加载内核模块的命令）逼出来的，`CONFIG_RTW88` 的注释里记着菜单开关的教训，原话咱们抄在这里：`menu gate — children (CORE/USB/8723D/8723DU) are invisible to olddefconfig without it`。咱们翻过来讲：总开关咱们不开，子项对配置工具就是不可见的，咱们已有的 =y 行也会被悄悄丢掉。零模块的纪律在 v7.3.1 补丁重放时白赚了一笔：根文件系统里没有模块目录要同步，咱们讲到追上游稳定分支时细讲。

至于 `CONFIG_DRM_PANTHOR`（GPU 固件内嵌的两行配置咱们也留在片段里）、网卡强制 `=y`、无线、调频，分别归 GPU、网络、外设三章的内容，配置咱们留在片段里不挪窝，本章咱们不展开。

## 首次启动：波特率、root 设备号、设备树，三件事

U-Boot 把内核镜像交给内核之前的链路，上一章咱们都铺好了（boot.scr、`mmc read 0x08000000 0x6000 0x20000`、bootm，镜像咱们用 FIT 打包，FIT 是 U-Boot 的一种镜像封装格式）。咱们要让内核真跑到 systemd，还有三个板级细节要咱们敲定，否则咱们会分别卡在波特率乱码、等根设备、设备树不匹配上：

1. **串口波特率全链 115200。** 原厂默认是 1500000，topeet 这块板全链是 115200：DDR 固件（比 U-Boot 更早跑、负责初始化内存的那级固件）侧咱们用瑞芯微的 `ddrbin_tool` 工具改参数，U-Boot 侧 `CONFIG_BAUDRATE=115200`，内核侧控制台参数带 `115200`。三方任何一方不对齐，串口看到的都是乱码，而且乱码长得跟“板子挂了”一模一样。
2. **root=/dev/mmcblk0p3。** topeet 的 eMMC 在内核里枚举成 mmcblk0，而咱们手里上一块板 RK3568-ATK 是 mmcblk1。照旧经验咱们写 `mmcblk1p3`，内核就永远停在 `Waiting for root device`。U-Boot 里 eMMC 恒为 `mmc 0`，两边说的是同一块存储，编号体系不一样而已。设备树 `aliases` 的 `mmc0 = &sdhci` 就是给这个枚举兜底。
3. **设备树换成 rk3588-topeet。** 最小可用阶段的 evb1 参考板设备树，到这一步退休。

咱们把这些细节对齐是在 2026 年 7 月 27 日，板子随即第一次启动到了 Ubuntu 的 systemd：主机名是 `rk3588-topeet`，咱们看到的默认目标就是 graphical.target（图形界面），串口 115200 咱们全程看着都可读。驱动探测成功的全清单咱们抄在这里：

- 8 个 CPU（A55×4 + A76×4）、16GB 内存
- eMMC HS400、PMIC rk806
- 调压器 fan53555（当时误认领 RK860X）
- GMAC0 RGMII、GPU Panthor Mali-G610、USB host

“误认领 RK860X”是咱们事后回看才敢下的判语：当时的移植记录里记的原话是“rk8602(fan53555)”，隐患那时其实已经埋下、只是还没发作。

首次启动当天的日志咱们没有归档原件。归档里最早的全量启动日志，是咱们 8 月 1 日早晨那一轮，那时咱们还在 ttyS2 控制台时期：

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

咱们逐行核对：`Machine model: Topeet RK3588 Board (iTOP-RK3588)` 说明咱们亲手翻译的设备树被内核认了，`Mounted root ... on device 179:3` 里 179 是 mmcblk 的主设备号、3 就是 mmcblk0p3，然后 Ubuntu 26.04 的 systemd 顶着 graphical.target 起来了。earlycon 参数咱们配的是 `earlycon=uart8250,mmio32,0xfeb50000`，这是后来控制台切到 ttyFIQ0 时才进启动参数的（上面这段首启的命令行里还没有它），交接给真正的控制台之前，它给咱们保证最早期的打印不丢。

## 一场误诊带出一场真病：ttyFIQ 与 rk860x 的 I²C 卡死

首次启动跑通了、GNOME 桌面也点亮了之后，咱们把控制台从 ttyS2 切到原厂式的 ttyFIQ0，病就来了。当时的调试记录里给咱们留了一段难得的完整病历，其中就包括一次被纠正的误诊。

### 症状：控制台换成 ttyFIQ0 之后，板子“挂死”

原厂的调试口是 ttyFIQ0，由 FIQ 调试器给咱们暴露出来。咱们照原厂架构把整套东西移植过来，移植量咱们数过：`drivers/soc/rockchip/fiq_debugger/` 整目录 16 个文件、3990 行，含 RK UART 后端和 TrustZone 安全扩展的适配层。原厂 5.10 用到的、主线已经删除的内核接口，咱们全部换成了 7.1 的等价物。换上之后症状就来了：系统咱们进得去，但 ttyFIQ0 上咱们无法输入，过一会儿咱们就看到乱码，在咱们眼里整块板子就是挂死了。启动末尾同时冒出了 CPU4/CPU6 调压失败的报错。

### 误诊与纠正

咱们第一反应，容易把矛头指向刚换的控制台：ttyFIQ0 是不是没注册成功？日志一查，注册路径其实全通了：

```
[    0.553407] Registered FIQ tty driver
[    0.788953] fiq_debugger_probe: could not install nmi irq handler
[    0.795679] printk: legacy console [ttyFIQ0] enabled
```

中间那行 `could not install nmi irq handler` 咱们一开始看着也吓人，其实是正常路径：板级配置 `rockchip,irq-mode-enable = <1>` 本来就跑 IRQ 模式（启动参数里 `irqchip.gicv3_pseudo_nmi=0`），FIQ 调试器在 NMI（不可屏蔽中断）不可用时退回了普通中断处理，这是原厂的既定行为。控制台注册了、使能了，咱们确认病不在它身上。

真凶是咱们在日志末尾找到的，咱们接着往下看：

```
[   11.095227] cpu cpu6: _set_opp_voltage: failed to set voltage (925000 925000 1000000 mV): -110
[   11.095235] cpu cpu6: Failed to set regulator voltages: -110
[   11.095238] cpufreq: __target_index: Failed to change cpu frequency: -110
[   14.171224] cpu cpu4: _set_opp_voltage: failed to set voltage (987500 987500 1000000 mV): -110
```

还有更早的三行日志，咱们当时没把它们当回事：

```
[    1.178913] fan53555-regulator 1-0042: FAN53555 Option[10] Rev[1] Detected!
[    1.179404] fan53555-regulator 0-0042: FAN53555 Option[10] Rev[1] Detected!
[    1.180107] fan53555-regulator 0-0043: FAN53555 Option[10] Rev[1] Detected!
```

### 根因链：错误的驱动加载成功，比加载失败更危险

咱们把三行 `FAN53555 Detected` 和设备树对上，事情就清楚了。板上那三颗 RK8602/RK8603（i2c0 的 0x42/0x43、i2c1 的 0x42）本该由原厂的独立驱动 `rk860x-regulator` 管，主线 7.1 里咱们找不到它，通用的 fan53555 驱动却认领了 RK8602。更糟的是旧版设备树学原厂把 RK8603 写成 `"rockchip,rk8603", "rockchip,rk8602"` 的兜底兼容名，于是连 RK8603 也被 fan53555 当 RK8602 认走了。咱们知道 CPU 调频要改电压，fan53555 就用它自己的语义去敲 RK860X 的 I²C 寄存器，这笔传输超时了，咱们拿到的返回值是 `-ETIMEDOUT`（-110）。

结果还有第二层。咱们查到主线 RK3x I²C 驱动超时后不做原厂那套恢复：从设备拉死时钟线（SCL，I²C 的时钟线）的状态检测主线里找不到，两组复位咱们也等不到。咱们要是碰上从设备拉住时钟线，控制器就可能僵死到咱们没法救。而挂在这颗僵死的 I²C 控制器上的，偏偏是 CPU 大核调压器，咱们调频改压全要从它身上走。于是咱们看到的症状就是：调频失败、控制台输入失去响应、系统整个停住。控制台咱们核对下来只是受害者，凶手是另有其人的。

### 修复：一次合并，一个候选

修复咱们全部落进同一个改动，咱们一次做完下面五步：

1. 原厂的 `rk860x-regulator.c` 咱们移植到主线 7.1（只改 I²C 探测接口和已删除头文件的适配）。
2. kernel.config 里咱们关 FAN53555、开 RK860X，杜绝双驱动竞争。
3. 设备树咱们用精确 compatible，不再写兜底兼容名。
4. i2c0/i2c1 节点咱们补 `i2c`/`apb` 两组复位（就是关键节点部分设备树里那两行的来历）。
5. RK3x I²C 超时路径咱们移植原厂的四件套：中断挂起寄存器日志、从机时钟拉住检测、两组复位、总线时序重算。

咱们在 2026 年 8 月 1 日烧板验证：系统正常进入了，ttyFIQ0 咱们持续输入，也再没碰上挂死了，板验后内核日志里 RK860X 和调频的 -110 全部消失。烧板之前咱们过了四道静态检查，当时的记录里有：

1. 咱们把整套补丁按序重放到上游 v7.1 的干净树上，这一步咱们没遇到冲突，全量编译咱们也过了。
2. 咱们核对 `.config`：RK860X 开、FAN53555 关，都对上了。
3. 咱们查 `vmlinux` 的符号表：含 `rk860x_regulator_probe`、`rk3x_i2c_xfer_common` 等新符号，fan53555 的符号咱们找不到。
4. `rk3588-topeet.dtb` 咱们在工作树和干净回放树上各算一次哈希，两边是完全相同的，FIT 咱们封进当轮产物，update.img 的打包回读自检咱们也跑通了。一轮咱们只保留一个有证据的候选，这套检查咱们跑下来，“烧一次就过”就从运气变成了纪律。

板验后内核日志残留的三条报错，咱们核对过都不在本故障域：FIQ 调试器探测互斥的备用中断打过两次 `-ENXIO`（控制台实际已注册，咱们保持原厂的 IRQ 模式，不为清日志伪造不存在的中断），外加一条无线子系统早期加载监管数据库失败的 `-2`（咱们留给无线章）。

还有个后续咱们要交代明白。原厂驱动给 RK3588 这代控制器（版本号 v5）配的 auto-stop 状态机咱们也移植过，瞄准的是调压传输里 START 等待状态的卡死，中断挂起寄存器（IPD）卡在 0x10 的样子咱们见过。不过 auto-stop 状态机和触摸轮询两处改动，咱们做成了一对耦合实验，候选镜像咱们没能可靠跑到登录界面，所以咱们有意把这两步从序列里摘掉了，咱们只把它们作失败证据留档。活下来的超时恢复，是前一步里那套聚焦的版本。

另外当时的记录末尾有一段诚实纠偏，咱们照录在这里：8 月 1 日的板验只证明当轮启动和输入恢复正常，“RK860X 移植消除了所有随机挂死”这个更强的命题咱们证明不了，因为后续咱们仍遇到过间歇性挂死，不能把不同的故障合并成一个“已解决”。

同期的触摸也还在闹别扭：Goodix 探测复位后 I²C 读超时 -110，但用户态的 `i2ctransfer` 能读到 911，说明总线是通的、芯片也有应答，要审的重点在复位和中断脚的时序上，触摸的后续调查咱们交给 LCD 章接手。这两桩没结的案子，本章末节咱们搭起取证三件套来接。三件套咱们配的是 ramoops、硬锁检测器和硬件看门狗，其中 ramoops 是把崩溃日志写进保留内存用的。

当时的记录里留下的教训，咱们原样抄给各位：

- 控制台最后一条日志附近出现挂死，不等于控制台驱动就是根因。咱们得验证注册路径，验证通了再去其他子系统找确定的错误。
- 兜底兼容名不是无害兼容。RK8603 兜底到 RK8602，让错误的驱动加载成功，比加载失败更危险。
- 原厂同板 SDK 的价值不只在设备树，还有超时恢复这类低概率硬件状态机处理。主线接口咱们可以适配，语义不能删。
- 反复烧板之前，咱们必须做干净的补丁重放、全量链接、镜像哈希比对和打包回读自检，自始至终只保留一个有证据的候选。

## 追上游稳定分支：从 v7.1 到 v7.3.1

时间线咱们快进到 11 月。v7.1 线咱们板验收官，当天咱们拍板跟上最新稳定分支，那时咱们确认过上游还没有 7.3.2、7.4。

### 预审：把上游变更日志通读一遍

咱们在重放之前，把 7.2、7.3 两个大版本的变更日志完整扫了一遍，逐条对照整套补丁触达的子系统，预审的判断是“重头补丁零重写、最多动几个改动块（hunk，diff 里的一段改动）”。事后兑现得出奇地准：整套重放下来，实际只动了两处。

### 序列瘦身：升级收编了哪些旧修复

升级给咱们带来一笔瘦身。原序列里咱们放着的五个改动，是当年的回迁补丁（backport），也就是把新版内核修复搬回旧版的那批。咱们具体数一数：调频调度器里的一处竞争修复，调频电压表查表处的一处竞争修复，还有无线驱动的三连修复。咱们这边内核一升级，上游就把这些修复吃进树里了，咱们自己再背着就是重复，于是咱们把它们全部删掉。同一批咱们新增了一个节点：重启进下载模式的 reboot-mode，配合上一章咱们刚点亮的 rockusb。

### 真正动了两处

**面板驱动咱们遇到的是 API 改名。** v7.2 起 `of_drm_get_panel_orientation()` 改名为 `drm_of_get_panel_orientation()`（签名同形：只是搬到了 drm_of.h 这个头文件），咱们改了调用点、补了 include，属于纯改名、没有语义差的改动。面板驱动本身是 LCD 章的内容，这里咱们只记重放的改动。

**板级设备树咱们重做了 Makefile 接线。** 设备树的 Makefile 是按字母序排的单行列表，咱们这一行的插队位置在两块已有板之间。v7.3 上游在附近新收了几块板，插入点周围的上下文行变了，补丁尾部的上下文于是失效。咱们重排之后插入位没变，前后邻居咱们也没换。

其余的改动（FIQ 调试器、RK860X、触摸、显示时钟、调频、网卡这些）零改动，咱们把它们原样落到 v7.3.1，印证了咱们的预审：7.2、7.3 没动咱们重头的区域。配置片段侧的增量只有一行 `CONFIG_SYSCON_REBOOT_MODE=y`，合并后咱们把中断、网络、显示、调频、无线这些关键符号逐个对着 `.config` 审过，全部符合咱们的预期。

### 白捡的修复与两个语法错

升级还白捡了一批上游修复，咱们零动作白拿：GPU 驱动的内存回收改进、RK3568 网卡的链路协商修复、视频解码器的安全修复、一处显示时钟的显式使能，外加咱们还白得一批新板设备树。头两处正好是 GPU 章和网络章用得上的修复。

重放时咱们另写出一个设备树语法错，值得记下来：设备树编译器（dtc）不吃 cell 值里的算术表达式，reboot-mode 节点里这行 `mode-ums = <REBOOT_FLAG + 12>;` 咱们一写就报语法错，绑定头文件里咱们又找不到现成宏，最后咱们用字面量 `<0x5242C30C>` 加注释交代来历。同一场里咱们还学到：往 dts 追加 SoC 级节点必须包进 `/ { }`，顶层咱们要是裸写 `syscon@…` 就会报语法错，咱们的第一版就死在这。

### 零模块纪律的红利与板验

前面说的“片段全 =y、零模块”在这里兑现了：根文件系统树内没有 `/lib/modules` 依赖，TFTP（通过网络直接下载文件的简单协议）拉什么内核咱们就跑什么内核。NFS 根文件系统咱们也不用做任何同步动作，它就是咱们把局域网目录直接挂成根目录。v7.3.1 的构建咱们验过：`Linux version 7.3.1-00020` 这个版本串对上、Image 51MB，整套补丁咱们重放得干干净净、没有触发任何回滚，关键配置符号的审计咱们 15/15 全部通过。板侧验证咱们走 TFTP 加 NFS，全程咱们都不用烧录，网络引导的机制细节是网络章的正题，这里咱们只当验证手段用。咱们在 U-Boot 串口打断自动启动之后：

```
setenv ipaddr 192.168.50.99
setenv serverip 192.168.50.5
tftp ${scriptaddr} boot-tftp.scr
source ${scriptaddr}
```

2026 年 11 月 1 日深夜咱们板验通过，一轮就过了。验收线是这样的：串口出现 `Linux version 7.3.1-00020` 的版本串，`VFS: Mounted root (nfs filesystem)` 说明网络根文件系统挂上了，进 shell 后 `uname -r` 咱们对上了，显示管线回归咱们也验过（LCD 亮 GNOME），咱们敲 `reboot loader`，板子就进了 rockusb。

这轮验证用的产物目录是 `out/rk3588-topeet/tftpboot/`，Image、设备树和引导脚本咱们都放在里面。旧的 eMMC 引导镜像 boot.img 和原厂 SDK 时代的产物，咱们留档在同目录。引导脚本的内容就是上面那套引导逻辑的固化，原文咱们抄在下面：

```sh
setenv bootargs console=ttyFIQ0 root=/dev/nfs nfsroot=192.168.50.5:/home/charliechen/rk-forge/out/rk3588-topeet/rootfs,vers=3,tcp ip=192.168.50.99:192.168.50.5::255.255.255.0::eth0:off rw
tftpboot ${kernel_addr_r} Image
tftpboot ${fdt_addr_r} rk3588-topeet.dtb
booti ${kernel_addr_r} - ${fdt_addr_r}
```

bootargs 咱们除了写控制台和 NFS 根，剩下的就是那七段网络参数了，写的是这块板的静态网络位置（本机地址、服务器地址、网关咱们留空、子网掩码、主机名留空、网口名、关闭自动配置），然后咱们依次下载内核和设备树，最后咱们用 `booti` 引导。脚本改动后咱们用 `mkimage` 重新生成为可执行的 scr。eMMC 侧的 boot.img 咱们也已重打包为 v7.3.1，下次咱们烧录时自然就带上了。还遗留一条诚实记录：仿真侧的一个适配改动这次咱们没验，那是仿真线的资产，下次仿真跑时咱们再核。

## 本章的活儿和后续各章的分工

本章咱们自己干的活是四件：设备树咱们全量翻译，调试口咱们整个移植，调压器咱们配上恢复，最后加上重启进下载模式的节点。同一批内核改动里还住着别章的主角，咱们一章一章看：面板驱动（树外 DRM 面板驱动：回放原厂的初始化字节序列），触摸的时序与轴映射，显示控制器的时钟交接和格式支持，归的都是 LCD 章。调频的事务语义与护栏的移植，归的是外设章。网卡的常开、复位和时序，归的是网络章。升级后被上游收编而删掉的五个回迁改动，咱们讲序列瘦身的时候说过。摘除的 auto-stop 状态机与触摸轮询这对失败实验，咱们讲病历的时候也说过。每处改动的完整内容都在各自章节里展开，这里咱们不再重复。

## 无声硬锁：为看不见的死准备取证

本章的方法论咱们压轴来讲。前面的病案里留了一个没结的案子：随机挂死没有被彻底归因。RK3588 上的随机挂死咱们领教过，狠就狠在咱们一个报错都收不到、板子直接无声死掉。ttyFIQ0 跑的是 IRQ 模式（原厂行为、启动参数 `irqchip.gicv3_pseudo_nmi=0`），挂死发生时连调试器的触发串咱们都收不到响应。咱们手里的证据说明故障至少深入到三者之一：

- 某 CPU 长时间关本地中断
- 中断控制器或串口不再投递中断
- 全局互锁或 SoC 级硬锁

这三者咱们手里的证据区分不了，但足以帮咱们排除“系统还能调度、只是终端卡住”的温和解释。

既然死前咱们一个字都打不出来，咱们就让板子自己把遗书写在掉电不丢的地方。装备咱们分三层搭，配置全放在 kernel.config 的 Persistent lockup diagnostics 段，段首注释把思路给咱们写得很直白，原话咱们抄在这里：`ttyFIQ0 runs in IRQ mode and provably never answers during a hard lockup, so detection is watchdog-based`。咱们翻过来讲：ttyFIQ0 跑在 IRQ 模式下时被证明是不会应答的，所以检测只能靠看门狗这一系。

**咱们装备的第一层是 ramoops/pstore**，它是内核把崩溃日志存进一块预留内存的机制。咱们在保留内存里开一块 ramoops 窗口，咱们用 `CONFIG_PSTORE_RAM` 把内核恐慌记录和滚动控制台存进去，这块内存咱们让它跨看门狗暖重启保留，咱们断电的话记录就没了。窗口位置有个主线特有的教训咱们吃过：最初咱们照原厂用 `0x110000` 低地址窗口，但主线的启动链在内核挂 pstore 之前就把那片内存清了。清内存的是启动早期初始化内存的两级固件（TPL 和 ddrbin），于是咱们把窗口搬到 `0x10000000`。板级设备树里咱们定型成这样：

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

record-size 咱们给每条恐慌记录 128KiB，console-size 咱们给滚动控制台留 512KiB。启动日志里咱们能看到内核认领它：

```
[    0.000000] OF: reserved mem: 0x0000000010000000..0x00000000100dffff (896 KiB) map non-reusable ramoops@10000000
```

**咱们的第二层是不依赖 pseudo-NMI 的检测器。** pseudo-NMI 咱们知道，是把普通中断按不可屏蔽中断对待的机制。软锁检测加中断风暴检测、伙伴核代查的硬锁检测（一颗 CPU 停摆时，由仍在运行的伙伴 CPU 代它查岗）、60 秒僵死任务检测、工作队列看门狗，咱们让它们全部触发即内核恐慌，咱们再配 `CONFIG_PANIC_TIMEOUT=10` 让它到点自动重启。伙伴检测咱们选来做保底，是有实测依据的，咱们在 kernel.config 同一段注释里能读到当时的实测：以性能计数器中断当唯一检测手段时，一次 280 秒的压力压出的停摆，没有任何硬锁报告（最后是 RCU 停摆报告抓到的。RCU 是内核的一种无锁同步机制，它停摆往往是内核卡死的信号），而它依赖的硬件前提咱们在板上验证不了，于是咱们把 `CONFIG_HARDLOCKUP_DETECTOR_PREFER_BUDDY` 回补为底线。顺带一个配置陷阱咱们记着：`CONFIG_ARM64_PSEUDO_NMI=y` 单开不够，这个运行时开关默认是关的，内核命令行咱们得显式带 `irqchip.gicv3_pseudo_nmi=1`。机制边界咱们照实讲：如果所有 CPU、中断控制器或整颗 SoC 同时停摆，任何软件检测器都没有执行的机会，“没有检测器报告”咱们不能读成“没有挂死”。

**咱们的第三层是硬件看门狗兜底。** Ubuntu 根文件系统里咱们固化 `RuntimeWatchdogSec=30s`，systemd 替咱们持续喂的，是 RK3588 挂在 `feaf0000` 的那颗 DesignWare 看门狗。全局停摆时约 30 秒后咱们能等到暖重启，重启后咱们要做的第一件事就是读 pstore：

```sh
find /sys/fs/pstore /var/lib/systemd/pstore -maxdepth 2 -type f -print 2>/dev/null
for f in /sys/fs/pstore/* /var/lib/systemd/pstore/*; do
	[ -f "$f" ] && { echo "===== $f ====="; cat "$f"; }
done
journalctl -b -1 -k --no-pager | tail -n 300
```

取证姿势咱们这里也有讲究，当时的记录写得直白：挂死的时候咱们别急着断电，咱们等上 30 到 45 秒，咱们看板子会不会自己暖重启。45 秒后咱们看到板子仍不重启，说明硬件看门狗在那个冻结状态下也没能替咱们把系统复位，这时咱们改按 reset 做暖复位再读 pstore，咱们不要急着拔电，因为咱们知道 pstore 只在暖重启后幸存。还有一个反直觉的解读规则：如果自动重启了、pstore 里却只有最后一段打印而没有栈，空手而归本身就是咱们手里的证据，因为冻结覆盖了所有还能运行检测器的 CPU 和中断路径，咱们的故障域又收窄了一圈。

这套装备在 8 月 16 日凌晨抓到过一次教科书级的现场，当时咱们跑的是 v7.1、调频调试时期：

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

咱们读下来，遗书信息量很大：伙伴检测器（栈里的 `watchdog_buddy_check_hardlockup`）由 CPU2/CPU4 代查报出 CPU3/CPU5 硬锁，内核恐慌栈里停摆的 CPU 停在 `cpuidle_enter_state`，末尾三行是调频改动挂的恐慌通知回调把三个簇最后的频率电压打了出来，咱们眼看它 10 秒后自动重启，ramoops 咱们留着重启后取证。咱们后来破 LCD 章那场 VOP2 硬锁，读到的现场就是这套组合留下来的 pstore。

## 成功长这样

v7.1 线收官那轮的启动日志，咱们看 2026 年 11 月 1 日这一轮（eMMC 根，ttyFIQ0 控制台）的结尾：

```
[    0.000000] Linux version 7.1.0-00024-ga7dad2806329 ... #60 SMP PREEMPT Sun Nov  1 21:22:37 CST 2026
[    0.000000] Machine model: Topeet RK3588 Board (iTOP-RK3588)
[    0.000000] Kernel command line: console=ttyFIQ0 root=/dev/mmcblk0p3 rw rootwait
...
[    0.056256] Registered FIQ tty driver
...
rk3588-topeet login: root
```

`console=ttyFIQ0` 说明调试口和调压器的修复都在位，ttyFIQ0 能交互的前提是 I²C 不再卡死。日志的结尾那一行，咱们看到的是 `rk3588-topeet login:`，`root` 是咱们敲进去的用户名，shell 是日志收档之后才起来的。当晚咱们再进一步，v7.3.1 咱们经 TFTP 加 NFS 板验，一轮就过了，内核线咱们就此收官。

这一章到尾声了，板子咱们已经从 BootROM 带进了 Ubuntu 的 shell。但桌面还是黑着的：LCD 从 DSI 到 LVDS 的显示管线、TC358775 桥芯片、GT911 触摸，连同要用本章取证装备破案的 VOP2 硬锁，咱们都留给 LCD 章。咱们 LCD 章见。
