# LCD 显示：一块没有主线驱动的屏，和三场连环硬仗

> [上一章](02_kernel.md) 里内核已经在板上站住了，DT 移植和补丁序列的方法论咱们也都交过手。这一章就把它们全部押上那块 10.1 寸 1024×600 的屏。主线没有这块屏的 panel 驱动，桥 IC 做的是 DSI 转 LVDS，显示链上偏偏没人这么用过它，VOP2 里还埋着一个会把整块板无声冻死的时钟交接问题。TC358775 出图、VOP2 死机、GT911 触摸这三场硬仗咱们一场一场打下来，结果 GNOME 桌面才第一次亮在玻璃上。

## 显示链路全图：像素从内存到玻璃要过四道门

背景咱们这样补。Linux 内核的显示框架叫 DRM（Direct Rendering Manager），咱们这一章一直跟它打交道。屏幕显示什么、什么分辨率、什么时候刷新这些事归 KMS（Kernel Mode Setting）管，咱们全章都泡在它的抽象里。按 KMS 的抽象，咱们把显示看成一条链，每一环咱们各配一个驱动、各管一段：

- **CRTC**：扫描引擎，按行从帧缓冲读像素、按 mode 里的节拍发出去。
- **encoder**：把像素流编码成具体接口的信号，这里是 MIPI DSI。
- **connector**：物理接口在软件里的代表。
- **panel/bridge**：屏幕侧的驱动。panel 驱动管上电、初始化序列、背光。如果中间有转接芯片，还可以再挂一个 bridge 驱动去管它。

对应到咱们这块板，链路咱们画成下面这样：

```
帧缓冲 fb0
  → VOP2 (fdd90000) 视频端口 vp2          CRTC：RK3588 的显示控制器，共 4 个视频端口
  → DSI0 (fde20000, mipi-dsi2 控制器)      encoder：MIPI DSI 发送端
  → mipidcphy0 (Samsung DCPHY)             物理层：4 条 data lane
  → TC358775 桥 IC（DSI 转 LVDS）           bridge：屏侧转接芯片
  → 10.1" 1024×600 LVDS 面板

GT911 触摸 → i2c2 @ 0x14（独立链路，INT=GPIO3_C0，RST=GPIO3_C1，与显示只共用电源轨）
```

为什么好端端的 LVDS 屏要走 DSI？迅为的手册写得很直白。RK3588 本身其实没有 LVDS 显示输出，所以迅为的 LVDS 屏都是 MIPI DSI 经转接板转出来的，转接芯片就是前面提到的桥 IC，出处咱们记在《iTOP-3588 开发板多屏显示手册 v1.2》。于是这块屏在 DT 里的身份是 DSI 面板，桥的行为就藏在屏的初始化序列里，后面咱们会在这上面反复吃亏。

还有一个 DSI 的基础概念得立住。**咱们跟同一条 DSI 链的两种工作方式都要打交道**。命令模式你看就像 I2C，咱们一条一条发寄存器写、拿它做初始化。视频模式反而更像 HDMI，像素流倒是连绵不断，正常显示走的就是它。那主机在两种模式之间切换的时机，正是本章第一场硬仗的病灶。

最后交代一个容易被带偏的事实。原厂 SDK 出厂默认启用的屏其实是 MIPI1 那一路，咱们看到的是 800×1280（HX8394）。触摸那一路其实是 FT5x06。而咱们要的 1024×600 + GT911 分支，原厂只留了 `#define LCD_TYPE_MIPI1` 一个入口，在原厂的 `topeet-screen-lcds.dts` 里还把它编译关闭了。你看，原厂的正常镜像压根没跑过这个分支，咱们能参照的只有原厂源码、没有运行记录可对，这个差别咱们后面在触摸一节还会回来算。

## 面板移植：主线没有驱动，自己写一个

原厂 SDK（kernel 5.10 BSP）驱动这块屏用的是私有的 `simple-panel-dsi` 绑定，DT 里倒是塞了一段 `panel-init-sequence` 字节块，驱动拿过来做的就是把整段序列原样重放。主线其实没有这个绑定，显示链上也偏偏没人用过这颗桥。摆在咱们面前的就两条路，要么给桥单写一个驱动，要么写一个通用 panel 驱动、原样重放原厂的序列。咱们选了后者，因为桥的寄存器序列是从原厂 DT 逐字节搬来的厂商私有数据，重放的改动面最小，桥寄存器的完整语义咱们并不需要全懂。于是有了 [0001（panel 驱动）](../../../boards/rk3588-topeet/patches/linux/0001-drm-panel-topeet-dsi-driver.patch)和 [0002（板级 DT）](../../../boards/rk3588-topeet/patches/linux/0002-arm64-dts-rk3588-topeet-panel.patch)。

驱动骨架是咱们照主线 `panel-himax-hx8394.c` 摹的。注册咱们交给 `module_mipi_dsi_driver`，probe 里咱们再跑 `devm_drm_panel_alloc`，然后咱们照 `drm_panel_funcs` 实现五个回调，列成四条（`disable` 和 `unprepare` 咱们合在一条里说）：

- `prepare` 管上电、复位。
- `enable` 负责点亮点后的延时。
- `disable`/`unprepare` 反向关掉。
- `get_modes` 把 DT 里 `display-timings` 描述的 mode 报给 DRM core。

初始化序列咱们从 DT 的 `panel-init-sequence` 读进来，格式是原厂定的记录流：

```
<u8 type><u8 delay_ms><u8 len><len 个 payload 字节>
  type 0x29 = GENERIC_LONG_WRITE   写桥的厂商寄存器
  type 0x05/0x15/0x39 = DCS 短写/带参短写/长写（这块屏的序列里几乎不出现）
```

重放的核心很直白。咱们遍历记录、按 type 分派到 `mipi_dsi_generic_write_multi` 或 `mipi_dsi_dcs_write_buffer_multi`，每条后面咱们让它睡一个 delay，出错咱们也不马上返回，错误倒是都聚合在 multi-context 里、最后统一报出。mode 侧咱们直接在 probe 里写死 4 lane、RGB888、video burst、LPM 发命令这一套，跟原厂是完全一致的。

DT 侧（0002）咱们接着把整条管线挂起来：

- `backlight` 用 pwm-backlight 挂在 pwm1 上。
- `vcc3v3_lcd_n` 是面板 3.3V 电源、GPIO1_B3 使能。
- `&vop`、`&vop_mmu`、`&mipidcphy0`、`&dsi0` 逐个 okay。
- 最后用主线的 OF-graph 把 `vp2 → dsi0 → panel` 三段 endpoint 连起来。

面板节点咱们来看节选，init 序列咱们只示前两条和末条：

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

咱们再交代两个硬件细节。这块面板**没有独立的 reset 引脚**，复位靠的就是断电重上电，所以驱动里 reset GPIO 是可选的，在这块板上咱们给它留 NULL。触摸的 reset 在 GPIO3_C1，那咱们就别把它和面板弄混。config 侧五个符号咱们数过一个都不能少：

```
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y       # dsi0 = mipi-dsi2 控制器（NOT _DSI）
CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y  # mipidcphy0 的 PHY 驱动
CONFIG_DRM_MIPI_DSI=y
CONFIG_DRM_PANEL_TOPEET_DSI=y
CONFIG_BACKLIGHT_PWM=y
```

移植过程中咱们攒下了一批致命的陷阱（gotcha），错任何一个 panel 咱们见到的都是静默不亮，咱们把它们列在这里（完整版见 [notes/44](../../notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)）：

1. **DSI host 的 config 符号是 `ROCKCHIP_DW_MIPI_DSI2`，不是 `_DSI`**。RK3588 的 dsi0 是 `rockchip,rk3588-mipi-dsi2` 控制器，由 `dw-mipi-dsi2-rockchip.c` 绑定，编错符号直接不绑。
2. **PHY 驱动是 `PHY_ROCKCHIP_SAMSUNG_DCPHY`**，DT 标签主线拼写是 `mipidcphy0`（原厂写 `mipi_dcphy0`，BSP 专属）。
3. **序列里的 `0x29` 是 generic long write，不是 DCS（MIPI 联盟定义的屏端命令集）**。`0x39` 才是 DCS 长写。1024×600 整段 `29 ...` 全是给桥的厂商寄存器写。
4. **EOT flag 主线改名了**：原厂的 `MIPI_DSI_MODE_EOT_PACKET` 在主线叫 `MIPI_DSI_MODE_NO_EOT_PACKET`，同一个 bit、名字取反。OF-graph 是主线唯一的路由表达，原厂的 `&route_dsi0`、`&dsi0_in_vp2{status}` 都是 BSP 私有节点，主线没有。这两处都得按主线的写法重新核对，名字不可信，要核语义。
5. **init 序列不补 DCS sleep-out/display-on 收尾**。原厂同文件里 MIPI0/MIPI1 屏的序列都以 `05 .. 11`/`05 .. 29` 收尾，唯独这块不是——当时不敢确定是不是漏了，后来证实桥家族根本不支持 DCS 短写，这段序列靠视频流自启动，是设计使然。
6. **`hfront-porch = <1580>` 照原厂原值保留**。这个值大得离谱（多半是 158 的笔误），但 bridge 的初始化序列就是按这个 mode 配的，改 mode 要跟桥配置匹配。为什么这样也能工作，主戏一的复盘里有答案。

## 第一轮板验：三个 config 拦路虎，四版镜像

代码咱们落好之后烧进板里。这一轮全是 kernel.config 的问题，不过的话每版镜像只修得好一个，咱们烧了四版才换来第一缕画面（完整表见 [notes/45](../../notes/45-2026-07-31-rk3588-lcd-bringup-blockers.md)）：

| 镜像 MD5 | 改动 | 板上结果 |
|---|---|---|
| `8520c77f` | +直接 bootcmd（LCD 已在镜像内） | panel 永久 deferred：DCPHY 没编 |
| `69d5d278` | +`PHY_ROCKCHIP_SAMSUNG_DCPHY=y` | 仍 deferred：`BACKLIGHT_PWM=m` |
| `b8d0abf3` | +`BACKLIGHT_PWM=y` | DRM 全 bind、背光亮，**屏无画面** |
| `370c0597` | 面板驱动 init→prepare（下一节） | **boot logo 出图 + fb0 灌噪点花屏** |

**咱们碰到的第一个拦路虎是 PHY 驱动没编。**症状咱们在 dmesg 里翻到的就这一行，panel 链倒是永久 deferred，`/dev/dri` 咱们也看不到：

```
platform fde20000.dsi: deferred probe pending: dw-mipi-dsi2: failed to get mipi phy
```

此前规划时咱们预设过“DSI2 host 会自动 select PHY 符号”，实测 host select 的只是 `GENERIC_PHY_MIPI_DPHY` 框架，具体到 `mipidcphy0` 这颗 PHY 的驱动，它其实并不负责。PHY 偏偏没 probe，那 dsi2 也就拿不到 PHY 了，结果 panel 只能跟着干等。咱们 `grep PHY_ROCKCHIP_SAMSUNG_DCPHY .config` 一看，`is not set`，咱们给它加上就好。

**咱们碰到的第二个拦路虎是 `BACKLIGHT_PWM=m`。**PHY 修好之后 dmesg 变了脸，咱们接着看：

```
mipi-dsi fde20000.dsi.0: deferred probe pending: (reason unknown)
```

`(reason unknown)` 反而比具体报错还磨人。咱们这时看两个旁证，`/sys/class/backlight/` 是空的，dmesg 里咱们一行 pwm/backlight 都没看到。对上号了，`CONFIG_BACKLIGHT_PWM=m`。backlight 驱动偏偏是个模块，而这个阶段的 rootfs 没有 modprobe，backlight 设备也就不会出现了，panel 的下场就是卡在 `drm_panel_of_backlight()` 上一直等。config 里只声明 `BACKLIGHT_CLASS_DEVICE=y`（框架）是不够的，具体驱动咱们得单独 `=y`。咱们还把显示相关符号全扫了一遍 `=m`，扫出来 `=m` 的只有 backlight。

这一轮咱们提炼出的经验就一条：**“符号会自动 select”的话咱们别信，显示链路上每个具体驱动的符号咱们都逐个 `grep .config` 确认 `=y`**。deferred probe 的排查顺序咱们也定型了。咱们第一步跑 `dmesg | grep deferred`，看谁在等、等什么，然后咱们查对应的 `/sys/class/...` 是不是空的，最后咱们才去查驱动符号。

咱们把 `b8d0abf3` 烧进板里，然后咱们看到 DRM 管线第一次全通：

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

结果屏上连雪花都没有。像素你看明明在内存里，VOP2 也该是在扫描的，可它们偏偏就是没变成光。咱们第一场硬仗的开局就在这里。

还得记下当时发现的一个怪象，因为到了第二场硬仗咱们还要回到它身上。咱们赶上 DRM 接管 fbcon（内核的文字控制台）那一瞬间，**偶发**串口乱码加整板冻结偏偏都冒出来过，冷启动、热启动咱们看到表现不同、非必现。咱们试过 `nomodeset` 或 `fbcon=disable`，结果都能避开。当时咱们只当是 bringup 噪声、随手记了一行。

## 主戏一：背光亮着，屏是黑的——TC358775 的生命周期

咱们面对的局面是背光亮、屏黑、dmesg 无报错，这是显示调试里最不舒服的一类，链路上每一层偏偏都说自己没事。

**咱们第一步用 debugfs 找断点。**咱们跑一下 `cat /sys/kernel/debug/dri/0/state`：

```
crtc[83]: video_port2
active=1
mode: "1024x600": 47 82000 1024 2604 2614 2714 600 610 620 645 0x48 0xa
connector[85]: DSI-1
	crtc=video_port2
```

咱们从 state 里能读到三个信息。vp2 这一行咱们看到 `active=1`，结果 VOP2 确实在扫描 fb0。mode 咱们看到的是 1024×600@47Hz、82MHz 像素钟。参数倒是正确应用了，hsync_start=2604 偏偏就是 hfront-porch=1580，咱们对过。connector 咱们看到绑在 vp2 上，那路由是没错的。所以断点在 VOP2 之后，在 DSI 视频编码、PHY 高速模式、桥这三段里偏偏有东西断了。state 的输出还排除了“vp2 不通、该换 vp3”的怀疑，gameforce-ace（主线另一块 RK3588 板）咱们记得用的是 vp3，但 vp2 实测是通的。

**咱们第二步排除下层驱动。**咱们把主线的 DSI2 core、rockchip 平台适配层（glue）、samsung-dcphy 三份代码，咱们跟原厂 BSP 逐行对照。视频模式切换序列（`DSI2_DSI_VID_TX_CFG` + `MODE_CTRL=VIDEO_MODE` + poll 状态）、IPI 配置（HSA/HBP/HACT/HLINE/VSA/VBP/VACT/VFP 全套 timing）、lane rate 计算（含 burst 的 10/9 开销）、PHY power_on 序列、GRF 写，咱们一路对下来，寄存器级咱们对出来全部等价，主线其实没漏写东西。这一步的代价咱们心里有数，可它把下层驱动有 bug 这个假设给彻底关掉了，也把原厂同配置能点亮这个事实变成了更强的约束，配置和驱动都是对的，那问题必然在咱们自己这层之上的某个行为差异上。咱们剩下两个嫌疑，要么是 VOP2 到 DSI2 的像素喂入没接上，要么是桥没锁住视频同步。

**咱们第三步写自包含诊断文档去会诊。**咱们把症状、证据、已排除项、配置整编成一份不依赖上下文的文档，写好之后咱们拿去会诊，结果换回来两个决定性的认知。整份文档咱们收在 [dsi2-video-blank-diagnosis.md](../../logs/rk3588/dsi2-video-blank-diagnosis.md) 里。咱们换回来的第一个认知，是**桥其实是 Toshiba TC358775**。init 序列的 payload 是 `[addr_lo, addr_hi, data_le32]`，小端 16 位寄存器地址加 32 位数据。咱们拿这个格式解码序列开头的几条：

```
04 01 01 00 00 00  →  addr 0x0104 (PPI_STARTPPI) = 1
04 02 01 00 00 00  →  addr 0x0204 (DSI_STARTDSI) = 1
9C 04 31 04 00 00  →  addr 0x049C (LVCFG) = 0x431   （LVDLINK=0，single-link LVDS）
```

这些寄存器地址跟主线现成的 `drivers/gpu/drm/bridge/tc358775.c` 的寄存器表逐字吻合，桥的身份就这么定了。认出桥还解释了前面第 5 条陷阱，这个家族是不支持 DCS 短写的，原厂的四块 LVDS 桥屏的序列里全没有 DCS 收尾，这是桥家族的系统性设计。认出型号还开了理论上第二条路，拿主线的 tc358775 bridge 驱动咱们配一个纯 LVDS 面板，panel 的形态就拆成 bridge + panel 两级。咱们没走，因为那要咱们为桥重新对齐 LVDS lane 格式和绑定，而重放路径当时只差最后一口气。

咱们换回来的另一个认知直接指向真凶，**init 序列发错了生命周期阶段**。咱们最初的驱动把 init 放在 panel 的 `.enable()` 里发。而按 DRM 的桥使能顺序，`dw_mipi_dsi2` host 是早在 panel `.enable()` **之前**就已经执行了 `atomic_enable` 的，把链路切到了视频模式。此后咱们再发 init，走的就是视频模式下的 LP 注入，这颗桥对它的响应并不可靠。最阴的地方在于，注入命令偏偏**返回 0**，host 侧 FIFO 走完了，咱们以为初始化成功了，其实桥根本没锁存配置。命令模式（走背光的路）通、视频模式（走像素流的路）死，两边咱们一对比，病灶就锁在 init 发出去的时机上。

修法咱们后来定稿成了补丁 0001 的现行形态（当年以独立补丁 [0034](../../../boards/rk3588-topeet/patches/linux/0034-drm-panel-topeet-dsi-send-init-in-prepare-and-read-back.patch) 落地）：

- init 序列从 `.enable` 搬到 `.prepare`，这个阶段 host 还在命令模式，写入窗口是干净的。
- probe 里设 `prepare_prev_first = true`，让 DRM 把 host 预启动之后再调 panel 的 prepare，保证发序列时 host 已就绪。
- exit 序列对称地从 `.disable` 搬到 `.unprepare`，init 失败时回滚上电。

咱们把 `370c0597` 烧进板里，boot logo（企鹅）咱们看到正常显示，往 fb0 灌噪点结果出了花屏。视频管线咱们算是全打通了，四版镜像的弧线到这里走完（[notes/46](../../notes/46-2026-07-31-rk3588-lcd-dsi2-video-blocker-handoff.md)、[notes/47](../../notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md)）。

**不过的话，这场仗咱们没让它就此收束。**三个月后的补丁栈整合期（[notes/121](../../notes/121-2026-11-01-rk3588-display-bringup-tc358775-lifecycle.md)），面板偏偏又一次从第一次 modeset 起零像素、只剩背光。这次咱们做了三轮更系统的排除，把面板驱动之外的一切逐项证明无辜：

| 项 | 证据 | 判决 |
|---|---|---|
| 背光 | echo 64/0 有明暗变化，PWM enabled 78% | 无辜 |
| DT 状态 | 源/dtb/runtime 三重核验全 okay | 无辜 |
| gdm/会话 | autologin 完整桌面，DBus 全活 | 无辜 |
| GPU | egl-readback：Mali-G610 GLES3.1 shader + 读回 PASS | 无辜 |
| AFBC | noafbc 传导确认 + modifier=0 仍黑 | 无辜 |
| CSC | 源码核 XR24 + RGB 输出，y2r/r2y=0 | 无辜 |
| CPU 直扫 | 自写 kmsdraw（dumb buffer + SetCrtc）连发 12 帧全成功仍黑 | 无辜 |
| DSI 协议 | EOT/LPM/timing/极性/lanes 逐维对齐原厂无差异 | 无差异 |

咱们排除到最后，同一个生命周期 bug 偏偏再次浮出水面，和八月那次的判定一致，两次排查隔着三个月各自抵达了同一根因。终局处理咱们定的是把 0034 **折叠进 0001**，让面板驱动生而正确、不留诊断残留。这轮咱们还顺手写下两个工具，它们后来都成了咱们显示排查的常备弹药：

- 零依赖的 `kmsdraw`，dumb buffer 直扫测试图、绕开整个桌面栈。
- surfaceless EGL 读回测试。

复盘还解释了前面悬着的“怪 mode”。原厂 blob 里桥自己的 HTIM/VTIM（hbp=160/hsync=20/hfp=160）跟 host mode（hbp=100/hsync=10/hfp=1580）完全不同，**桥是从自身寄存器再生 LVDS 输出时序的，host 侧的 82MHz、hfp=1580 只是传输载体**。所以疑似笔误的 1580 能用，改了反而要跟桥配置重新配平。上游现成的案例也有，RK3588 Tiger SoM 咱们查到的组合是 DSI0 经 TC358775 到 LVDS，它在 v6.12 主线上跑得好好的（lkml 2024-11-20），咱们由此也知道架构组合本身没问题。

这一仗咱们提炼下来的方法论，值得咱们单独说清楚，因为它适用于咱们往后碰到的每一类“波形对了但对端没准备好”的时序问题：

1. **分层找断点，别猜。**debugfs 的 CRTC state 告诉咱们谁在扫描，connector 绑定告诉咱们路由通没通。第一步证明“像素离开了 CRTC”，然后再去查下游。
2. **命令通道和数据通道分开验证。**背光亮证明命令模式通、PHY 物理层通。屏黑证明视频模式断。两个事实一交叉，嫌疑域就窄了。
3. **"返回 0"只说明本地 FIFO 走完，不说明远端锁存。**跨芯片的写入成功与否，要看对端有没有可观察的行为变化，不能信返回值。
4. **生命周期回调是有语义窗口的。**`.prepare` 是"上电后、出画前"的命令模式窗口，`.enable` 是"host 已切视频模式之后"。把寄存器初始化放进错误的窗口，错误不会在当时报出来，只会表现为"一切正常但没有画面"。

## 主戏二：无声死机——VOP2 的 dclk 交接

第一轮板验时咱们埋下的线头，fbcon 接管瞬间咱们看到偶发乱码加冻结，后来偏偏恶化成了持续问题，最难缠的形态是**无声死机**。你看屏幕定格或乱码，串口偏偏没反应、oops（内核报错）也没有。碰上 panic 咱们的抓法是 ramoops 加硬件看门狗，方法论咱们在内核那章已经交过，这里咱们只看抓回来的东西。

完整 panic 里咱们最早看到的保留异常出现在 DRM 启动阶段，同一个报错咱们数过连续出现三次：

```
rockchip-drm display-subsystem: [CRTC:83:video_port2] vblank wait timed out
```

vblank wait timed out 的意思是这样。CRTC 提交了 mode 和画面，然后咱们等“扫描完一帧”的中断来报到，咱们等到超时也没等来，那视频口咱们看多半根本没开始扫描。这就是 [U-Boot 章](01_uboot.md)心跳表的变体：启动链上一级一条心跳，显示链这边的心跳就是 vblank 中断，死的是 vblank 这一跳，bind 和 fbcon 接管这些前级都报过到了。硬锁检测器随后约 16 秒就报了硬锁（hard lockup），咱们看到落在 CPU7 上。咱们注意一个取证细节，panic 里 CPU6 的栈其实只是观察者，咱们不能拿它断言 CPU7 卡在哪，完整 panic 咱们收在 [notes/54](../../notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)。咱们再把旧观察合进来，`nomodeset`、`fbcon=disable` 咱们试过都能避开冻结，故障域就收敛到 VOP/DSI 的 modeset 交接。

咱们逐项比较原厂 `rk3588s.dtsi` 和 VOP2 驱动，确认主线板级移植漏了三项 BSP 在做的硬件交接语义：

- VOP 的 ACLK 固定 **750 MHz**。
- `DCLK_VOP2_SRC`（vp2 像素时钟源）以专用 `PLL_V0PLL` 为父时钟。
- 原厂在视频口 timing/config 寄存器提交后**脉冲对应 `dclk_vpN` 的 reset**，再开启 vblank。

第三条是关键：主线基础 DTS 没有这六路 reset 的描述，主线 VOP2 驱动里也找不到去脉冲它们的代码。只把 `vp2 → dsi0` 的 graph 接通，不等于复现了原厂的硬件交接，时序提交了、dclk 域偏偏没有复位脉冲，视频口咱们看可能永远不开始扫描，后面所有 vblank 等待也就全部超时了。缺的交接咱们用 [0009](../../../boards/rk3588-topeet/patches/linux/0009-drm-rockchip-align-RK3588-VOP2-dclk-handoff-with-BSP.patch) 补上：

- 板级 `&vop` 加 ACLK 750 MHz 与六路 reset（axi/ahb/dclk_vp0-3）描述。
- `&vop` 上把 `DCLK_VOP2_SRC` 重父（改挂到新的父时钟）到 V0PLL。
- VOP2 驱动按名字获取 optional 的 `dclk_vpN` reset，在 timing/interface 提交后 assert 10 µs 再 deassert，时序对齐原厂。

这里必须按仓库口径诚实交代状态：0009 落地时是**候选镜像**，通过标准写在补丁交接里、咱们摘录如下：

- 启动阶段不再出现 VP2 vblank timeout。
- 连续多轮冷热启动和桌面运行无 hard lock。

连续冷/热启动稳定性的保留意见一直挂到结案文档（见 [sdk-diff](../../sdk-diff-rk3588.md)），显示压力测试在 11 月的收官记录里也仍标记为另开课题。补丁的正确性是机制级证明的（下面有判据链），但多轮稳定性这个维度仓库的结案文档里始终没有写成已完成。每轮板验的判定命令也是定式的，稳定性判定和触摸判定咱们分开记、不混写：

```sh
dmesg | grep -iE 'vblank|dclk reset|rk3x-i2c|timeout|cpufreq|voltage|Hard LOCKUP'
cat /proc/interrupts | grep -iE 'goodix|gt911'
```

**咱们还挖出一层把这场戏和下一章连起来的转折。**8 月版 0009 咱们把 V0PLL 重父写在了 port 子节点 `&vp2` 上，而 **port 不是设备**，`of_clk_set_defaults` 只认设备节点、永远不会轮到它的头上，重父这一下就白写了，dtc 咱们看也不报错。这行静默死代码的后果咱们后来才算清：`DCLK_VOP2_SRC` 一直挂在默认父 GPLL 上，显示一次 modeset 改频就惊动了这块大家共用的 PLL，网卡跟着遭了殃。显示 modeset 楔死网卡的完整战役在[网络章](06_network.md)，重锁机理、时钟父子和修复的现行形态都记在那里，咱们这里只立住显示侧的判定。

修复轮 R31 的板上判据链咱们贴在下面（轮次编号的解释在网络章，这里的 R31 指修复验证轮。log 咱们截自 [vop/2.txt](../../logs/rk3588/vop/2.txt)，DBG 前缀的行来自当时的临时仪器补丁、后已退役）：

```
[    1.223845] DBG32 vp2 pre-set-rate dclk=12000000 parent=dclk_vop2_src req=82000000
[    1.223995] DBG32 vp2 set_rate ret=0 dclk=82000000 parent=dclk_vop2_src
[    1.245256] DBG30 CRU V0PLL0 0x000000c6->0x00000148
[    1.630998] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
[    5.918707] rk_gmac-dwmac fe1b0000.ethernet eth0: Link is Up - 1Gbps/Full - flow control rx/tx
```

这几条咱们在 log 里逐项看到了：

- dclk 精确命中 82 MHz，GPLL 整数分频给不出这个数，反证时钟源确实换了。
- 改频瞬间重锁的是 V0PLL，GPLL 全程零变更。
- fbcon 顺利接管出画面。
- 网卡 1Gbps 起来，还挂上了 NFS 根。

修复的设计预期被逐项观察证实了，这不是咱们撞大运，同栈无修复的对照轮 R30 同晚必死。port 子节点不是设备这件事咱们算是刻进了条件反射，port 上写的 assigned-clock 等于静默死代码，设备级的属性咱们要重查设备节点。

同一区域咱们还有两张 VOP2 格式补丁要交代，它们修的是内核**能力广播**的错误，硬件本身是没病的：

- [0020](../../../boards/rk3588-topeet/patches/linux/0020-drm-rockchip-vop2-advertise-linear-modifier-on-rk3588-cluster-windows.patch) 把 RK3588 cluster 窗口的 modifier（描述像素内存排布方式的修饰符）表从 RK3568 共享表里拆出来、补上 LINEAR。检查函数本来就接受 LINEAR，但广播表没登，做 modifier 协商的客户端看不到这个能力。
- [0021](../../../boards/rk3588-topeet/patches/linux/0021-drm-rockchip-vop2-drop-afbc-only-10bpc-formats-from-rk3588-cluster-windows.patch) 把 XRGB/XBGR2101010 从广播里下架，这些格式在 RK3588 cluster 窗口上只支持 AFBC（Arm 的帧缓冲压缩格式）组合。IN_FORMATS 是格式×modifier 的平面叉积，表达不了仅 AFBC 这个约束，mutter 按 10bpc 挑了它们之后每条 present 路径都失败，桌面永远不亮。

对软件渲染（llvmpipe）的栈，咱们这套修正是刚需，有硬件 GPU 时同样防御性地成立。

## GT911：probe、中断、坐标轴，三关三个病根

触摸走的算是一条独立链路，但它出的三个问题一个比一个隐蔽，而且病根分布在三个不同的层——驱动时序、引脚配置、输入语义。咱们分开讲。

### 第一关：probe 必 -110，芯片却是好的

GT911 有个特性咱们得交代在前面：它支持两个 I2C 地址（0x5D/0x14），**复位期间 INT 线的电平决定锁存（latch）哪个地址**。主线 goodix 驱动的复位序列就是围绕这个设计的：

1. RST 拉低，保持 20 ms。
2. INT 驱到目标电平（要 0x14 就拉高）。
3. RST 放开，地址在这一瞬间锁进芯片。
4. 等 6–10 ms（手册的 T4），随后 INT 做一次低脉冲同步、切回输入。

板上的第一现象极其矛盾，取证咱们单独立了一份文档：

- [gt911-touch-i2c-110-diagnosis.md](../../logs/rk3588/gt911-touch-i2c-110-diagnosis.md)

```sh
i2cdetect -y 2                          # 0x14 有响应
i2ctransfer -y 2 w2@0x14 0x81 0x40 r6   # 读回 39 31 31 ... = ASCII "911"
```

芯片在、总线通、地址对，手动咱们也能读出 product-id 这串芯片标识。结果驱动 probe 偏偏必失败：

```
Goodix-TS 2-0014: Error reading 1 bytes from 0x8140: -110
Goodix-TS 2-0014: I2C communication failure: -110
Goodix-TS 2-0014: probe with driver Goodix-TS failed with error -110
```

-110 对应的是 ETIMEDOUT。手动读和驱动读的差别在哪？驱动读发生在**复位序列之后约 60 ms**，而且复位序列本身动过 INT 和 RST 两根线。排查当中咱们试过改 reset 极性、加盲延时，结果都不成，咱们后来在诊断文档里写下“两次假设都错了”，就是这么来的。最后咱们从原厂驱动里抠出两个这块板必需的时序步骤、落成两张补丁：

- [0005](../../../boards/rk3588-topeet/patches/linux/0005-input-goodix-release-reset-line-after-address-select.patch)：地址选择窗口结束后把 RST 线**释放回 input**。主线驱动一直把它保持为输出，这块板上被持续驱动的 RST 会让 GT911 停止应答 I2C，直到 probe 失败、devm 释放 GPIO 才恢复——这正好解释了"驱动放弃后手动读就通了"。
- [0006](../../../boards/rk3588-topeet/patches/linux/0006-input-goodix-sequence-power-before-reset.patch)：probe 里上电之后等 20 ms 再做复位/地址选择。这块板的触摸和 LCD 模块共用电源轨，早到的 probe 会在轨还没稳的时候就发起第一次 I2C 传输，超时在所难免。

两张补丁之后咱们看到 probe 稳定了：`ID 911, version: 1060`。

### 第二关：坐标在流，中断不响

probe 通了，新问题跟着就来了：手指按上去，手工读状态寄存器 `0x814e` 咱们能看到 1–3 指坐标在变，但 IRQ 76 的计数永远是 0，`/dev/input/event0` 咱们看不到事件。这说明芯片是在报点的，中断路径偏偏断了。

有一段失败的尝试咱们得交代，因为它有独立的教训。当时照原厂 `gt9xx.c` 咱们移植了轮询模式（[0008](../../../boards/rk3588-topeet/patches/linux/0008-input-goodix-add-TOPEET-vendor-polling-mode.patch)：opt-in 的 `goodix,polling-mode`，16 ms hrtimer 咱们配上独立工作队列，每轮咱们读坐标并写 `0x814e` 确认），连同 I2C v5 状态机补丁一起出了组合镜像 `c670a208…`。板上随机挂死、到不了 login，两案咱们当场从 series 撤出，补丁文件咱们留作失败证据。事后复盘还有更深一层：咱们曾拿“原厂源码里有轮询路径”当作它安全性的依据，可原厂默认配置启用的是 FT5x06，GT911 分支倒是根本没编进原厂镜像，**源码存在是不等于同板验证过的**，这个口径咱们以后不能再犯。

真病根咱们用 pinctrl 寄存器取证抓到（[notes/52](../../notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)）。咱们写入 0 清掉 `0x814e`，再隔 10 ms、110 ms、1.1 s 咱们三次复查，结果全是同一个画面：

```
GT911 status: 0x00
GPIO3_C0:      in lo IRQ
IRQ 76:        0
```

配置寄存器咱们看到 `0x804d = 0x8d`，低两位的值是 1，控制器倒是下降沿触发模式，空闲 INT 咱们想本该是高电平，结果它偏偏一直躺在低。咱们再看 pinctrl：

```
pin 112 (gpio3-16): input bias pull down ...
```

PC0 被 IOC 配成了**内部下拉**。下拉偏偏把 INT 空闲态一直按在低电平，下降沿永远产生不了。修法咱们落在 DT 上：新增 `gt911_int` pinctrl group，GPIO3_C0 咱们配 `pcfg_pull_up`，节点的 `interrupts` 咱们也一并校正，`IRQ_TYPE_LEVEL_LOW` 是误导性的，咱们把它改成控制器实际使用的 `IRQ_TYPE_EDGE_FALLING`，这段已折进 0002 的现行 DT。修好之后咱们看到 IRQ 递增、event0 出事件。咱们回头看，轮询路线本来就是绕开中断病的岔路，病根治好之后咱们就不再需要它。

### 第三关：轴是"反"的吗——谁负责旋转

最后一关反而是最反直觉的。触摸能用了，但点击位置和显示位置偏偏对不上，横屏下像是轴转置了。直觉方案咱们想到的是加 `touchscreen-swapped-x-y` 交换 XY。**这个方案被五点板验否决了**（[notes/55](../../notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)）。加了 swap 的候选 `2fa62f8f…`，五点咱们实测下来：

| 物理点击位置 | 事件 X | 事件 Y | 实际映射位置 |
|---|---:|---:|---|
| 左上 | 38 | 12 | 左上 |
| 右上 | 32 | 592 | 左下 |
| 右下 | 1015 | 591 | 右下 |
| 左下 | 1011 | 14 | 右上 |
| 中心 | 558 | 317 | 中心 |

右上点到了左下、左下点到了右上——沿对角线转置，说明 swap 生效了但**不应该存在**。咱们把坐标反交换回芯片原始数据：物理左右对应的原生 X 是 0..599，物理上下对应的原生 Y 是 0..1023，轴方向本来就是对的。

真相咱们在配置寄存器 `0x8047` 的读数里找到了：

```
60 58 02 00 04 05 8d 00
```

配置版本咱们读出 0x60，原生的 X 范围是 `0x0258 = 600`，原生的 Y 范围是 `0x0400 = 1024`。**控制器两个物理轴的数值分辨率就是 600×1024**，屏幕本身咱们看并不是竖着装的。咱们最初在 DT 里写的 `touchscreen-size-x = <1024>; touchscreen-size-y = <600>` 是拿显示尺寸覆盖了控制器原生范围、却没缩放事件值，内核偏偏按 X 0..1023、Y 0..599 去解释本来是 0..599、0..1023 的数据，坐标咱们看到全错了。“旋转”这件事其实没人需要做，轴方向正确、数值范围不同而已，桌面输入栈是会把 X/Y 各自归一化到 1024×600 的。原厂对照下来的结果也一致：`tp-size = <911>` 分支没开交换，配置版本 0x60（96）不低于固定配置（fixed config）的判定阈值 90，配置下发这一步原厂也省了。终修是 [0010](../../../boards/rk3588-topeet/patches/linux/0010-arm64-dts-rk3588-topeet-fix-GT911-axis-mapping.patch)：咱们删掉尺寸覆盖，swap 咱们不做、反转也不做，咱们让 `goodix_read_config()` 发布芯片真实范围（X 0..599、Y 0..1023）。修复后五点物理点击的原始值应近似：

```
左上  (0, 0)      右上  (599, 0)
左下  (0, 1023)   右下  (599, 1023)
中心  (300, 512)
```

验收咱们用 evdev 直接看原始流、别只看内核报告注册成功：

```sh
timeout 15s od -An -tx1 -w24 /dev/input/event0
```

这一关也有按仓库口径保留的尾巴：坐标事件咱们已板验取证，GNOME 下的触摸交互完整验收（虚拟键盘、拖动、多点）标记为待续，11 月的 eMMC 终验咱们还发现最小 rootfs 里缺 `goodix_911_cfg.bin`，触摸咱们暂时降级用芯片 OTP（一次性可编程存储）里的出厂配置，咱们还没验完。

## 成功长这样

收官态的补丁栈咱们数下来是 24 张正式补丁（0001–0006、0009–0021、0023–0025、0027、0028，0007/0008 留了档不入列），eMMC 正式镜像 `7.1.0-00024-ga7dad2806329`（MD5 `10e6e29d…`）咱们烧录后零 Oops。下面这段咱们截自终验 log（[finish/1.txt](../../logs/rk3588/finish/1.txt)），一个字咱们都没合成：

```
[    0.442890] rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
[    0.442926] rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[    0.895099] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
[    1.055436] Goodix-TS 2-0014: ID 911, version: 1060
[    1.073104] input: Goodix Capacitive TouchScreen as /devices/platform/feaa0000.i2c/i2c-2/2-0014/input/input0
...
rk3588-topeet login:
```

VOP2 和 DSI 咱们看到在 0.44 s 完成 bind，fb0 在 0.9 s 就建立了起来、面板跟着出画，触摸在同一秒内也注册成了 input0，系统一路走到了 login，GNOME 桌面上了屏。两点边界咱们照旧说清：本章所有板验记录都落在 v7.1 补丁栈上，内核章讲的 rebase 把这套序列带进了 v7.3.1。VOP2 候选镜像的稳定性保留意见与显示压力测试，按仓库口径是仍然挂在案上的。下一章咱们把 Mali-G610 的 Panthor 驱动点起来，桌面已经在屏上了，该让它有 GPU 加速了。
