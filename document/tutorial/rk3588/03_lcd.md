# LCD 显示：一块没有主线驱动的屏，和三场连环硬仗

> [上一章](02_kernel.md) 里内核已经在板上站住了，DT 移植和补丁序列的方法论咱们也都交过手。这一章就把它们全部押上那块 10.1 寸 1024×600 的屏。主线没有这块屏的 panel 驱动，桥 IC 做的是 DSI 转 LVDS，显示链上偏偏没人这么用过它，VOP2 里还埋着一个会把整块板无声冻死的时钟交接问题。TC358775 出图、VOP2 死机、GT911 触摸这三场硬仗咱们一场一场打下来，结果 GNOME 桌面才第一次亮在玻璃上。

## 显示链路全图：像素从内存到玻璃要过四道门

Linux 内核的显示框架叫 DRM（Direct Rendering Manager），这一章咱们一直跟它打交道。屏幕显示什么、什么分辨率、什么时候刷新，这些事其实归 KMS（Kernel Mode Setting）管，全章都泡在它的抽象里。按 KMS 的抽象，显示其实就是一条链，每一环各配一个驱动、而各管一段：

- **CRTC**：扫描引擎，按行从帧缓冲读像素、按 mode 里的节拍发出去。
- **encoder**：把像素流编码成具体接口的信号，这里是 MIPI DSI。
- **connector**：物理接口在软件里的代表。
- **panel/bridge**：屏幕侧的驱动。panel 驱动管上电、初始化序列、背光。如果中间有转接芯片，还可以再挂一个 bridge 驱动去管它。

这套链路落到咱们这块板上，咱们把它画成下面这样：

```
帧缓冲 fb0
  → VOP2 (fdd90000) 视频端口 vp2          CRTC：RK3588 的显示控制器，共 4 个视频端口
  → DSI0 (fde20000, mipi-dsi2 控制器)      encoder：MIPI DSI 发送端
  → mipidcphy0 (Samsung DCPHY)             物理层：4 条 data lane
  → TC358775 桥 IC（DSI 转 LVDS）           bridge：屏侧转接芯片
  → 10.1" 1024×600 LVDS 面板

GT911 触摸 → i2c2 @ 0x14（独立链路，INT=GPIO3_C0，RST=GPIO3_C1，与显示只共用电源轨）
```

为什么好端端的 LVDS 屏要走 DSI？迅为的手册写得很直白。RK3588 本身其实没有 LVDS 显示输出，所以迅为的 LVDS 屏都是 MIPI DSI 经转接板转出来的，转接芯片就是前面提到的桥 IC，这个说法出自迅为的《iTOP-3588 开发板多屏显示手册 v1.2》。于是这块屏在 DT（内核启动时靠它认硬件的描述数据，也就是设备树）里的身份是 DSI 面板，桥的行为就藏在屏的初始化序列里，咱们后面会在这上面反复吃亏。

还有一个 DSI 的基础概念得立住。**同一条 DSI 链其实有两种工作方式，这一章两种咱们都要打交道**。命令模式你看就像 I2C，一条一条地发寄存器写，初始化拿它做就行了。视频模式反而更像 HDMI，像素流是连绵不断的，正常显示走的就是它。那主机在两种模式之间切换的时机，正是本章第一场硬仗的病灶。

最后交代一个容易被带偏的事实。原厂 SDK（厂商的整套开发源码包）出厂默认启用的屏其实是 MIPI1 那一路的 800×1280（HX8394），触摸用的是 FT5x06。咱们要的 1024×600 + GT911 分支，在原厂的 `topeet-screen-lcds.dts` 里是被注释掉没编译的，文件的开头写着：

```
//#define LCD_TYPE_LVDS_10_1_1024x600_GT911  //VP2
#define LCD_TYPE_MIPI1    //VP3
```

你看，原厂的正常镜像压根没跑过这个分支，咱们能参照的只有原厂源码、没有运行记录可对，这个差别到了触摸一节还会回来算。

## 面板移植：主线没有驱动，自己写一个

原厂 SDK 的内核是 5.10 BSP（板级支持包，厂商随芯片发布的内核源码树），驱动这块屏用的是私有的 `simple-panel-dsi` 绑定，设备树里塞了一段 `panel-init-sequence` 字节块，驱动拿过来做的就是把整段序列原样重放。主线其实没有这个绑定，显示链上也偏偏没人用过这颗桥。摆在咱们面前的就两条路，要么给桥单写一个驱动，要么写一个通用 panel 驱动、原样重放原厂的序列。咱们选了后者，因为桥的寄存器序列是从原厂设备树逐字节搬来的厂商私有数据，重放的改动面最小，桥寄存器的完整语义咱们并不需要全懂。于是落地的是两份改动：一份是面板驱动，一份是板级设备树的显示管线。

驱动骨架是咱们照主线 `panel-himax-hx8394.c` 摹的。注册就交给 `module_mipi_dsi_driver` 了，在驱动的探测函数（probe，内核里驱动认领设备的入口）里再跑 `devm_drm_panel_alloc`，然后照 `drm_panel_funcs` 的接口实现五个回调，列成四条（`disable` 和 `unprepare` 是合在一条里说的）：

- `prepare` 管上电、复位。
- `enable` 负责点亮点后的延时。
- `disable`/`unprepare` 反向关掉。
- `get_modes` 把设备树里 `display-timings` 描述的 mode 报给 DRM core。

初始化序列咱们从设备树的 `panel-init-sequence` 读进来，格式是原厂定的记录流：

```
<u8 type><u8 delay_ms><u8 len><len 个 payload 字节>
  type 0x29 = GENERIC_LONG_WRITE   写桥的厂商寄存器
  type 0x05/0x15/0x39 = DCS 短写/带参短写/长写（这块屏的序列里几乎不出现）
```

重放的核心很直白，就是遍历记录、按 type 分派到对应的 `mipi_dsi_generic_write_multi` 或 `mipi_dsi_dcs_write_buffer_multi`，咱们让它在每条后面睡一个 delay，出了错也不马上返回，而是把错误都聚合在 multi-context 里、最后统一报出。mode 侧直接在探测函数里写死了 4 lane、RGB888、video burst、LPM（低功耗发送模式，命令走低速通道）这一套发命令的配置，跟原厂的完全一致。

设备树这边咱们接着把整条管线挂起来：

- `backlight` 用 pwm-backlight 挂在 pwm1 上。
- `vcc3v3_lcd_n` 是面板 3.3V 电源、GPIO1_B3 使能。
- `&vop`、`&vop_mmu`、`&mipidcphy0`、`&dsi0` 逐个 okay。
- 最后用主线的 OF-graph（设备树里用 endpoint 节点一段段描述连接关系的写法）把 `vp2 → dsi0 → panel` 三段 endpoint 连起来。

这几个代号在主线的基础设备树（SoC 那一级的定义，都住在 `rk3588-base.dtsi` 里）都有本体，咱们逐个认一遍，不然光看 `&vop`、`&dsi0` 不知道它们是谁。

**VOP2（`&vop`）是 RK3588 的显示控制器。** 芯片的图像输出全归它管，里面并排着四个视频端口 vp0 到 vp3，咱们这块板用的是 vp2。它的本体在基础设备树里是这样开头的：

```dts
vop: vop@fdd90000 {
	compatible = "rockchip,rk3588-vop";
	reg = <0x0 0xfdd90000 0x0 0x4200>, <0x0 0xfdd95000 0x0 0x1000>;
	reg-names = "vop", "gamma-lut";
	interrupts = <GIC_SPI 156 IRQ_TYPE_LEVEL_HIGH 0>;
	clocks = <&cru ACLK_VOP>,
		 <&cru HCLK_VOP>,
		 <&cru DCLK_VOP0>,
		 <&cru DCLK_VOP1>,
		 <&cru DCLK_VOP2>,
		 <&cru DCLK_VOP3>,
		 <&cru PCLK_VOP_ROOT>,
		 <&hdptxphy0>;
	clock-names = "aclk",
		      "hclk",
		      "dclk_vp0",
		      "dclk_vp1",
		      "dclk_vp2",
		      "dclk_vp3",
		      "pclk_vop",
		      "pll_hdmiphy0";
	iommus = <&vop_mmu>;
	power-domains = <&power RK3588_PD_VOP>;
	rockchip,grf = <&sys_grf>;
	rockchip,vop-grf = <&vop_grf>;
	rockchip,vo1-grf = <&vo1_grf>;
	rockchip,pmu = <&pmu>;
	status = "disabled";
	...

	vop_out: ports {
		#address-cells = <1>;
		#size-cells = <0>;
		...
	};
};
```

（省略号里是 vp0 到 vp3 四个端口，vp2 下面单独展开。）

`compatible = "rockchip,rk3588-vop"` 就是"我是 RK3588 的显示控制器"这张身份证。`clocks` 里的 `&cru` 是芯片的时钟/复位控制器（CRU，Clock and Reset Unit），`DCLK_VOP0` 到 `DCLK_VOP3` 是四个视频端口各自的像素时钟——主戏二那场死机，就是 dclk_vp2 这一根没交接好。`iommus = <&vop_mmu>` 说它读内存要走一块 IOMMU，`power-domains` 那行是它挂在 VOP 电源域下面。

**`&vp2` 是 VOP2 的 2 号视频端口。** 上面 `ports` 里的 `vp2: port@2` 就是它，展开来只有三行：

```dts
vp2: port@2 {
	#address-cells = <1>;
	#size-cells = <0>;
	reg = <2>;
};
```

`reg = <2>` 给它编的是 2 号。这一章说的 `vp2 → dsi0 → panel`，就是像素流从这个端口出去、送进 DSI 控制器。它是个 port 子节点、不是独立设备，主戏二里"重父写在 `&vp2` 上等于白写"的坑，根子就在这里。

**`&dsi0` 是 MIPI DSI 的发送端控制器。** 它把像素流按 MIPI DSI 协议编码后送出去。本体长这样：

```dts
dsi0: dsi@fde20000 {
	compatible = "rockchip,rk3588-mipi-dsi2";
	reg = <0x0 0xfde20000 0x0 0x10000>;
	interrupts = <GIC_SPI 167 IRQ_TYPE_LEVEL_HIGH 0>;
	clocks = <&cru PCLK_DSIHOST0>, <&cru CLK_DSIHOST0>;
	clock-names = "pclk", "sys";
	resets = <&cru SRST_P_DSIHOST0>;
	reset-names = "apb";
	power-domains = <&power RK3588_PD_VOP>;
	phys = <&mipidcphy0 PHY_TYPE_DPHY>;
	phy-names = "dcphy";
	rockchip,grf = <&vop_grf>;
	status = "disabled";

	ports {
		#address-cells = <1>;
		#size-cells = <0>;

		dsi0_in: port@0 {
			reg = <0>;
		};

		dsi0_out: port@1 {
			reg = <1>;
		};
	};
};
```

`compatible = "rockchip,rk3588-mipi-dsi2"` 是它的身份证，这也解释了第一条陷阱：它是 mipi-dsi2 控制器，config 符号要选 `_DSI2` 不是 `_DSI`。`phys = <&mipidcphy0 PHY_TYPE_DPHY>` 写的是"我的物理层用 mipidcphy0"。一个进（dsi0_in）一个出（dsi0_out）两个端口，就是后面 OF-graph 要接的那两端。

**`&mipidcphy0` 是 DSI 链路的物理层（PHY）。** 控制器把数据打包成逻辑字节，真正把电信号送上 4 条 data lane 的，是这颗 DCPHY。本体：

```dts
mipidcphy0: phy@feda0000 {
	compatible = "rockchip,rk3588-mipi-dcphy";
	reg = <0x0 0xfeda0000 0x0 0x10000>;
	rockchip,grf = <&mipidcphy0_grf>;
	clocks = <&cru PCLK_MIPI_DCPHY0>,
		 <&cru CLK_USBDPPHY_MIPIDCPPHY_REF>;
	clock-names = "pclk", "ref";
	resets = <&cru SRST_M_MIPI_DCPHY0>,
		 <&cru SRST_P_MIPI_DCPHY0>,
		 <&cru SRST_P_MIPI_DCPHY0_GRF>,
		 <&cru SRST_S_MIPI_DCPHY0>;
	reset-names = "m_phy", "apb", "grf", "s_phy";
	#phy-cells = <1>;
	status = "disabled";
};
```

它自己也有独立的时钟和四个复位域。第一轮板验的第一个拦路虎（DCPHY 没编）就是这颗 PHY 没起来，dsi0 也就拿不到它。设备树标签主线拼写是 `mipidcphy0`，原厂写 `mipi_dcphy0`，指的是同一颗。

**`&vop_mmu` 是 VOP2 的内存管理单元（IOMMU）。** 显示控制器要不停读帧缓冲，这块 IOMMU 管的就是它读内存时的地址翻译。本体：

```dts
vop_mmu: iommu@fdd97e00 {
	compatible = "rockchip,rk3588-iommu", "rockchip,rk3568-iommu";
	reg = <0x0 0xfdd97e00 0x0 0x100>, <0x0 0xfdd97f00 0x0 0x100>;
	interrupts = <GIC_SPI 156 IRQ_TYPE_LEVEL_HIGH 0>;
	clocks = <&cru ACLK_VOP>, <&cru HCLK_VOP>;
	clock-names = "aclk", "iface";
	#iommu-cells = <0>;
	power-domains = <&power RK3588_PD_VOP>;
	status = "disabled";
};
```

VOP2 靠 `iommus = <&vop_mmu>` 引用它，所以点亮显示时它俩要一起 okay，漏了哪一个显示都起不来。

`backlight` 和 `vcc3v3_lcd_n` 是板级自己的两个节点，不在 SoC 那级、住在板级 dts 里：

```dts
vcc3v3_lcd_n: regulator-vcc3v3-lcd-n {
	compatible = "regulator-fixed";
	regulator-name = "vcc3v3_lcd0_n";
	regulator-boot-on;
	enable-active-high;
	gpio = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>;
	vin-supply = <&vcc_3v3_s3>;
};

backlight: backlight {
	compatible = "pwm-backlight";
	/* Simple linear ramp (vendor used a low-end gamma curve; swap if needed). */
	brightness-levels = <0 4 8 12 16 20 24 28 32 36 40 44 48 52 56 60 64 68 72
			     ...
			     248 252 255>;
	default-brightness-level = <50>;
	pwms = <&pwm1 0 25000 0>;
};
```

`vcc3v3_lcd_n` 是固定电压电源，`gpio = <&gpio1 RK_PB3 GPIO_ACTIVE_HIGH>` 就是"面板 3.3V 由 GPIO1_B3 使能"那句话的原文——面板没有独立 reset 引脚，复位靠的就是断掉再重上这一路电。`backlight` 是 pwm-backlight，`pwms = <&pwm1 0 25000 0>` 把它挂到 pwm1，`brightness-levels` 那一串是 64 级亮度表（这里截了首尾两行），后面 `BACKLIGHT_PWM=m` 的坑说的就是它没编成内置。

面板节点咱们看节选，而 init 序列只示前两条和末条：

```dts
&dsi0 {
	lcd_panel: panel@0 {
		compatible = "topeet,dsi-panel-seq";
		reg = <0>;
		power-supply = <&vcc3v3_lcd_n>;
		backlight = <&backlight>;
		panel-init-sequence = [
			29 02 06 3C 01 09 00 07 00
			29 02 06 14 01 06 00 00 00
			/* ……共 27 条，全是 0x29 generic long write …… */
			29 02 06 9C 04 31 04 00 00
		];
		panel-exit-sequence = [ 05 05 01 28  05 78 01 10 ];
		display-timings {
			dsi0_timing0: timing0 {
				clock-frequency = <82000000>;
				hactive = <1024>;  vactive = <600>;
				hfront-porch = <1580>; hsync-len = <10>; hback-porch = <100>;
				vfront-porch = <10>; vsync-len = <10>; vback-porch = <25>;
			};
		};
		port { mipi_panel_in: endpoint { remote-endpoint = <&dsi0_out_panel>; }; };
	};
};
&dsi0_in  { dsi0_in_vp2:  endpoint { remote-endpoint = <&vp2_out_dsi0>; }; };
&dsi0_out { dsi0_out_panel: endpoint { remote-endpoint = <&mipi_panel_in>; }; };
&vp2 { vp2_out_dsi0: endpoint@ROCKCHIP_VOP2_EP_MIPI0 {
		reg = <ROCKCHIP_VOP2_EP_MIPI0>;
		remote-endpoint = <&dsi0_in_vp2>; }; };
```

再交代两个硬件上的细节。这块面板**没有独立的 reset 引脚**，复位靠的就是断电重上电，所以驱动里 reset GPIO 是可选的，在这块板上咱们给它留 NULL。触摸的 reset 在 GPIO3_C1，别把它和面板的弄混。config 侧的五个符号数过一遍、一个都不能少：

```
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y       # dsi0 = mipi-dsi2 控制器（NOT _DSI）
CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y  # mipidcphy0 的 PHY 驱动
CONFIG_DRM_MIPI_DSI=y
CONFIG_DRM_PANEL_TOPEET_DSI=y
CONFIG_BACKLIGHT_PWM=y
```

移植过程中咱们攒下了一批致命的陷阱（gotcha），错了任何一个 panel 都是静默不亮，咱们把它们列在这里：

1. **DSI host 的 config 符号是 `ROCKCHIP_DW_MIPI_DSI2`，不是 `_DSI`**。RK3588 的 dsi0 是 `rockchip,rk3588-mipi-dsi2` 控制器，由 `dw-mipi-dsi2-rockchip.c` 绑定，编错符号直接不绑。
2. **PHY 驱动是 `PHY_ROCKCHIP_SAMSUNG_DCPHY`**，设备树标签主线拼写是 `mipidcphy0`（原厂写 `mipi_dcphy0`，BSP 专属）。
3. **序列里的 `0x29` 是 generic long write，不是 DCS（MIPI 联盟定义的屏端命令集）**。`0x39` 才是 DCS 长写。1024×600 整段 `29 ...` 全是给桥的厂商寄存器写。
4. **EOT flag（包尾标志）主线改名了**：原厂的 `MIPI_DSI_MODE_EOT_PACKET` 在主线叫 `MIPI_DSI_MODE_NO_EOT_PACKET`，同一个 bit、名字取反。OF-graph 是主线唯一的路由表达，原厂的 `&route_dsi0`、`&dsi0_in_vp2{status}` 都是 BSP 私有节点，主线没有。这两处都得按主线的写法重新核对，名字不可信，要核语义。
5. **init 序列不补 DCS sleep-out/display-on 收尾**。原厂同文件里 MIPI0/MIPI1 屏的序列都以 `05 .. 11`/`05 .. 29` 收尾，唯独这块不是——当时不敢确定是不是漏了，后来证实桥家族根本不支持 DCS 短写，这段序列靠视频流自启动，是设计使然。
6. **`hfront-porch = <1580>` 照原厂原值保留**。这个值大得离谱（多半是 158 的笔误），但 bridge 的初始化序列就是按这个 mode 配的，改 mode 要跟桥配置匹配。为什么这样也能工作，主戏一的复盘里有答案。

## 第一轮板验：三个 config 拦路虎，四版镜像

代码落好了之后烧进板里。这一轮全是 kernel.config 的问题，不过每版镜像只修得好一个，咱们烧了四版才换来第一缕画面：

| 镜像 MD5 | 改动 | 板上结果 |
|---|---|---|
| `8520c77f` | +直接 bootcmd（LCD 已在镜像内） | panel 永久 deferred：DCPHY 没编 |
| `69d5d278` | +`PHY_ROCKCHIP_SAMSUNG_DCPHY=y` | 仍 deferred：`BACKLIGHT_PWM=m` |
| `b8d0abf3` | +`BACKLIGHT_PWM=y` | DRM 全 bind、背光亮，**屏无画面** |
| `370c0597` | 面板驱动 init→prepare（下一节） | **boot logo 出图 + fb0 灌噪点花屏** |

**碰到的第一个拦路虎是 PHY 驱动没编。**dmesg 里翻到的症状就这一行，panel 链一直停在推迟探测的状态（deferred，驱动等资源、等到了再重试），咱们在 `/dev/dri` 里也看不到对应节点：

```
platform fde20000.dsi: deferred probe pending: dw-mipi-dsi2: failed to get mipi phy
```

此前规划时咱们预设过“DSI2 host 会自动 select PHY 符号”，实测 host select 的只是 `GENERIC_PHY_MIPI_DPHY` 框架，具体到 `mipidcphy0` 这颗 PHY 的驱动，它其实并不负责。结果 PHY 没被探测到，dsi2 也就拿不到 PHY 了，panel 的下场就是跟着干等。咱们拿 `grep PHY_ROCKCHIP_SAMSUNG_DCPHY .config` 一查，查出来的是 `is not set`，加上就好了。

**第二个拦路虎换成了 `BACKLIGHT_PWM=m`。**咱们把 PHY 修好之后，dmesg 变了脸：

```
mipi-dsi fde20000.dsi.0: deferred probe pending: (reason unknown)
```

`(reason unknown)` 反而比具体报错还磨人。这时咱们看两个旁证，`/sys/class/backlight/` 是空的，dmesg 里一行 pwm/backlight 的影子都没有。对上号了，`CONFIG_BACKLIGHT_PWM=m`。backlight 驱动偏偏是个模块，而这个阶段的根文件系统没有 modprobe，backlight 的设备节点也就不会出现，panel 的下场就是卡在 `drm_panel_of_backlight()` 上一直等。config 里只声明 `BACKLIGHT_CLASS_DEVICE=y`（框架）是不够的，具体的驱动得单独 `=y`。显示相关符号咱们又全扫了一遍 `=m`，扫出来的只有 backlight。

这一轮咱们提炼出的经验就一条：**“符号会自动 select”的话别信，显示链路上每个具体驱动的符号都要逐个 `grep .config` 确认 `=y`**。推迟探测的排查顺序也定型了：第一步跑 `dmesg | grep deferred`，看谁在等、等什么，然后查对应的 `/sys/class/...` 是不是空的，最后才轮到查驱动的符号。

咱们把 `b8d0abf3` 烧进板里，DRM 的管线第一次全通：

```
rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[drm] Initialized rockchip 1.0.0 for display-subsystem on minor 0
rockchip-drm: fb0: rockchipdrmfb frame buffer device
```

背光亮了，这说明命令模式是通的，init 序列送到了桥。那咱们往 fb0 灌一把噪点试试：

```sh
head -c 2457600 /dev/urandom > /dev/fb0
```

结果屏上连雪花都没有。像素你看明明在内存里，VOP2 也该是在扫描的，可它们偏偏就是没变成光。第一场硬仗的开局就在这里。

还得记下当时发现的一个怪象，因为到了第二场硬仗还要回到它身上。赶上 DRM 接管 fbcon（内核的文字控制台）的那一瞬间，**偶发**的串口乱码加整板冻结冒出来过，冷启动、热启动的表现不同、非必现。咱们试过 `nomodeset` 或 `fbcon=disable`，倒是都能避开。当时只当是点亮初调（bringup）阶段的偶发噪声，随手记了一行。

## 主戏一：背光亮着，屏是黑的——TC358775 的生命周期

眼下的局面是背光亮、屏黑、dmesg 无报错，这是咱们在显示调试里最不舒服的一类，链路上每一层偏偏都说自己没事。

**第一步咱们用 debugfs 找断点。**跑一下下面的命令：

```
crtc[83]: video_port2
active=1
mode: "1024x600": 47 82000 1024 2604 2614 2714 600 610 620 645 0x48 0xa
connector[85]: DSI-1
	crtc=video_port2
```

咱们从 state 里能读到三个信息。vp2 这一行的值是 `active=1`，说明 VOP2 确实在扫描咱们的 fb0。mode 是 1024×600@47Hz、82MHz 的像素钟，参数正确应用了，hsync_start=2604 也正好对上了 hfront-porch=1580（1024+1580=2604），咱们核对过。connector 绑在了 vp2 上，路由是对的。所以断点在 VOP2 之后，在 DSI 视频编码、PHY 高速模式、桥这三段里偏偏有东西断了。state 的输出还排除了“vp2 不通、该换 vp3”的怀疑：主线另一块 RK3588 板用的是 vp3，但 vp2 实测是通的。

**第二步咱们排除下层驱动。**把主线的 DSI2 core、rockchip 平台适配层（glue）、samsung-dcphy 三份代码跟原厂 BSP 逐行对照：视频模式切换序列（`DSI2_DSI_VID_TX_CFG` + `MODE_CTRL=VIDEO_MODE` + poll 状态）、IPI（DSI 控制器接收像素流的视频输入接口）配置（HSA/HBP/HACT/HLINE/VSA/VBP/VACT/VFP 全套 timing）、lane rate 计算（含 burst 的 10/9 开销）、PHY power_on 序列、GRF（芯片的全局寄存器堆）写，一路比对了下来，寄存器级全部等价、主线没漏写该写的东西。这一步的代价咱们心里有数，可它把下层驱动有 bug 这个假设彻底关掉了，咱们也把“原厂同配置能点亮”变成了更强的约束：配置和驱动都是对的，那问题必然在咱们自己这层之上的某个行为差异上。剩下的两个嫌疑，要么是 VOP2 到 DSI2 的像素喂入没接上，要么是桥没锁住视频同步。

**第三步咱们写自包含诊断文档去会诊。**把症状、证据、已排除项、配置整编成一份不依赖上下文的文档、拿去会诊，换回来两个决定性的认知。第一个认知是**桥其实是 Toshiba TC358775**。init 序列的 payload 是 `[addr_lo, addr_hi, data_le32]`，小端 16 位寄存器地址加 32 位数据。咱们拿这个格式解码序列开头的几条：

```
04 01 01 00 00 00  →  addr 0x0104 (PPI_STARTPPI) = 1
04 02 01 00 00 00  →  addr 0x0204 (DSI_STARTDSI) = 1
9C 04 31 04 00 00  →  addr 0x049C (LVCFG) = 0x431   （LVDLINK=0，single-link LVDS）
```

这些寄存器地址跟主线现成的 `drivers/gpu/drm/bridge/tc358775.c` 的寄存器表逐字吻合，桥的身份就这么定了。认出桥还解释了前面第 5 条陷阱，这个家族是不支持 DCS 短写的，原厂的四块 LVDS 桥屏的序列里全没有 DCS 收尾，这是桥家族的系统性设计。认出型号还开了理论上第二条路，拿主线的 tc358775 bridge 驱动配一个纯 LVDS 面板，panel 的形态就拆成 bridge + panel 两级。咱们没走，因为那要为桥重新对齐它的 LVDS lane 格式和绑定，而重放路径当时只差最后一口气。

另一个认知直接指向真凶：**init 序列发错了生命周期阶段**。最初的驱动把 init 放在 panel 的 `.enable()` 里发。而按 DRM 的桥使能顺序，`dw_mipi_dsi2` host 早在 panel `.enable()` **之前**就已经执行了 `atomic_enable`，把链路切到了视频模式。咱们此后再发 init，走的就是视频模式下的 LP（低功耗通道）注入，这颗桥对它的响应并不可靠。最阴的地方在于，注入命令偏偏**返回 0**，host 侧 FIFO 走完了，咱们以为初始化成功了，其实桥根本没锁存配置。命令模式（走背光的路）通、视频模式（走像素流的路）死，而两边一对比，病灶就锁在 init 发出去的时机上。

咱们后来把修法定稿成了面板驱动里的现行形态：

- init 序列从 `.enable` 搬到 `.prepare`，这个阶段 host 还在命令模式，写入窗口是干净的。
- 探测函数里设 `prepare_prev_first = true`，让 DRM 把 host 预启动之后再调 panel 的 prepare，保证发序列时 host 已就绪。
- exit 序列对称地从 `.disable` 搬到 `.unprepare`，init 失败时回滚上电。

咱们把 `370c0597` 烧进板里，boot logo（企鹅）正常显示了，往 fb0 灌噪点也出了花屏。视频管线算是全打通了，四版镜像的弧线到这里走完。

**不过这场仗没就此收束。**三个月后的补丁栈整合期，面板偏偏又一次从第一次 modeset（显示模式设置，把分辨率和时序写到硬件上的那一步）起零像素、只剩背光。这次咱们做了三轮更系统的排除，把面板驱动之外的一切逐项证明无辜：

| 项 | 证据 | 判决 |
|---|---|---|
| 背光 | echo 64/0 有明暗变化，PWM enabled 78% | 无辜 |
| DT 状态 | 源/dtb/runtime 三重核验全 okay | 无辜 |
| gdm/会话 | autologin 完整桌面，DBus 全活 | 无辜 |
| GPU | egl-readback：Mali-G610 GLES3.1 shader + 读回通过 | 无辜 |
| AFBC | noafbc 传导确认 + modifier=0 仍黑 | 无辜 |
| CSC | 源码核 XR24 + RGB 输出，y2r/r2y=0 | 无辜 |
| CPU 直扫 | 自写 kmsdraw（dumb buffer + SetCrtc）连发 12 帧全成功仍黑 | 无辜 |
| DSI 协议 | EOT/LPM/timing/极性/lanes 逐维对齐原厂无差异 | 无差异 |

排除到了最后，同一个生命周期的 bug 再次浮出水面，和八月那次的判定一致，两次排查隔着三个月各自抵达了同一根因。终局处理是把这个修复直接并进了面板驱动本体，让驱动生而正确，不留诊断用的过渡残留。这一轮咱们还顺手写下两个工具，它们后来都成了显示排查的常备弹药：

- 零依赖的 `kmsdraw`，用 dumb buffer（一块 CPU 能直接写的普通内存帧缓冲，不需要 GPU 参与）直扫测试图、绕开整个桌面栈。
- surfaceless EGL 读回测试（不开窗口表面、直接在 GPU 上下文里渲染再读回像素）。

咱们复盘还解释了前面悬着的“怪 mode”。原厂 blob（厂商编译好的二进制驱动）里桥自己的 HTIM/VTIM（hbp=160/hsync=20/hfp=160）跟 host mode（hbp=100/hsync=10/hfp=1580）完全不同，**桥是从自身寄存器再生 LVDS 输出时序的，host 侧的 82MHz、hfp=1580 只是传输载体**。所以疑似笔误的 1580 能用，改了反而要跟桥配置重新配平。上游现成的案例也有，RK3588 Tiger SoM 查到的组合是 DSI0 经 TC358775 到 LVDS，它在 v6.12 主线上跑得好好的（内核邮件列表 2024-11-20 的帖子），由此也知道架构组合本身是没有问题的。

这一仗提炼下来的方法论值得咱们单独说清楚，因为它适用于往后碰到的每一类“波形对了但对端没准备好”的时序问题：

1. **分层找断点，别猜。**debugfs 的 CRTC state 告诉你谁在扫描，connector 绑定告诉你路由通没通。第一步证明“像素离开了 CRTC”，然后再去查下游。
2. **命令通道和数据通道分开验证。**背光亮证明命令模式通、PHY 物理层通。屏黑证明视频模式断。两个事实一交叉，嫌疑域就窄了。
3. **“返回 0”只说明本地 FIFO 走完，不说明远端锁存。**跨芯片的写入成功与否，要看对端有没有可观察的行为变化，不能信返回值。
4. **生命周期回调是有语义窗口的。**`.prepare` 是“上电后、出画前”的命令模式窗口，`.enable` 是“host 已切视频模式之后”。把寄存器初始化放进错误的窗口，错误不会在当时报出来，只会表现为“一切正常但没有画面”。

## 主戏二：无声死机——VOP2 的 dclk 交接

第一轮板验时埋下的线头，fbcon 接管的瞬间还是偶发乱码加冻结，后来偏偏恶化成了持续问题，最难缠的形态是**无声死机**。你看屏幕定格或乱码，串口偏偏没反应、oops（内核报错）也没有。碰上了内核恐慌（panic，内核彻底崩溃停机的状态），咱们抓证据靠两样东西：ramoops（一块保留内存，崩溃前的控制台输出会写进去、重启后能取回）和硬件看门狗。这里咱们只看抓回来的东西。

完整恐慌日志里最早看到的保留异常出现在 DRM 启动阶段，同一个报错咱们连续看到了三次：

```
rockchip-drm display-subsystem: [CRTC:83:video_port2] vblank wait timed out
```

vblank wait timed out 的意思是这样。CRTC 提交了 mode 和画面，然后等扫描完一帧的中断来报到，等到超时了也没等来，那视频口多半是根本没开始扫描的。启动链上每一级都要报一次自己活着的心跳，显示链这边的心跳就是 vblank 中断：死的是 vblank 这一跳，bind 和 fbcon 接管这些前级都报过到了。硬锁检测器随后约 16 秒就报了硬锁（hard lockup），而且落在了 CPU7 上。这里有个取证细节要注意：恐慌日志里 CPU6 的栈其实只是观察者，拿它断言不了 CPU7 卡在哪。咱们再把旧观察合进来，试过的 `nomodeset`、`fbcon=disable` 都能避开冻结，故障域就收敛到 VOP/DSI 的 modeset 交接。

咱们逐项比较原厂 `rk3588s.dtsi` 和 VOP2 驱动，确认主线板级移植漏了三项 BSP 在做的硬件交接语义：

- VOP 的 ACLK 固定 **750 MHz**。
- `DCLK_VOP2_SRC`（vp2 像素时钟源）以专用 `PLL_V0PLL` 为父时钟。
- 原厂在视频口 timing/config 寄存器提交后**脉冲对应 `dclk_vpN` 的 reset**，再开启 vblank。

第三条是关键：主线基础设备树没有这六路 reset 的描述，主线 VOP2 驱动里也找不到去脉冲它们的代码。只把 `vp2 → dsi0` 的 graph 接通，不等于复现了原厂的硬件交接——时序提交了、dclk 域偏偏没有复位脉冲，视频口的扫描就可能永远启动不了，后面所有 vblank 等待也就全部超时了。缺的交接咱们自己补上：

- 板级 `&vop` 加 ACLK 750 MHz 与六路 reset（axi/ahb/dclk_vp0-3）描述。
- `&vop` 上把 `DCLK_VOP2_SRC` 重父（改挂到新的父时钟）到 V0PLL。
- VOP2 驱动按名字获取 optional 的 `dclk_vpN` reset，在 timing/interface 提交后 assert 10 µs 再 deassert，时序对齐原厂。

补完之后，板级 `&vop` 节点最终长成下面这样（开头那段英文注释完整讲了为什么 DCLK_VOP2_SRC 必须从 GPLL 改挂到 V0PLL，正文前面已经讲透，这里只摘首尾两行）：

```dts
&vop {
	/* Match the RK3588 BSP's VOP clock/reset contract.  The DCLK resets
	 * ...
	 * (lkml, 2025-03-12), whose fix is this exact assignment. */
	assigned-clocks = <&cru ACLK_VOP>, <&cru DCLK_VOP2_SRC>;
	assigned-clock-rates = <750000000>, <0>;
	assigned-clock-parents = <0>, <&cru PLL_V0PLL>;
	resets = <&cru SRST_A_VOP>,
		 <&cru SRST_H_VOP>,
		 <&cru SRST_D_VOP0>,
		 <&cru SRST_D_VOP1>,
		 <&cru SRST_D_VOP2>,
		 <&cru SRST_D_VOP3>;
	reset-names = "axi", "ahb", "dclk_vp0", "dclk_vp1",
		      "dclk_vp2", "dclk_vp3";
	status = "okay";
};
```

`assigned-clock-parents = <0>, <&cru PLL_V0PLL>` 就是"重父到 V0PLL"那句话的原文：第一个 `<0>` 说的是 ACLK_VOP 保持默认父时钟不动，第二个把 DCLK_VOP2_SRC 挂到 V0PLL。`assigned-clock-rates = <750000000>, <0>` 里 750 MHz 是 ACLK 的目标频率，`<0>` 是让 DCLK_VOP2_SRC 这个选择器不改频率。`resets` 加 `reset-names` 那六行，就是前面说的 axi/ahb/dclk_vp0 到 dclk_vp3 六路复位，VOP2 驱动按 reset-names 里的名字逐根去拿，拿到的才在提交时序后脉冲。

这里必须诚实交代状态：这项修复落地时是**候选镜像**（功能判据过了、多轮稳定性还没验证的状态），咱们当时给的通过标准如下：

- 启动阶段不再出现 VP2 vblank timeout。
- 连续多轮冷热启动和桌面运行无 hard lock。

连续冷/热启动稳定性的保留意见一直挂到结案都没销掉，显示压力测试在 11 月的收官记录里也仍标记为另开课题。修复的正确性有机制级的证明（下面有判据链），但是多轮稳定性这个维度始终没有写成已完成。每轮板验的判定命令也是定式的，稳定性判定和触摸判定咱们分开记、不混写：

```sh
dmesg | grep -iE 'vblank|dclk reset|rk3x-i2c|timeout|cpufreq|voltage|Hard LOCKUP'
cat /proc/interrupts | grep -iE 'goodix|gt911'
```

**这里还挖出一层把这场戏和下一章连起来的转折。**8 月那版的修复，咱们把 V0PLL 重父写在了 port 子节点 `&vp2` 上，而 **port 不是设备**，`of_clk_set_defaults` 只认设备节点、永远不会轮到它的头上，重父这一下就白写了，而 dtc 也不报错。这行静默死代码的后果咱们后来才算清：`DCLK_VOP2_SRC` 一直挂在默认父时钟 GPLL（通用锁相环）上，显示一次 modeset 改频就惊动了这块大家共用的 PLL，网卡跟着遭了殃。网卡那头怎么修是下一章的主线，咱们这里把显示侧的判定立住。

修复验证轮的板上判据链咱们贴在下面（DBG 前缀的行来自当时临时加的调试输出，后来已经移除了）：

```
[    1.223845] DBG32 vp2 pre-set-rate dclk=12000000 parent=dclk_vop2_src req=82000000
[    1.223995] DBG32 vp2 set_rate ret=0 dclk=82000000 parent=dclk_vop2_src
[    1.245256] DBG30 CRU V0PLL0 0x000000c6->0x00000148
[    1.630998] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
[    5.918707] rk_gmac-dwmac fe1b0000.ethernet eth0: Link is Up - 1Gbps/Full - flow control rx/tx
```

这几条咱们在日志里逐项都看到了：

- dclk 精确命中 82 MHz，GPLL 整数分频给不出这个数，反证时钟源确实换了。
- 改频瞬间重锁的是 V0PLL，GPLL 全程零变更。
- fbcon 顺利接管出画面。
- 网卡 1Gbps 起来，还挂上了 NFS 根。

修复的设计预期被逐项观察证实了，这不是碰运气的结果，同一晚烧的同栈无修复对照镜像必死。port 子节点不是设备这件事咱们算是刻进了条件反射：port 上写的 assigned-clock 等于静默死代码，设备级的属性要写到设备节点上再重查一遍。

同一区域咱们还有两处 VOP2 格式修正要交代，它们修的是内核**能力广播**的错误，硬件本身是没病的：

- 一处把 RK3588 cluster 窗口的 modifier（描述像素内存排布方式的修饰符）表从 RK3568 共享表里移出来、补上 LINEAR。检查函数本来就接受 LINEAR，但广播表没登，做 modifier 协商的客户端看不到这个能力。
- 另一处把 XRGB/XBGR2101010 从广播里下架，这些格式在 RK3588 cluster 窗口上只支持 AFBC（Arm 的帧缓冲压缩格式）组合。IN_FORMATS 是格式×modifier 的平面叉积，表达不了仅 AFBC 这个约束，mutter 按 10bpc 挑了它们之后每条 present 路径都失败，桌面永远不亮。

对软件渲染的栈（llvmpipe，纯 CPU 模拟出的 GPU 实现），咱们这套修正是刚需，有硬件 GPU 时同样防御性地成立。

## GT911：探测、中断、坐标轴，三关三个病根

触摸走的算是一条独立链路，但它出的三个问题一个比一个隐蔽，而且病根分布在三个不同的层——驱动时序、引脚配置、输入语义。咱们分开讲。

### 第一关：探测必报 -110，芯片却是好的

GT911 有个特性咱们得交代在前面：它支持两个 I2C 地址（0x5D/0x14），**复位期间 INT 线的电平决定锁存（latch）哪个地址**。主线 goodix 驱动的复位序列就是围绕这个设计的：

1. RST 拉低，保持 20 ms。
2. INT 驱到目标电平（要 0x14 就拉高）。
3. RST 放开，地址在这一瞬间锁进芯片。
4. 等 6–10 ms（手册的 T4），随后 INT 做一次低脉冲同步、切回输入。

板上的第一现象极其矛盾，咱们现场取证是这样的：

```sh
i2cdetect -y 2                          # 0x14 有响应
i2ctransfer -y 2 w2@0x14 0x81 0x40 r6   # 读回 39 31 31 ... = ASCII "911"
```

芯片在、总线通、地址是对的，咱们手动也能读出 product-id 这串芯片标识。结果驱动的探测偏偏必失败：

```
Goodix-TS 2-0014: Error reading 1 bytes from 0x8140: -110
Goodix-TS 2-0014: I2C communication failure: -110
Goodix-TS 2-0014: probe with driver Goodix-TS failed with error -110
```

-110 对应的是 ETIMEDOUT。手动读和驱动读的差别在哪？驱动读发生在**复位序列之后约 60 ms**，而且复位序列本身动过 INT 和 RST 两根线。排查当中咱们试过改 reset 极性、加盲延时，都不成——咱们后来写下“两次假设都错了”，就是这么来的。最后从原厂驱动里抠出两个这块板必需的时序步骤，落成两处驱动上的改动：

- 一处改 goodix 驱动的复位时序，地址选择窗口结束后把 RST 线**释放回输入态**。主线驱动一直把它保持为输出，这块板上被持续驱动的 RST 会让 GT911 停止应答 I2C，直到探测失败、devm 释放 GPIO 才恢复——这正好解释了“驱动放弃后手动读就通了”。
- 另一处改探测顺序，上电之后等 20 ms 再做复位/地址选择。这块板的触摸和 LCD 模块共用电源轨，早到的探测会在轨还没稳的时候就发起第一次 I2C 传输，超时在所难免。

咱们做完这两项改动之后，探测就稳定了：`ID 911, version: 1060`。

### 第二关：坐标在流，中断不响

探测通了，新问题跟着就来了：咱们把手指按上去，手工读状态寄存器 `0x814e` 是能看到 1–3 指坐标在变的，但 IRQ 76 的计数永远是 0，事件也到不了 `/dev/input/event0`。这说明芯片是在报点的，中断路径偏偏断了。

有一段失败的尝试得交代，因为它有独立的教训。当时照原厂 `gt9xx.c` 移植了轮询模式（可选的 `goodix,polling-mode` 属性，16 ms 的 hrtimer（内核的高精度定时器）配上独立工作队列，每轮的流程是读坐标并写 `0x814e` 确认），连同 I2C v5 状态机改动一起出了组合镜像 `c670a208…`。板上随机挂死、到不了 login，这两项改动咱们当场从补丁栈撤出，文件留了下来作失败证据。事后复盘还有更深一层：咱们曾拿“原厂源码里有轮询路径”当作它安全性的依据，可原厂默认配置启用的是 FT5x06，GT911 的分支根本没编进原厂镜像，**源码的存在不等于同板验证过**，这样的错以后不能再犯了。

真病根咱们用 pinctrl 寄存器取证抓到。写入 0 清掉了 `0x814e`，咱们再隔 10 ms、110 ms、1.1 s 三次复查，结果全是同一个画面：

```
GT911 status: 0x00
GPIO3_C0:      in lo IRQ
IRQ 76:        0
```

配置寄存器咱们读到 `0x804d = 0x8d`，低两位的值是 1，控制器倒是下降沿触发模式，空闲态的 INT 本该是高电平，结果它偏偏一直躺在低。再看 pinctrl 的输出：

```
pin 112 (gpio3-16): input bias pull down ...
```

PC0 被 IO 配置单元（IOC）配成了**内部下拉**。下拉偏偏把 INT 空闲态一直按在低电平，下降沿永远产生不了。修法落在设备树上：咱们新增 `gt911_int` pinctrl group，GPIO3_C0 的 pull 配置改成 `pcfg_pull_up`，节点的 `interrupts` 一并校正，`IRQ_TYPE_LEVEL_LOW` 是误导性的，改成控制器实际使用的 `IRQ_TYPE_EDGE_FALLING`。这段修改已经并进现行的板级设备树。板级 dts 里，中断引脚那组和触摸节点本体长这样：

```dts
&pinctrl {
	touchscreen {
		gt911_int: gt911-int {
			rockchip,pins = <3 RK_PC0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};

&i2c2 {
	status = "okay";
	pinctrl-names = "default";
	pinctrl-0 = <&i2c2m4_xfer>;

	touchscreen@14 {
		compatible = "goodix,gt911";
		reg = <0x14>;
		pinctrl-names = "default";
		pinctrl-0 = <&gt911_int>;
		AVDD28-supply = <&vcc3v3_lcd_n>;
		VDDIO-supply = <&vcc3v3_lcd_n>;
		interrupt-parent = <&gpio3>;
		interrupts = <RK_PC0 IRQ_TYPE_EDGE_FALLING>;
		/* Mainline Goodix uses logical GPIO values as the raw address strap. */
		irq-gpios = <&gpio3 RK_PC0 GPIO_ACTIVE_HIGH>;
		panel = <&lcd_panel>;
		reset-gpios = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;
		status = "okay";
	};
};
```

`gt911_int` 那组的 `rockchip,pins = <3 RK_PC0 RK_FUNC_GPIO &pcfg_pull_up>`，就是把 GPIO3_C0 复用成普通 GPIO、且改成内部上拉的那句话原文——第二关的病根就改在这一行。`touchscreen@14` 是 GT911 的节点本体：`reg = <0x14>` 是它的 I2C 地址，`interrupts = <RK_PC0 IRQ_TYPE_EDGE_FALLING>` 是校正后的下降沿中断，`reset-gpios = <&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>` 就是第一关复位时序要用的那根 RST 线，AVDD28/VDDIO 两路供电挂的是面板电源 `vcc3v3_lcd_n`。修好了之后看到的是 IRQ 递增、event0 出事件。咱们回头看，轮询路线本来就是绕开中断病的岔路，病根治好之后就不再需要它了。

### 第三关：轴是“反”的吗——谁负责旋转

最后一关反而是最反直觉的。触摸能用了，但点击位置和显示位置偏偏对不上，横屏下像是轴转置了。直觉的方案是加 `touchscreen-swapped-x-y` 交换 XY。**这个方案被五点板验否决了。**加了 swap 的候选镜像 `2fa62f8f…`，咱们五点实测下来：

| 物理点击位置 | 事件 X | 事件 Y | 实际映射位置 |
|---|---:|---:|---|
| 左上 | 38 | 12 | 左上 |
| 右上 | 32 | 592 | 左下 |
| 右下 | 1015 | 591 | 右下 |
| 左下 | 1011 | 14 | 右上 |
| 中心 | 558 | 317 | 中心 |

右上点到了左下、左下点到了右上——沿对角线转置，说明 swap 生效了但**不应该存在**。咱们把坐标反交换回芯片原始数据：物理左右对应的原生 X 是 0..599，物理上下对应的原生 Y 是 0..1023，轴方向本来就是对的。

咱们在配置寄存器 `0x8047` 的读数里找到了真相：

```
60 58 02 00 04 05 8d 00
```

配置版本读出来的值是 0x60，原生的 X 范围是 `0x0258 = 600`，原生的 Y 范围是 `0x0400 = 1024`。**控制器两个物理轴的数值分辨率就是 600×1024**，屏幕本身并不是竖着装的。咱们最初在设备树里写的 `touchscreen-size-x = <1024>; touchscreen-size-y = <600>` 是拿显示尺寸覆盖了控制器原生范围、却没缩放事件值，内核偏偏按 X 0..1023、Y 0..599 去解释本来是 0..599、0..1023 的数据，坐标全错了。“旋转”这件事其实没人需要做，轴方向正确、数值范围不同而已，桌面输入栈会把 X/Y 各自归一化到 1024×600 的。原厂对照下来的结果也一致：`tp-size = <911>` 分支没开交换，配置版本 0x60（96）不低于固定配置（fixed config）的判定阈值 90，配置下发这一步原厂也省了。终修落在设备树上：咱们删掉尺寸覆盖，swap 不做了、反转也不做了，让 `goodix_read_config()` 发布芯片真实的范围（X 0..599、Y 0..1023）。修复后五点物理点击的原始值应近似：

```
左上  (0, 0)      右上  (599, 0)
左下  (0, 1023)   右下  (599, 1023)
中心  (300, 512)
```

验收用 evdev（内核输入事件的原始接口）直接看原始流，咱们别只看内核报告注册成功：

```sh
timeout 15s od -An -tx1 -w24 /dev/input/event0
```

这一关还留着一个尾巴：坐标事件咱们已经板验取证，GNOME 下的触摸交互完整验收（虚拟键盘、拖动、多点）标记为待续。11 月的 eMMC 终验还发现最小根文件系统里缺 `goodix_911_cfg.bin`，触摸暂时降级用芯片 OTP（一次性可编程存储）里的出厂配置，这个咱们还没验完。

## 成功长这样

收官时补丁栈已经整编完毕了（两次失败尝试留档、不入栈），咱们烧上的 eMMC 正式镜像（MD5 `10e6e29d…`）是零 Oops。下面这段是从终验日志里截的，一个字都不是合成的：

```
[    0.442890] rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
[    0.442926] rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[    0.895099] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
[    1.055436] Goodix-TS 2-0014: ID 911, version: 1060
[    1.073104] input: Goodix Capacitive TouchScreen as /devices/platform/feaa0000.i2c/i2c-2/2-0014/input/input0
...
rk3588-topeet login:
```

VOP2 和 DSI 在 0.44 s 完成了 bind，fb0 在 0.9 s 就建立了起来、面板跟着出画，触摸在同一秒内也注册成了 input0，系统一路走到了 login，GNOME 桌面上了屏。两点边界照旧说清：本章所有板验记录都落在 v7.1 的补丁栈上，这套序列后来整体重放到了 v7.3.1 内核上。VOP2 候选镜像的稳定性保留意见与显示压力测试，到了收官时仍然挂着。下一章咱们把 Mali-G610 的 Panthor 驱动点起来，桌面已经在屏上了，该让它有 GPU 加速了。
