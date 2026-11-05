# Ch2 — 板级 DT 八子系统：从“能启动”到“能用”

> 上一章收尾的时候，链已经通了，主线 7.1 一路跑到了 `login:`。可镜像的家底还是 EVB1 的：`rk3568.dtsi` 里 SoC 级的控制器（GMAC、I2C、SPI、VOP、DSI、USB）主线里全有现成的，EVB1 参考设计之外的板级东西，像双网口的 PHY 时序、10.1 寸的屏、触摸、CAN、RTC、RK809 的供电与 io-domain，对它来说全是没见过的东西。这一章咱们写一块 ATK 专用的板级设备树（DT 就是内核描述板级硬件用的数据结构），起的名字是 `rk3568-atk-evb1-ddr4-v10.dts`，不再复用 evb1-v10 的老家底，把八个子系统一次都移植了过去，然后咱们逐项对着串口取板验。方案的出处是 [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)（DT 移植方案），板验的实况出自 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)（交接状态表），原始的串口都在 `document/logs/rk3568/`。

> 工程债的口径咱们放在开头交代：这一章对应的板级 DT 与 panel descriptor（panel 驱动里描述板级参数的纯数据块），目前是 `third_party/src/rk3568-atk/linux/` 工作树里的未提交改动，它的行话名是 working-tree delta，clone 下来是看不到的，正式的 quilt 化还没做。咱们把后果也说直接一点：本章教的是移植方法加板上的证据，第二个人按仓库的流程 clone 下来，这些外设他是复现不了的。这笔债的收法，文末的 P4 一节专门讲，读者把它当成“咱们当时是怎么移植的”的现场记录来读就行。

## 分诊：方案表与实况表对着读

板级的东西不在 SoC 的 dtsi 里，这是咱们要写专用 DT 的原因。

咱们从硬件说起。ATK 板用的 PHY 是 RTL8211F，RGMII 的链路要配收发 delay。屏是 10.1 寸 800x1280 的 MIPI DSI 屏，要自己的 init 序列与时序。触摸挂在 I2C 的总线上，IRQ 的极性得对着原理图配。供电集中在 RK809 的一颗身上，全板的电都归它管。io-domain 的声明也一样要做，它是 Rockchip 特有的 IO 电压域机制，管的是外设 IO 的电压档，档位跟电源域对不上的时候，外设就点不亮了。这些全都得写进板级的 `.dts`。复用主线 evb1-v10 的 DT，等于让板子戴着别人的帽子跑，SoC 的这部分能起，板级的外设却一概没人认。

方案不是咱们拍脑袋出的。[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 记的那一轮 workflow 放了 8 个 agent、烧掉 567k tokens（00 章交代过 workflow 的来路），做了子系统分析加 synthesis 加 critique（synthesis 把各方分析并成一份可执行的方案，critique 挑的是方案的毛病，这一轮 workflow 的三段就是这么分的）。分诊的结果，笔记里分了 A 与 C 两档：大半的子系统归 A 类，主线的驱动直接就能用，咱们的活只是把板级硬件在 DT 里接上 phandle。phandle 是设备树里引用别的节点的句柄。LCD 归 C 类里极小的一种，主线有 drm_panel 的骨架，缺一块板级的 descriptor。

WiFi 归 C 类的硬阻塞，rtl8852bs 走的是 SDIO 这一路，主线的 rtw89 不认 SDIO，也就只能搬原厂的驱动。WiFi 咱们只带一句：armbian 适配版的驱动已经接线进了构建，板上的验证咱们还没有做，按路线图排在后面的章，本章咱们就不展开。

分诊的质量咱们也交代一层。notes/41 留下的是 critique 之后的定稿：两条 major（sata2 的误判、IOVCC 的电压）都被纠回来了，还有一批 minor 也标了出来，backlight 的亮度档、fan 的供电轨、触摸的 compatible，核对的依据都得回原厂树或原理图去找。咱们在后文的 LCD 一节会回到它们身上，它们正好是接线活里最容易错的两类：资源的冲突与电压的档位。

两张表咱们对着摆。左边是 notes/41 方案期的预测，右边是 notes/42 板验后的实况：

| 子系统 | 方案分类（notes/41） | 板验实况（notes/42） |
|---|---|---|
| PMIC/电源/io-domain（RK809） | A 主线直接 | 无独立板验行，间接证据（见 PMIC 一节） |
| 双 GMAC（2× RTL8211F RGMII+delay） | A | ✅ eth0/eth1 双口通 |
| 触摸（GT911）+ adc-keys | A | ✅ GT928，`/dev/input/event0` |
| GPU（Mali-G52，Panfrost） | A 主线直接（本章补记，notes/41 原表未列） | ✅ Panfrost card1 |
| 音频（RK809 内置 codec） | A | ⚠️ 声卡没 probe，GPIO 冲突 |
| HDMI/USB/eMMC/TF/CAN1/RTC/fan | A | CAN/RTC/eMMC 板验过，HDMI bound 未接屏 |
| LCD（10.1 寸 800x1280 MIPI） | C 极小，补 descriptor | ✅ 点亮，panel IC 两说（见专节） |
| WiFi（rtl8852bs，SDIO） | C 硬阻塞，搬原厂驱动 | ❌ 待移植（SDIO 总线已枚举） |

表里 WiFi 的实况格要交代半句来路：它照录的是 notes/42 交接时的原文，当时的板验状态就是待移植。后来换路接 armbian fork 的驱动进构建，是交接之后的事，00 章的 WiFi 段记了换路的经过，板上的验证咱们到今天还没做。

notes/41 还排过首烧与二烧的期望：首烧想看到的是 console、eMMC/TF、eth、USB、CAN、RTC、fan、HDMI 与 RK809 的音频，二烧加了 panel descriptor 之后要点亮屏、触摸与背光。实况与期望的差别，咱们在两场正戏里都能对上。

两张表的分叉处，正好是本章的两场正戏。音频在方案表里归的是 A 类，notes/41 首烧的期望清单里还写着 aplay -l 见 “Analog RK809”，实况却是声卡的 probe 压根没发生，翻车的经过咱们单独开一节讲。LCD 的 panel IC，方案判的是 HX8394，实况点亮走的是 ILI9881C 的驱动骨架，这个矛盾咱们也没关死，留给后面的专节。方案表管的是“打算怎么干”，实况表管的是“板上发生了什么”，其实把两张对着读，分叉就出在音频与 LCD 的身上。

板级 DT 里实际写了什么，咱们看 notes/42 关键改动清单记下的底数：dsi1 名下挂 ILI9881C 的 panel 节点（带 power-supply 与 reset），gmac0/gmac1 配 RTL8211F 的 RGMII delay，RK809 的 sound 节点，GT911 的触摸，剩下 CAN1、RTC、fan、leds 也各归了各位。落地要走六步，notes/41 的清单排的是：

- 新写 dts，并在 Makefile 里加上 dtb 的一行。
- 补 panel 的 descriptor。
- kernel 的配置全 `=y`。
- U-Boot 的 defconfig 改 BOOTCOMMAND 与波特率。
- boot.scr 挪到 0x08000000。
- 一轮大重 build 加重 pack。

同一份清单的六步里，U-Boot defconfig 与 boot.scr 地址那两步走的是上一章讲过的启动链，咱们本章的正题是 dts、descriptor 与 kernel 配置这三步，末一步的大重 build 两边共用。

当天早上 09:11 那一轮还是 evb1 家底的旧镜像，屏是黑的。这笔实况记在 notes/40 的剩余问题表里，09:11 的 log 本身停在 U-Boot 的提示符，全程没有内核的输出。午后的大重 build 切到 ATK 板级 DT 之后，12:32 的记录（kernel #7）里 `Machine model` 已经报了 `Alientek ATK-DLRK3568 Board`，DRM、触摸与音频冲突的行都齐了。13:11 的记录（kernel #8）把 eth 与 GPU 的行也补齐了，一路走到了 login。三份 log 的分工 01 章讲过，本章的证据行号咱们都取自 13:11 的记录，音频冲突的第一次在案是 12:32 的第 438 至 441 行。

## 框架总开关：漏一个，整栈变模块

咱们把一条贯穿全部外设的教训放在正题前面说清楚，它出自 [kernel.config](../../../boards/rk3568-atk/kernel.config) 的注释，前前后后磨了三个来回才收敛。buildroot busybox 的 rootfs 里没有 modprobe，CONFIG 编成了 `=m`，开机的时候没人替它自动加载，效果上等于缺席了。全章在册的例外是 WiFi 的 rtl8852bs：它编的就是 `=m`，靠 S99wifi 启动脚本 insmod 的路子加载（kernel.config 的注释记着这笔，咱们还没在板上验过它）。而框架级的总开关一漏，依赖它的具体驱动全部跟着降成 `=m`，kconfig 的 select 机制救不了漏写的框架项。

咱们从网络的第一课说起。第一次出在网络的身上：`STMMAC_ETH`、`DWMAC_ROCKCHIP` 编成了模块，dmesg 里一行 eth 的影子都没有，`/sys/class/net` 只剩下了 lo（notes/40 的剩余问题表里记着它的名字）。这一课的修法记在同一张表里，就是把 kernel.config 的这两项改成 `=y` 重编。第二次轮到了显示：`CONFIG_DRM` 这个总开关漏了，整条显示栈（`DRM_ROCKCHIP`、`ROCKCHIP_VOP2`、`ROCKCHIP_DW_MIPI_DSI`、panel、PHY、backlight）全跟着降成了 `=m`，DRM 自然也就不 probe 了。第三次轮到了音频：`CONFIG_SOUND` 漏了，`SND`、`SND_SOC`、`RK817` 整栈都成了 `=m`，声卡自然也就没了踪影。同一类的毛病还埋在显示栈的深处：`PHY_ROCKCHIP_INNO_DSIDPHY` 漏编了它就 defer，屏也就不亮了。

咱们在 [kernel.config](../../../boards/rk3568-atk/kernel.config) 里留下的那一大段显式 `=y`，就是把这些框架总开关和具体驱动一个个写成 built-in 的结果，当时为什么这么改，注释里原样地留着（节选）：

```
# ---- Ethernet: 2x RTL8211F RGMII (was =m → no eth0 without modprobe; force =y) ----
CONFIG_STMMAC_ETH=y
CONFIG_DWMAC_ROCKCHIP=y
# ---- Audio: RK809 PMIC codec (ATK has NO ES8388) ----
CONFIG_SOUND=y                     # 框架总开关! (漏了它 SND/SND_SOC/RK817 整栈 =m)
CONFIG_SND_SOC=y
CONFIG_SND_SOC_RK817=y
CONFIG_SND_SIMPLE_CARD=y
# ---- LCD / DRM: ATK 10.1" MIPI ILI9881C ----
CONFIG_DRM=y                       # 框架 built-in! (漏了它整栈降 =m, busybox 无 modules)
CONFIG_DRM_PANEL_ILITEK_ILI9881C=y
CONFIG_PHY_ROCKCHIP_INNO_DSIDPHY=y  # dsi_dphy1 (fe860000) — 漏了它 =m, dsi1 defer 屏不亮
```

纪律就定了一条：每一栈的符号逐个 `grep .config` 确认 `=y`，咱们别信“会自动 select”。这个纪律在 RK3588 卷的内核章里同样立着，两块板交的是同一笔学费。

## A 类六项：接线、板验与读 log 的提醒

A 类的接线活，咱们归拢起来看，做的是同一套动作的重复：把控制器的 status 从 disabled 改成 okay，给外设挂 pinctrl 的组，给供电轨挂 regulator 的引用，再把 phandle 接到 dtsi 里对应的控制器上。八个子系统的大半，干的就是这套动作的各种组合。

A 类的六项（双 GMAC、触摸、GPU、CAN、RTC、PMIC）咱们按分量排着讲，证据行各带串口的时间戳。详略上咱们不搞平均：双 GMAC 和触摸值得咱们细读，GPU、CAN、RTC 咱们一笔带过，PMIC 单讲它怎么验。杂项（fan、leds、TF 卡、HDMI）都收在了节尾。

### 双 GMAC：delay 配在 MAC 一侧

两路控制器分别落在 fe010000 与 fe2a0000 的地址上，各自接了一颗 RTL8211F，phy-mode 配成 rgmii（RGMII 是千兆 MAC 与 PHY 之间的接口标准），收发 delay 按 ATK 的值，咱们把它配在 MAC 一侧，写进 GRF 里相应的寄存器。GRF 是 SoC 的通用寄存器区，板级的引脚配置与电压域的档位都住在它里面。13:11 的 log 里两路的注册是这样的（第 488 至 502 行是一段窗口，中间夹着的 pulseaudio、ssh-keygen 等行略去了）：

```
[    5.073257] rk_gmac-dwmac fe010000.ethernet eth0: PHY [stmmac-1:00] driver [Generic PHY] (irq=POLL)
[    5.127870] rk_gmac-dwmac fe010000.ethernet eth0: configuring for phy/rgmii link mode
[    5.207122] rk_gmac-dwmac fe2a0000.ethernet eth1: configuring for phy/rgmii link mode
```

咱们读这段时有三个提醒。

头一个提醒落在 PHY 的驱动名上：认领 PHY 的报文写的是 Generic PHY，RTL8211F 的专用驱动虽然编成了 `=y` 却没绑上，为什么没绑咱们没查过。链路照样通了，因为报文配的是 phy/rgmii 而不是 rgmii-id，它的含义是 delay 不加在 PHY 里、由 MAC 一侧承担，通用驱动带得了 rgmii 的链路。

另一个提醒说的是注册的时点：eth 的注册拖到了第五秒上下才完成，串口上它们混在 userspace 启动脚本的输出中间，Starting pulseaudio 与 ssh-keygen 的行间都能看到它，读的时候咱们别当成乱序。还有一个提醒说的是名字的互换。U-Boot 报的是 `Net:   eth1: ethernet@fe010000, eth0: ethernet@fe2a0000`（13:11 第 20 行），到了内核里，fe010000 成了 eth0，fe2a0000 成了 eth1。同一颗控制器挂着两套编号的体系，跟上一章 eMMC 三个名字的翻车四是同一类事，写脚本引用网口名的时候，两边咱们都得核一遍。板验以 notes/42 的表为准，两个口都验通了。

另外有一行容易让人多想的：第 318 与 337 行报的是 `supply phy not found, using dummy regulator`，说的是 gmac 节点没给 PHY 单独声明供电轨，内核垫了一个空的。它倒是挡不住链路，读的时候咱们把它当背景噪音放过去。双 GMAC 的板验素材对应课纲卷五的 GMAC/PHY 一课，00 章的全卷地图里咱们标过它的位置。

### 触摸：DT 写 gt911，板上读出 GT928

触摸 IC 挂在 i2c1（fe5a0000）的 0x14 地址上。DT 里的 compatible 写的是 `goodix,gt911`，这个值咱们是从原厂树里的 tp-size=911 推断的（notes/41 的 critique minor 记了推断的来路），主线 goodix 驱动上了电会自己读 chip_id 再适配，IRQ 的极性也按 EDGE_FALLING 转换过。板上的实况是这样的（第 431 至 433 行）：

```
[    3.688868] Goodix-TS 1-0014: ID 928, version: 6010
[    3.695375] Goodix-TS 1-0014: Direct firmware load for goodix_928_cfg.bin failed with error -2
[    3.722572] input: Goodix Capacitive TouchScreen as /devices/platform/fe5a0000.i2c/i2c-1/1-0014/input/input0
```

读出来的 ID 是 928，驱动于是把芯片按 GT928 对待了，DT 里写的型号名与芯片本体不是同一颗，绑定倒是没受影响。中间那行 -2 是缺 `goodix_928_cfg.bin` 之后的回退，触摸的事件照样注册了 input0，所以咱们把它当记录而不是故障。严格地说，触摸的配置究竟从哪来的（芯片里烧的或出厂缺省值），咱们没验证过。同一条 I2C 的线上还挂着 adc-keys，它报了 input2（第 464 行）。触摸的供电轨（AVDD28/VDDIO）按原厂的值抄了 `vcc5v0_sys`，notes/41 把它列进了待原理图核对的清单，不过到今天咱们也没核。

### GPU：Panfrost 一次到位

Mali-G52 走主线的开源 Panfrost 驱动，fragment 里的一行 `CONFIG_DRM_PANFROST=y` 就够。咱们在板上看到的证据是这样的（第 456 至 463 行）：

```
[    4.305394] panfrost fde60000.gpu: clock rate = 594000000
[    4.323621] panfrost fde60000.gpu: mali-g52 id 0x7402 major 0x1 minor 0x0 status 0x0
[    4.371650] [drm] Initialized panfrost 1.6.0 for fde60000.gpu on minor 1
```

minor 1 的意思是 card1：card0 让给了显示子系统（第 453 行的 minor 0），GPU 是板上的第二块 DRM 设备，时钟拉到了 594 MHz。这里咱们还要消一个容易混的名字：RK3588 的 Mali-G610 走的是 Panthor，而那已经是另一套驱动栈，固件加载的时机在那一卷的 GPU 章里是进阶课题。Panfrost 与 Panthor 的名字相近，驱动栈却是分开的两套，咱们写笔记的时候别把两个串了。

### CAN 与 RTC：快写

CAN 与 RTC 咱们快写。CAN1 的控制器在 fe580000，枚举成了 can0（第 303 至 304 行）：

```
[    2.101471] rockchip_canfd fe580000.can can0: Rockchip-CANFD rk3568v2 rev2.2 (errata 0x1fff) found
[    2.111543] rockchip_canfd fe580000.can can0: Erratum 5: CAN clock frequency (150MHz) lower than known good (300MHz), expect degraded performance
```

第二行是驱动自己交代的勘误警告：CAN 时钟 150 MHz 低于它认可的 300 MHz，位时序的余量要打折。can0 的注册不受影响。警告背后的时钟树哪一档没配对，咱们没查，咱们在这里如实记下。RTC 是 i2c5 上的 pcf8563（`5-0051` 表示总线 5 上的 0x51 地址），注册成了 rtc0，还把系统时钟设到了 2026-07-26T05:07:18 UTC（第 358 至 359 行），开机时间戳的来源就是它这一设。

### PMIC 与 io-domain：间接证据的口径

RK809 这一颗管着全板的供电，音频的 codec 也内置在它的身上，io-domain 按板上的 1.8V/3.3V 档声明。这一步要是配错了，轻则外设的表现不稳，重则外设干脆就不说话了，所以在方案的分诊里，它算 A 类里唯一要动脑子的地方。它的板验实况咱们照实说：notes/42 的状态表里没有 PMIC 的行，三份串口里内核侧主线 rk8xx 的探测一行都没有。U-Boot 的 banner 里倒是有 `PMIC: RK809` 一行，那是 bootloader 报的，读者拿 RK809 去 grep，头一个碰上的就是它，别当成内核的探测。13:11 的 log 里电源侧只有两行 image 电压轨的调整（第 429 至 430 行）和 i2c0 上 0x1c 一颗 fan53555 的探测（第 419 行），RK809 自己倒是一声没吭。

它倒是不算悬案。全板的 eMMC、LCD、GMAC 都活得好好的，电是它供的，这些就算它干着活的间接证据，00 章也是这么记的。只是按每行带依据的标准，独立的板验行确实是欠着的，咱们把它标成间接。至于 i2c0 上那颗 fan53555 的身份，两篇笔记都没写过它的名字，咱们不知道，留给拿原理图的人去认。有一个疑问咱们也摆在明处：log 里连 rk809 的 I2C 探测都没有，咱们分不清是 DT 的节点没写进去，还是驱动的 CONFIG 没编进去，答案得等下一次翻开 working-tree 里的 dts 原文。

### HDMI 与杂项

HDMI 是显示控制器的另一路输出，bound 的证据有三行（第 449 至 451 行），咱们贴在下面：

```
[    3.908605] dwhdmi-rockchip fe0a0000.hdmi: Detected HDMI TX controller v2.11a with HDCP (DWC HDMI 2.0 TX PHY)
[    3.920499] dwhdmi-rockchip fe0a0000.hdmi: registered DesignWare HDMI I2C bus driver
[    3.931151] rockchip-drm display-subsystem: bound fe0a0000.hdmi (ops dw_hdmi_rockchip_ops)
```

咱们没接屏，notes/42 记的 card0-HDMI-A-1 是 disconnected，咱们把枚举成功当作它板上的终点，点亮这一步咱们不宣称。它的音频那路 hdmi-sound 在第 511 行 deferred（parse error），归到音频的尾巴一起记。

杂项咱们收五件。PWM 风扇的供电轨 fan-supply 按原厂指了 `dc_12v`（12V 风扇），草案曾把它误写成了 `vcc5v0_sys`，被 notes/41 的 critique 改正。backlight 的 default-brightness 也按原厂的值，从草案的 100 改到了 255。GPIO 灯与 fan 一样进了 fragment，log 里没有它们俩的行，风扇转了没有、灯亮了没有，咱们没记板验。TF 卡槽（dwmmc fe2b0000）报了 `Got CD GPIO`（第 438 行），卡在位的检测通了。eMMC 的 HS200（第 375 行）属于上一章的存储线，咱们在这里只报个名。

## 音频翻车：一根引脚，两个申请者

音频的架构咱们铺垫三句。这板没有独立的音频 codec（没有 ES8388），模拟的音频在 RK809 的身上，内核侧由 rk817_codec 的驱动来管。机器那一层用的是主线的 simple-audio-card 这个 machine driver（machine driver 是把 CPU 侧数字音频接口与 codec 粘在一起的胶水驱动），因为原厂的 `rockchip,multicodecs-card` 不在主线（notes/41 的音频修正条目）。配置侧的 `SND_SOC_RK817`、`SND_SIMPLE_CARD`、`SND_SOC_BT_SCO` 全 `=y`，框架总开关的教训上一节讲过了。方案表把它归了 A 类，实况翻了车。

翻车的现场，12:32（kernel #7）与 13:11（kernel #8）的两轮 log，其实翻在了同一个点上。13:11 第 439 至 443 行的五行，咱们按原文照引：

```
[    3.773659] rockchip-pinctrl pinctrl: pin gpio1-4 already requested by fe410000.i2s; cannot claim for rk809-sound
[    3.788284] rockchip-pinctrl pinctrl: error -EINVAL: pin-36 (rk809-sound)
[    3.793075] mmc_host mmc0: Bus speed = 375000Hz (req 400000Hz, actual 375000HZ div = 0)
[    3.795899] rockchip-pinctrl pinctrl: error -EINVAL: could not request pin 36 (gpio1-4) from group hp-det on device rockchip-pinctrl
[    3.818239] asoc-simple-card rk809-sound: error -EINVAL: Error applying setting, reverse things back
```

五行里第 441 行是路过的 mmc 消息，说的是控制器扫卡的总线频率，音频自己的报错实为四行。串口上全板的输出走的是同一条道，就绪了的驱动随时插行进来，咱们读的时候按报文的主体把行归位，别让路过的消息带偏。

咱们把机制读出来。gpio1-4 是 GPIO1 组的第 4 根脚，全局的编号是 36（32+4）。fe410000 是 i2s1 的控制器，notes/42 记了它的 mclk 用这根脚。rk809-sound 这个声卡的 hp-det 组也要同一根，hp-det 做的是耳机插入的检测。pinctrl 按申请的次序仲裁，早一步的 i2s 把脚留下，晚一步的声卡吃 -EINVAL，一处 pinctrl 应用的失败就让它整体回滚（log 里那句 reverse things back），声卡就不注册了。落款在 ALSA 的设备清单里（第 467 至 468 行）。ALSA 是 Linux 的音频子系统，名单是这样的：

```
[    4.439625] ALSA device list:
[    4.442942]   #0: rockchip,bt
```

名单里只剩下了 `rockchip,bt`，那是 `SND_SOC_BT_SCO` 的虚拟卡，给蓝牙的通话音频占位，RK809 的模拟音频不在它名下。咱们验声卡的时候看的就是 ALSA 的名单，名单里少了一行，板上的声卡就少了一块。

咱们把定性看准了：报错挂在了 rk809-sound 的名下，乍看像驱动的失败，其实主线驱动一样不缺，毛病出在 DT 的接线表内部，两处节点要了同一根脚。修法 notes/42 给了两条，一条路是把 hp-det 挪到别的 GPIO 上，另一条路是让 i2s1 的 mclk pinctrl 组，从 gpio1-4 的身上避开。当时两个方向咱们都没做，交接到了今天，咱们也没等来声卡的 probe。改法的取舍，得看原理图上耳机检测实际走的线，咱们手上没有 ATK 的原理图，这一步咱们等图到位再定。音频的尾巴还有一条：hdmi-sound 的 simple-card 解析报错（第 511 行），它以 deferred 的状态挂着，咱们也没修。

## LCD：补一块 descriptor，外加 IC 身份两说

LCD 的戏分三折，咱们按顺序走：头一折是 descriptor 的形状，中间一折是身份的两说，收尾一折是 critique 的待办。身份的事放在中间，因为它牵着前后的两头。

### descriptor 的形状

LCD 是八个子系统里唯一要动内核源码的。主线 drm_panel 的骨架已经在树里，咱们补的是一块纯数据 descriptor：屏的 init 序列、lane 数、timing、mode 的标志，descriptor 里装的全是数据，咱们一行逻辑都不用写。实况按 notes/42 的关键改动记：descriptor 加在 `panel-ilitek-ili9881c.c` 里，descriptor 的名字是 `atk_10p1_desc`，194 条 init 从原厂 DT 的 panel-init-sequence 机械翻译过来，`.lanes=4`（漏了会卡死），timing 按原厂的 67 MHz，mode 的取值是 VIDEO_BURST。

机械翻译的活咱们说精确：序列的字节搬过去了，但原厂每条命令之后的 5ms 延时没有跟着搬，序列的尾命令也与驱动骨架自带的 prepare 流程有重复。屏亮说明主路径是对的，它们正是精调一节要收的尾（notes/42 的待办清单记了它们）。DT 的一侧给 dsi1（fe070000）挂了 panel 节点，节点里带上了 power-supply 与 reset 两样，reset 的脚是 GPIO4_PB5。配套的 PHY 是 fe860000 的 dsi-dphy1，`PHY_ROCKCHIP_INNO_DSIDPHY` 漏编了它就 defer，屏也就不亮了（kernel.config 的注释里记着它）。

点亮的证据，log 在第 452 至 455 行里给了咱们四行：

```
[    3.940845] rockchip-drm display-subsystem: bound fe070000.dsi (ops dw_mipi_dsi_rockchip_ops)
[    3.951315] [drm] Initialized rockchip 1.0.0 for display-subsystem on minor 0
[    4.255000] Console: switching to colour frame buffer device 100x80
[    4.291880] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
```

100x80 按每字符 8x16 的字号折算，折出来的正是 800x1280，console 切进了这块屏的 framebuffer（帧缓冲就是内核给用户态的一块能直接写像素的内存），fb0 也紧跟着注册了。notes/42 另记了 card0-DSI-1 connected 与 fb0 写入，那行出自板上的会话，并没有留在三份归档的 log 里，咱们标着来源转述。

### HX8394 还是 ILI9881C

屏 IC 的身份，两篇笔记的说法不一致，咱们把两说摆开。

咱们看的是 [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 一侧的推理：workflow 从原厂 init 序列的首命令认起，序列的起点是 `B9 FF 83 99`，这是 Himax 的 SETEXTC（扩展命令解锁），于是把 IC 判成了 HX8394。主线的 `panel-himax-hx8394.c` 恰好就在树里，方案就是给它加上约 250 行的 descriptor，of_match 的新项起名叫 `atk,rk3568-evb1-hx8394-10p1`。可 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 的交接状态表写的是 ILI9881C driver 加 ATK DT 点亮，工作树里实际加 descriptor 的文件是 `panel-ilitek-ili9881c.c`，[kernel.config](../../../boards/rk3568-atk/kernel.config) 的实物也是 `CONFIG_DRM_PANEL_ILITEK_ILI9881C=y`。屏也一样亮了。

咱们再补一层解读，注意它出自咱们的推理、不是笔记里的记录：descriptor 的活，本质是把原厂的 init 序列按字节推进 DSI，骨架里 sleep out、display on 的通用尾巴家家都有。同一份原厂的序列，套在哪家驱动骨架的身上都能推，所以拿 ILI9881C 骨架点亮的这件事，也反推不出屏的 IC 就是 ILI9881C。两说的证据强度其实并不对称：HX8394 有从命令字节出发的推理，ILI9881C 有点亮的现场，咱们把两说摆平，不替读者拍板。00 章的正文里记过一句“采纳了 notes/41 的判断”，那个采纳指的是工作假设，咱们真要定谳，证据只能在板上读：办法是走 DSI 读一次芯片的 ID，或者对 ATK 的原理图。这件事列进了待办，咱们把它记成写显示深水章之前必须做的事。身份一旦定了，连带的两件事也跟着悬：descriptor 的精调没有基线，P4 的 patch 化也在等它（见文末）。

### 方案 critique 留下的三处待办

notes/41 的 critique 有两条 major、一批 minor，咱们挑与 DT 直接相关的三处交代。

头一条落在 sata2 的身上。synthesis 那时判断的是 pcie3x2 与 sata2 抢 combphy2，于是把 sata2 列进了关闭的名单，critique 纠正了它：pcie3x2 走的是专用的 pcie30phy，sata2 用的是 combphy2，两边其实不冲突，真正抢 combphy2 的是 pcie2x1（ATK 没用这一路）。DT 里的 `&sata2` 保持了 status okay。log 的末尾，电源域 sync_state 的挂起名单里有 fc800000.sata（第 513 行），咱们把它读作节点在、设备自己还没 probe 完，而不是被咱们关掉了。

咱们看的另一条 major 是 IOVCC 的电压。草案把 vcc/iovcc 都指了 3.3V，可 IOVCC 在物理上常是 1.8V 的档位，hx8394 的驱动用 `devm_regulator_get` 拿电，拿电的请求是非可选的，缺了就 -EPROBE_DEFER。烧板之前咱们要对着 ATK 的原理图核三样，面板 VDD/IOVCC 实际的 LDO、控制的 GPIO、电压的档位。不过这件事到交接时也没核。io 电压配错的这类毛病不炸在启动日志里，炸在外设的稳定性上，值得咱们单独立一项盯着。

精调的收尾也没做完。descriptor 的两处尾巴（每条的延时、尾命令的重复）咱们在 descriptor 一节已经点过名，等屏黑或花屏了再调。sdk-diff 的执行顺序因此写明：descriptor 的板级精调还没定稳，咱们不抢着 patch 化。这也是 P4 一节的前置条件。

## 工程债 P4：三发补丁的欠单

眼下的现状是三件套都困在了工作树里。咱们说的三件套是：板级 DT（`arch/arm64/boot/dts/rockchip/rk3568-atk-evb1-ddr4-v10.dts` 连同 Makefile 的 dtb 行）、panel descriptor（`panel-ilitek-ili9881c.c` 的 `atk_10p1_desc`）、U-Boot defconfig 的 BOOTCOMMAND 与 BAUDRATE 改动，全部是 `third_party/src/rk3568-atk/` 里 clone 下来就看不到的未提交改动。

series 一侧的实况，咱们看 [patches/linux/series](../../../boards/rk3568-atk/patches/linux/series) 的在册清单：只有 rtl8852bs WiFi 的 0001 一发（Kconfig 与 Makefile 的两行注册），0002 的适配补丁在盘、由拉驱动的 fetch 脚本另行施加，板级 DT 与 descriptor 的哪一发都不在。series 文件的头注释把这件事写得明明白白，头注释的原话大意是：ATK 板级 DT 与 ILI9881C panel 的改动，眼下以 working-tree delta 的形式存在，还没有 quilt 化进 series 的在册清单。后果也够直白的。第二个人照着 `forge setup` 的流程 clone 下来，这板上的八个子系统，他是复现不出来的，上一章的 autoboot 也得他自己补 defconfig。板上跑着的系统，与仓库里能复现的系统，中间差的正是这三件。

P4 收完的形状，咱们在 00 章里定过它的样子：板级 DT 的一发、panel descriptor 的一发、U-Boot defconfig 的一发，三发都进 series 的在册清单，参照的是 RK3588 卷的样子，那一卷的 linux 二十七发、U-Boot 十发全都在册。

sdk-diff 给 P4 写的做法咱们照录：拉树用 `forge setup --board=rk3568-atk`，要拉一份干净的、带 `.git` 的 v7.1 源树，然后把三处的改动各自做成 quilt 补丁，再进 series 的在册清单。RK3588 卷的 series 就是现成的参照，它的 series 文件里每一发都带着决策注释，咱们照那个样子写就行。

顺序上咱们听 sdk-diff 的：它把 patch 化排在待办的第一位，同时写了它的前置：panel descriptor 的精调得在板上定稳。所以 P4 的实际入口是回到板上，把屏 IC 的 ID 读了、把 init delay 的精调做了、把音频的 GPIO 冲突一并修掉，然后按三发的形状一次 quilt 化。rtl8852bs 的板验与 USB3/PCIe 这些 roadmap 项，sdk-diff 把它们排在了 patch 化的后面，顺序它说了算。

咱们把这件事的分量也说清楚：教程的门槛是第二个人能 clone 复现，RK3588 卷的补丁齐全，本卷的三发还欠着。这也是 00 章把本卷标成 MVP 的原因，MVP 的边界就压在它的身上。

## 成功长这样

一轮大重 build（kernel 的 dtbs 与 Image、u-boot、重 pack）之后，13:11 的 log 从第 2.1 秒到第 5.2 秒把八个子系统的命运过了一遍。咱们摘主线索，行号是 [202607261311.txt](../../logs/rk3568/202607261311.txt) 的行号：

```
[    2.101471] rockchip_canfd fe580000.can can0: Rockchip-CANFD rk3568v2 rev2.2 (errata 0x1fff) found
[    2.830729] rtc-pcf8563 5-0051: registered as rtc0
[    2.837394] rtc-pcf8563 5-0051: setting system clock to 2026-07-26T05:07:18 UTC (1785042438)
[    3.039646] mmc1: new HS200 MMC card at address 0001
[    3.064842]  mmcblk1: p1 p2 p3
[    3.688868] Goodix-TS 1-0014: ID 928, version: 6010
[    3.722572] input: Goodix Capacitive TouchScreen as /devices/platform/fe5a0000.i2c/i2c-1/1-0014/input/input0
[    3.773659] rockchip-pinctrl pinctrl: pin gpio1-4 already requested by fe410000.i2s; cannot claim for rk809-sound
[    3.940845] rockchip-drm display-subsystem: bound fe070000.dsi (ops dw_mipi_dsi_rockchip_ops)
[    4.255000] Console: switching to colour frame buffer device 100x80
[    4.291880] rockchip-drm display-subsystem: [drm] fb0: rockchipdrmfb frame buffer device
[    4.323621] panfrost fde60000.gpu: mali-g52 id 0x7402 major 0x1 minor 0x0 status 0x0
[    4.371650] [drm] Initialized panfrost 1.6.0 for fde60000.gpu on minor 1
[    4.439625] ALSA device list:
[    4.442942]   #0: rockchip,bt
[    5.073257] rk_gmac-dwmac fe010000.ethernet eth0: PHY [stmmac-1:00] driver [Generic PHY] (irq=POLL)
[    5.127870] rk_gmac-dwmac fe010000.ethernet eth0: configuring for phy/rgmii link mode
[    5.207122] rk_gmac-dwmac fe2a0000.ethernet eth1: configuring for phy/rgmii link mode
```

咱们再给一段读 log 的提醒。第 5 秒前后的 eth 行混在 userspace 脚本的输出里，ALSA 的清单（第 467 至 468 行）落在 EXT4 挂载（第 470 行）的前头，而 init 要到第 475 行才登场，排序的依据只有时间戳。看声卡名单的另一个入口是板上的 `/proc/asound/cards`，它交出的内容与 log 里的清单是同一份。表里的行号咱们都核过原文，读者拿着行号去翻 [202607261311.txt](../../logs/rk3568/202607261311.txt) 的原文，完整的上下文就在那里。login 的原文与 deferred 的尾巴，01 章的收尾一节已经引过（log 第 508 至 523 行），咱们这里不重复贴，只把与外设有关的三条对上号。sdio-pwrseq 与 fe000000.mmc 的 defer，是 WiFi 那一路还没收的尾。hdmi-sound 的 parse error 归音频。pcie 与 sata 的挂起归 roadmap。

八个子系统的板验状态，连同编外的 HDMI，咱们连着证据行收进一张表：

| 子系统 | 板上状态 | 证据 |
|---|---|---|
| 双 GMAC | ✅ 双口通 | 13:11 第 488 至 502 行，notes/42 板验 |
| 触摸 | ✅ | 第 431 至 433 行 |
| GPU | ✅ card1 | 第 456 至 463 行 |
| CAN | ✅ can0 | 第 303 至 304 行 |
| RTC | ✅ rtc0 | 第 358 至 359 行 |
| LCD | ✅ 点亮 | 第 452 至 455 行，panel IC 两说（专节） |
| PMIC | 🟡 间接 | log 无 rk8xx 行，全板外设活着算间接（专节） |
| 音频 | ⚠️ 没 probe | 第 439 至 443 行，GPIO 冲突（专节） |
| HDMI | ⚠️ bound 未接屏 | 第 449 至 451 行 |

到了这一步，板子从能启动进到了能用。没收尾的咱们照实列：音频的 GPIO 冲突、WiFi 的板验（驱动已接线进构建）、LCD 的 chip ID 定谳与精调、P4 的三发补丁，再往外的 USB3、PCIe、VPU、NPU，在 sdk-diff 的 roadmap 里排着队。这些活归 P4 与后续的轮次，全卷的地图在[路线图](00_roadmap)。

## 档案与证据

出处大多收进下面的清单，正文里咱们只留必要的现场标注，读者要对照原始证据的时候看这里：

- 过程记录：[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)（首启全记录与剩余问题表，工程债的来路）、[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)（DT 移植方案与 workflow 分诊，本章主源）、[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)（交接状态表与关键改动，本章另一主源）。
- 活文档：[sdk-diff-rk3568](../../sdk-diff-rk3568.md)（逐子系统的差距与下一步的执行顺序，working-tree delta 的诚实声明也在它开头）。
- 串口三份：[202607260911.txt](../../logs/rk3568/202607260911.txt)（DDR 训练与 SPL/BL31，01 章主用）、[202607261232.txt](../../logs/rk3568/202607261232.txt)（kernel #7，音频冲突的第一次在案，第 438 至 441 行）、[202607261311.txt](../../logs/rk3568/202607261311.txt)（kernel #8，全链到 login，本章主战场，第 303 至 523 行）。
- 板配置实物：[kernel.config](../../../boards/rk3568-atk/kernel.config)（fragment 全文，框架总开关的四条注释都在里面）、[patches/linux/series](../../../boards/rk3568-atk/patches/linux/series)（在册状态与 working-tree delta 的头注释）、[board.yaml](../../../boards/rk3568-atk/board.yaml)。
- 版本指纹：Linux 主线 v7.1（板上构建号 #8，2026-07-26 13:05:43）、U-Boot 2026.07-rc4-00043-g5ca1a73c7d30-dirty（pin `5ca1a73c`，dirty 的尾巴正是 defconfig 那笔未 quilt 化的改动，01 章翻车五讲过）、rootfs buildroot 2026.08-git、eMMC C9A611 58.3 GiB（HS200）。
- 跨卷参照：[RK3588 内核章](../rk3588/02_kernel.md)（原厂 dts 三堆分拣的移植方法论，比本章的接线活更深一层）、[RK3588 LCD 章](../rk3588/03_lcd.md)（同一套 DRM 框架的深水区）、[RK3588 GPU 章](../rk3588/04_gpu.md)（Panthor 与 Panfrost 的对照）。
