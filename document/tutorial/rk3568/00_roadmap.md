# Ch0 — RK3568：阶梯的中间级

> 这一章咱们不敲命令。咱们把 RK3568 在 bring-up 阶梯（把一块新板从上电带到系统跑起来的过程，行话叫 bring-up）里的位置、这块板的硬件家底、本卷在主线与原厂 SDK 之间的方法论立场，连同全卷课程的真实状态一次交代清楚，让你拿着本页的导览决定从哪一章进、没有板的时候怎么读。

## RK3568 在阶梯里的位置：中间级，只做增量

RK3568 是一颗四核 Cortex-A55 的 AArch64 SoC，主打中端的档位。它在咱们的三级阶梯里占的是中间级：从 RK3506B 的 ARM32 与主线 bring-up 地基往上，咱们头一回进了 AArch64，头一回碰 ATF（ARM 官方的安全固件框架）和 PSCI（ARM 标准的电源管理接口），也头一回系统地学 Linux 的标准驱动框架，从设备模型的这些地基，一路学到 IRQ、DMA 和 I2C/SPI/UART 的总线框架。再往上的 RK3588 那一级，才轮到异构多核与 GPU、媒体、AI 这些产品级的课题。

RK3568 的主线支持比 RK3506 的成熟得多：pinctrl、clk、GIC（通用中断控制器）、USB、PCIe、GMAC（千兆以太网控制器）在主线里都是现成的，GPU 走的 Panfrost 是主线的开源驱动，VPU 的 Hantro 加 rkvdec2 也在树里。所以这块板移植的性质是“该有的主线里都有，剩下的活是拔掉原厂 SDK、把板级 DT 写出来”。DT（设备树）就是内核描述板级硬件用的数据结构。它的启动链也比 RK3588 的短了一截：原厂的 `rk356x_spl` 没赶上那场基址迁移的事故（RK3588 卷开场那回，SPL 与 BL31 的基址错配引出来一个不报错的 bootloop），所以咱们借原厂 SPL 加主线 U-Boot 就能起来，主线 SPL 也就不必换了。链上每一级的完整叙事，是[第一章](01_boot)的正题。

### 与上下两级：不重复，只增量

阶梯的纪律只有一条：每块板都得独立建立自己的证据链，固件、U-Boot、ATF、设备树、内核配置或镜像这一类的东西，咱们一样都不默认共享。同样都是 AArch64 的两块板，咱们也不能默认共用 RK3568 与 RK3588 之间的哪一样，平台边界的完整口径写在[教学路线](../../planning/rk3568/)里。

整条阶梯的分工，咱们用一张表对着看：

| 板 | SoC 与架构 | 那一卷的主课 | 教程现状 |
|---|---|---|---|
| RK3506B | Cortex-A7×3，ARM32（armhf） | 主线 bring-up、SPI-NAND/UBIFS 可靠性、SD 启动、buildroot/OpenWrt、工业接口 | 🟢 完整课，五段全兑现 |
| RK3568 | RK3568B2，Cortex-A55×4，AArch64 | AArch64/ATF 加标准驱动框架（本卷） | 🟡 MVP，01、02 两章已成 |
| RK3588 | A76×4 加 A55×4，big.LITTLE | 异构、GPU/媒体/AI 产品级 | 🟡 十章已成，仿真研究线收官 |

所以本卷不重讲 RK3506B 已建的东西，那些都收在下面这几条线的链接里，你缺哪块补哪块：

- [引导启动](../boot/)：主线 U-Boot 加板级设备树，从工具链到首启的通法。
- [根文件系统](../rootfs/)：buildroot 最小 rootfs、init 时序，还有 UBIFS 与 loader 弱写的那场长排查。
- [外设](../peripherals/)：Ethernet、USB、WiFi、I2C/UART、audio 的点亮经过。
- [SD 卡启动](../sd-boot/)：第二条启动路，纯 SD 卡也能进系统。
- [forge 编排器](../forge/)：把整条构建链收成一个命令的编排器。
- [OpenWrt 支线](../openwrt/)：给板子换一套真能 opkg 的发行版。

RK3568 的增量是 AArch64 那一层：头一回有 ATF（BL31 那一级常驻在最高的特权级 EL3），头一回用 binman（U-Boot 自带的镜像打包工具）自产 loader，做到了零原厂打包工具，启动存储也从 SPI-NAND 换成了 eMMC。这套 loader 的方案后来被 RK3588 卷整份沿用，那一卷又多走了一步，连 SPL 也换成了主线，两边的关系咱们放在后文的互文一节。

教学路线给这一级定过两项任务：帮学习者从 ARM32 的板级支持包（BSP，原厂发的那套内核加 U-Boot 加打包工具）进到 AArch64、ATF 与 64 位的用户系统，再拿真实的外设当载体，系统地学设备模型与标准驱动框架。结课的门槛也写在课纲里：你拿到一块新板，能独立完成常见外设的接入、调试、测试与交付。

反向的边界咱们同样立着：RK3568 不写成缩小版的 RK3588。NPU、复杂 ISP/VPU、Android 这些产品级的课题归 RK3588 那一级去管，RK3568 的主线是 AArch64 加标准驱动框架，产品化的锅咱们不背。

## 这块板：ATK-DLRK3568 的硬件家底

本卷的主角是正点原子的 ATK-DLRK3568。它和 RK3588 卷的迅为 topeet 板一样，都是原厂 EVB 的亲戚。正点原子拿的是 EVB1 DDR4 v1.0 参考设计，板名与参考设计的出处记在 [board.yaml](../../../boards/rk3568-atk/board.yaml) 的板头注释里，所以主线对 EVB1 的现成支持咱们能整份继承。规格的取法跟 RK3588 卷同款：写死在配置文件里的照配置文件，板上的读数以咱们自己的串口记录为准。

| 项目 | 规格 | 出处 |
|---|---|---|
| 板 | 正点原子 ATK-DLRK3568（Rockchip EVB1 DDR4 v1.0 参考设计），仓库代号 `rk3568-atk` | [board.yaml](../../../boards/rk3568-atk/board.yaml) 板头注释 |
| SoC | RK3568B2，AArch64 | 板上串口自报（U-Boot banner 的 `SoC: RK3568B2`），[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) |
| CPU | 四核 Cortex-A55 全部上线，`Brought up 1 node, 4 CPUs` | [13:11 串口](../../logs/rk3568/202607261311.txt) |
| 内存 | 4 GiB LPDDR4X，DDR 固件 v1.25 训练到 1560 MHz | [09:11 串口](../../logs/rk3568/202607260911.txt) 的 DDR 段 |
| 存储 | eMMC 58.3 GiB（C9A611），HS200 模式，GPT 三分区 p1/p2/p3 | 13:11 串口，[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md) |
| 供电 | RK809（PMIC，电源管理芯片），全板供电，音频 codec 也内置在里面 | [notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)、[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) |
| 调试串口 | UART2（内核里是 ttyS2），全链统一 115200 | [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 关键改动第七条 |

外设的清单与板验状态都在下面，咱们一项一项过，02 章会逐个讲移植的经过：

| 外设 | 型号与接法 | 板上状态 |
|---|---|---|
| 有线网 | 双 GMAC（gmac0/gmac1），RGMII（千兆 MAC 与 PHY 之间的接口标准）接两颗 RTL8211F | ✅ eth0/eth1 都通 |
| 显示 | 10.1 寸 800×1280 屏，走 MIPI DSI（显示屏的串行接口） | ✅ 点亮，panel IC 有争议（见下） |
| 触摸 | Goodix GT928，挂 I2C | ✅ `/dev/input/event0` |
| GPU | Mali-G52，主线 Panfrost 驱动 | ✅ DRM card1 |
| CAN | CAN1 控制器（rockchip_canfd） | ✅ 枚举成 can0 |
| RTC | pcf8563 | ✅ 板验过 |
| 音频 | RK809 内置 codec（rk817_codec）加 simple-audio-card | ⚠️ 声卡没 probe，GPIO 冲突 |
| WiFi/BT | rtl8852bs，走 SDIO（mmc2 一路） | 🚧 驱动已接线进构建，板上验证待做 |
| HDMI | 显示控制器的另一路输出 | ⚠️ 驱动 bound，未接屏 |

板上还有一批接口咱们整卷没碰。USB3、PCIe、SATA 在 sdk-diff 的表里排着 roadmap，摄像头与 VPU 的素材也还没攒齐，这些规划里的东西不进上面的状态表，免得把规划读成了事实。HDMI 咱们单独留在表里，因为它的驱动 bound 了、只是没接屏，记下的算板上发生过的事实。

LCD 的 panel IC 在两篇笔记里说法不一致，咱们照实摆。[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md) 的 workflow 分析从原厂 init sequence 的首命令认出 `B9 FF 83 99` 是 Himax 的 SETEXTC，把 IC 判成了 HX8394，而且主线 `panel-himax-hx8394.c` 已经在树里，移植的活只是补一块约 250 行的纯数据 descriptor，就是驱动里描述板级参数用的数据块。

可 [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 的交接状态表写的却是 ILI9881C driver，点亮它的也是 ATK 的板级 DT。[02 章](02_peripherals)采纳了 notes/41 的判断，理由是它有推理的依据、对应的主线驱动路子也更干净，但矛盾咱们没关死：写显示的深水章节之前，咱们得在板上读一次芯片 ID，把它的身份定下来。

后面全卷的取证都得靠调试串口，它出厂的默认波特率却是 1500000，咱们三处一起改成了 115200：DDR 的 blob 用 `ddrbin_tool` 改，U-Boot 的 defconfig 与内核侧跟着改，漏了一处，对应的阶段就是满屏乱码，统一的经过记在 notes/42 的关键改动里。烧写走的还是 Rockchip 的下载模式，RKBOOT ini 打出的 MiniLoaderAll 只当一次性下载助手，正常启动的链条上没有它。

## 主线，还是原厂 SDK：本卷的方法论立场

咱们整条教程线的主轴，是把原厂的那套 SDK 整个拔掉、换主线源码重走一遍。原厂 SDK 指芯片原厂 Rockchip 发的整套 BSP，魔改过的 U-Boot、内核加一套私有打包工具都在里面。这不等于原厂的东西没有用处，立场咱们说精确：主线能做的全走主线，原厂 SDK 咱们降级成参照物与提取池，闭源 blob 只在绕不开的位置保留。RK3568 手上正好摆着原厂世界的两份实物，咱们各看一眼。

一份是 Rockchip 的 Linux SDK（内核 5.10），它解在仓库的 reference 提取区（目录不入版本库），是 WiFi 驱动、io-domain（Rockchip 特有的 IO 电压域机制，外设的 IO 电压档跟电源域对不上就点不亮）、分区表这些细节的出处。另一份是咱们在 [notes/37](../../notes/37-2026-07-23-rk3568-android-sdk-build-flow.md) 里解剖的 Android 13 SDK：正点原子重打包的 Rockchip 多 SoC 包，26.5 GB 的 tgz 里只带 `.repo/` 不带工作树，本地展开后约有 105 GB 的体量。它的内核是 5.10.157，U-Boot 是原厂 2017.09 的老树，闭源的 blob 来自 rkbin，入口则是 `build.sh` 的一条龙（实体在 `device/rockchip/common/build/rockchip/`），一路编出了 update.img 才算完。

这套东西咱们后来真编通过了：咱们从 `lunch ATK_DLRK3568-userdebug` 起步，产出的 update.img 有 1.8 G、头部是 RKFW，boot.img、super.img 全套产物都验过魔数（notes/37 的完成小节），烧到板上的那一步没有做。

教学上咱们不选它。它教的是“把 Rockchip 的私有工具链跑顺”，咱们要教的其实是每一级为什么这样工作，两边要的东西正好相反。出了问题，闭源的 blob 加巨型脚本会把现场埋掉，咱们逐级对着串口取证的教法在里面施展不开。它自己成了一门赛道，塞不进 forge 的 `setup→build→pack→assemble` 编排，notes/37 的原话叫两个平行宇宙。所以它在本卷的身份是原厂对立面的参照：你读完 01 章的主线启动链，回头再看 build.sh 的整条龙，你就能看清，打包工具替你做的事、你要亲手理解的事，差别在了哪里。

主线这一边也不是纯白的。rkbin 的 DDR、SPL、BL31 三件闭源固件绕不开，这也是 Rockchip 三块板共同的硬边界。WiFi 的 rtl8852bs 走 SDIO，主线的 rtw89 不认 SDIO，只能用 Realtek 私有的那套驱动（原厂 SDK 里 851 个源文件），驱动咱们已经接进了构建，实况在全卷地图的 WiFi 行。NPU 的主线 Rocket 驱动只认 RK3588，RK3568 的 NPU 得走原厂 rknpu2 加闭源的运行时。每个子系统的差距，咱们看活文档 [sdk-diff-rk3568](../../sdk-diff-rk3568.md)，它的一行对一个子系统：原厂那侧有什么、主线这侧有没有、差的东西还挡不挡启动，跟着 bring-up 的推进持续更新。

闭源件咱们单独过一遍，取用的文件名都来自 board.yaml 的 rkbin 段：

| 固件 | 板上的取用 | 在链上的位置 | 主线能替吗 |
|---|---|---|---|
| DDR init | `rk3568_ddr_1560MHz_v1.*.bin`（实测 v1.25） | idbloader 的 TPL 段 | 不能，训练算法没有源码 |
| SPL | `rk356x_spl_v1.*.bin`（实测 v1.14） | idbloader 的第二段 | 能替，本卷借了原厂（理由见互文） |
| BL31（ATF） | `rk3568_bl31_v*.elf`（实测 v1.46） | 嵌在 u-boot.itb 里 | 不能，EL3 的运行时固件 |
| BL32（OP-TEE） | `rk3568_bl32_v*.bin` | 本卷省略了 | 非必需件，rkbin 发的裸 `.bin` 也对不上 binman 要的 ELF |
| usbplug | `rk356x_usbplug_v1.*.bin` | 不在正常启动链 | 无需替代，它是烧写侧的下载助手 |

闭源的三件里，SPL 本来是有主线替代的，咱们借原厂是配套验过的选择，互文的一节里有正反例。NPU 的情况则是另一回事：主线的 Rocket 只认 RK3588，notes/36 记了当时的拍板，NPU 是这块板存在的理由，所以原厂的 rknpu2 加闭源运行时留下的一处不干净，咱们认了。

## 全卷地图：课纲与真实状态

完整的课纲在[教学路线](../../planning/rk3568/)里，拢共是七卷二十章的编排，还外加了三个候选的毕业项目（驱动验证平台、轻量工业 HMI、PCIe/USB 与网络的综合设备），从 AArch64 的基线一路排到驱动质量与交付。课程化走到了哪一步，咱们分三档看。已经写成 tutorial 章节的算已课程化，本卷眼下写成了两章（01 启动、02 板级 DT），都挂着板上的串口证据。有 notes 素材、还没落成章节的算有素材未课程化，方案与数据是真的，动手的那一轮多数还没发生。课纲排了、板上却没有实验数据的算不抢跑，咱们不凭规划写成事实。

七卷的课纲全景，咱们对着下面逐卷读，右边一列是各卷对上的教程章节：

| 卷 | 章 | 主题 | 课纲状态 | 对应的教程章节 |
|---|---|---|---|---|
| 卷一：AArch64 与系统基线 | 1–4 | 平台全景、工具链/LP64、EL0–EL3 与 ATF/PSCI、U-Boot 与开发 rootfs | 🟡 部分已课程化（01 章） | 01 章（启动首启） |
| 卷二：Linux 驱动地基 | 5–7 | 字符设备、设备模型与 platform driver、DT binding | ⚪ 不抢跑 | 暂无 |
| 卷三：GPIO、中断、电源与时钟 | 8–10 | pinctrl/GPIO/input、GIC 与中断、clock/reset/regulator | 🟡 有素材未课程化（触摸、CAN、RTC 已板验） | 02 章（触摸、CAN、RTC 的板验素材） |
| 卷四：标准总线与真实设备 | 11–13 | I2C 与 regmap、SPI、UART/RS-485 | 🟡 有素材未课程化（I2C 触摸已板验） | 02 章（I2C 触摸的板验素材） |
| 卷五：DMA 与高速接口 | 14–17 | DMAengine、USB、PCIe/NVMe、GMAC/PHY | 🟡 有素材未课程化（双 GMAC 已板验） | 02 章（双 GMAC 的板验素材） |
| 卷六：显示与 HMI 选修 | 18 | DRM/KMS 入门 | 🟡 有素材未课程化（LCD、触摸已板验） | 02 章（LCD 与触摸的板验素材） |
| 卷七：驱动质量与交付 | 19–20 | 调试工具、可维护交付 | ⚪ 不抢跑 | 暂无 |
| 毕业项目 | — | 三个候选项目 | ⚪ 不抢跑 | 暂无 |

咱们再往下一层，看当前的真实进度，每行都带着它的依据：

| 线索 | 内容 | 状态 | 依据 |
|---|---|---|---|
| [01 引导启动](01_boot) | 主线 7.1 加 binman 自产 loader，板上首启到 login | 已课程化 | notes/36、notes/40，串口三份 |
| [02 板级 DT 八子系统](02_peripherals) | PMIC、双 GMAC、audio、触摸、LCD、GPU、CAN、RTC | 已课程化，DT 等 P4（内部工单号，指板级 DT 与 BOOTCOMMAND 的 quilt 化） | notes/41、notes/42 |
| WiFi（rtl8852bs） | armbian 适配版驱动已接线进构建，板上验证待做 | 有素材未课程化 | [notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md) 的交接，series 的 0001/0002 与 forge 的驱动取用，SDIO 已枚举 |
| buildroot Phase 2a 全栈 | Qt6、Mesa、GStreamer、Weston | 有素材未课程化 | [notes/38](../../notes/38-2026-07-24-rk3568-rootfs-mainline-equivalence.md)、[notes/39](../../notes/39-2026-07-24-qt6webengine-buildroot-port-feasibility.md) |
| QEMU 仿真研究线 | rk3568-lite 机器模型，bootm 加 FIT 已走通 | 有素材未课程化 | [notes/59](../../notes/59-2026-08-24-rk3568-qemu-sim-m0-day0.md) 至 [notes/66](../../notes/66-2026-08-26-rk3568-bootm-fit-relay.md) |
| 卷二：驱动地基 | 字符设备、设备模型、DT binding | 不抢跑 | 课纲已排，板上没有对应实验 |
| 卷五的 USB 与 PCIe | DWC3、PCIe/NVMe 框架 | 不抢跑 | USB3 控制器已起（12:32 与 13:11 里 xhci 都报 SuperSpeed），无设备级验证，PCIe 未板验 |
| 卷七：质量与交付 | ftrace/perf、可维护的交付 | 不抢跑 | 课纲已排 |
| VPU、NPU、摄像头 | 原厂 rknpu2、rkaiq 一类用户态栈 | 不抢跑 | sdk-diff 的 roadmap 行 |

依据里最全的是 01 章的板上证据，咱们回 `document/logs/rk3568/` 翻三份串口，09:11 记的是 DDR 训练与 SPL，12:32 记的是直载 autoboot，13:11 走完了到 login 的全链。

02 章的八子系统移植做完了，板验的记录咱们分开说。双 GMAC、触摸、LCD、GPU、CAN、RTC 六项的板验都过了。音频倒是一项负结果，hp-det 的 GPIO 抢了 i2s1 的 mclk，声卡的 probe 到今天没发生。PMIC 缺的是独立的板验行：notes/42 的板验表里没它，三份串口里主线 rk8xx 的探测也安静得一行都没有。它其实不算悬案，全板的电都是它供的，eMMC、LCD、GMAC 活得好好的，就算它活着的间接证据，只是按每行带依据的标准，这一项的依据确实间接。工程债的事另有一块，咱们单开一段讲。

WiFi 的移植路线调过一次。notes/42 第三节的 A1 方案原计划把原厂 5.10 的 851 个源文件自己适配到 7.1，实际接的时候换了路，armbian 社区把同一份 Realtek 驱动适配到了 7.1，咱们直接接它的 fork，forge 的取用步骤按 pin 把它取进内核树，再套一块 forge 自己的适配补丁，整份 drop 按工作源码的性质处理，在内核 clone 里进了 gitignore。落到仓库里的是三件实物：SDIO 总线上枚举出了 rtl8852bs（识别为 `vendor:0x024c`、`device:0xb852`），series 在册的 0001 补丁负责 Kconfig 与 Makefile 的两行注册，0002 的适配补丁在盘、由取用步骤施加。没做的属于板上那一头，insmod、wlan0、wpa 的验证都得板在手才做得成。那 851 个文件是 Realtek 私有的 phl 与 core 框架，跟主线的 rtw89 不属于一个体系。

buildroot Phase 2a 是本卷计划里 rootfs 全功能栈的代号，指的是 Qt6、Mesa、GStreamer、Weston 一套。它的素材是 notes/38 做的等价对照：那轮 workflow（自动编排的多步流程）放了十个 agent（各自替咱们干活的程序），把原厂 buildroot 的配置逐包对了一遍。八个功能域的条目共 148 个，数法里算上了跨域重复，大约七成的东西在主线 buildroot 开一个配置项就能拿到，真正必搬原厂的用户态栈去重后有八项，MPP、RGA、gstreamer-rockchip、rkaiq、alsa 的配置都在其列，NPU 的 rknpu2 是唯一没有主线等价的一类。

Qt6 已经进了 rootfs（455 MB 的体量），不过咱们还没在板上跑过 Qt 的应用。Qt6WebEngine 要不要进栈的问题，咱们也照着 notes/39 评估过了。

QEMU 的仿真线值得单独说一句。QEMU 主线的五十多个 ARM 机器模型里其实一个 Rockchip 都没有，Renode（另一个开源的全系统模拟器）的情况也一样，notes/59 的调研把这件事查实了。咱们的回应是自己写一个最小的 rk3568-lite 机器模型：4×A55、GICv3、UART、24MHz 时钟，让 U-Boot 用 `bootm` 起 forge 打包的同一份 boot.img（FIT 是按设备树结构打包内核与 DTB 的容器格式），四条断言都过了，六种模式的回归也全部 PASS。咱们按仓库的分工仍把它算研究线，因为它证明的只是软件控制流，板上的点亮还得真板说了算，课程化的事排在后面。

最要紧的工程债压在 02 章的头上，咱们把它摆到明处。板级设备树（PMIC、双 GMAC、RK809 audio、Goodix 触摸、LCD、GPU、CAN、RTC 八个子系统）、panel descriptor、U-Boot defconfig 的改动，虽然都进了板上跑着的系统，但目前还是 `third_party/src/rk3568-atk/` 里的 working-tree delta，也就是 clone 下来看不到的未提交改动。正式的 quilt 化（quilt 是内核圈管补丁序列的老工具，补丁进没进 series 的在册清单，就是咱们区分正式与非正式改动的界线）至今没有做，`boards/rk3568-atk/patches/linux/series` 在册的只有 rtl8852bs WiFi 的 0001 接线一发，0002 的适配补丁在盘、由取用步骤施加，不走 series 在册的路子。等别人重新 clone 了一份下来，这些外设他是复现不了的。这是 RK3568 落后 RK3588 一个工程化阶段的地方，RK3588 的补丁早已完整在册。

P4 收完的样子咱们也有参照。RK3588 卷在册的补丁有 linux 二十七发、U-Boot 十发，干的都是把板接到主线的活。咱们这一卷按 P4 收完，series 的形状也会长得一样：板级 DT 的一发、panel descriptor 的一发，再加 U-Boot defconfig 改动的一发。把这块债还上（内部叫 P4）是 RK3568 教程继续往下写的前置，sdk-diff 还补了一条执行顺序：panel descriptor 的精调还没在板上定稳，咱们就不抢着 patch 化了。

## 与 RK3588 卷的互文：两块板怎么串着读

两卷用的是同一种做法（拔原厂 SDK、换主线重走），RK3588 卷的十章已经写完，本卷的好几处都拿它当参照。互文的入口有七条，咱们挨个过：

- 启动链对照：本卷 01 章的链短一截、事故少，适合建立每一级的直觉。[RK3588 平台章](../rk3588/00_platform.md)的启动链全图是同一套机制的更复杂样本，每一级交接的加载地址、验签、闭源分界都在里面。
- SPL 取舍的正反例：RK3568 借原厂 SPL 借得心安理得，因为 `rk356x_spl` v1.14 与 BL31 v1.46 的交棒基址一致。RK3588 那边同号的 v1.14 SPL 对上了 BL31 v1.54 的基址迁移，出来一场没有报错的 bootloop，只能换主线 SPL。同版本号纯属两条版本线的巧合。两板合起来正好是一对正反例：闭源固件之间的配套约定，一块板上成立、另一块板上翻车，经验不能平移。那场 bootloop 的现场与修复，完整记录在 [notes/49](../../notes/49-2026-07-27-rk3588-bootloop-mainline-spl.md)。
- autoboot 与 FIT 暂存：两板各自独立验过同一个解法（FIT 暂存挪到 0x08000000，避开内核自己声明的加载地址），本卷 01 章的翻车二与 [RK3588 U-Boot 章](../rk3588/01_uboot.md)的 autoboot 一节互为印证。
- 内核版本：本卷全程用主线 v7.1，RK3588 卷在同一颗 7.1 上点亮后升到了 v7.3.1，那次 rebase 的经过，那一卷的[内核章](../rk3588/02_kernel.md)讲得最细。
- 显示：本卷 02 章的 LCD 是“主线有驱动骨架、补一块 descriptor”的干净样本。[RK3588 LCD 章](../rk3588/03_lcd.md)是同一套 DRM 框架的深水区（DSI 桥片的初始化时序、VOP2 死锁）。
- GPU：本卷的 Panfrost 驱 Mali-G52 直接就起来了。[RK3588 GPU 章](../rk3588/04_gpu.md)里 Panthor 的固件加载时机是进阶课题。
- rootfs：本卷走 buildroot 的 Qt6 教学栈，[RK3588 rootfs 章](../rk3588/05_rootfs.md)走 ubuntu-base 到 GNOME 桌面，两条路可以对照着看取舍。

两卷的时间线上还有一层渊源：RK3568 的 loader 基线在 2026 年 7 月 22 到 26 定型（notes/36 至 42），RK3588 的那一卷紧接着动工，把这套 binman 自产 loader 的做法带了过去。所以你读本卷的 01 章，读的其实就是那一卷链上前段的原型。

串读的顺序咱们给一个建议：拿本卷的 01 章打底建立直觉，再进 RK3588 卷的平台与 U-Boot 两章，看同一套机制在更复杂的 SoC 上翻出的花样。你想把显示做深，就把两卷的 LCD 章对着读，本卷看移植的形状，那一卷看时序的深水区。只冲方法论来的，那一卷的平台章加本卷的 01 章也就够了。边界咱们再念一遍：两卷不共用任何的固件、设备树或镜像，RK3588 卷的记录不能拿来当本卷的证据。

## 怎么用这一卷：没有板、查证据、选入口

没有板的读者也能读。01、02 两章的串口记录都是文本，咱们引的每一段样例（教程里的行话叫“成功长这样”）都能对着 `document/logs/rk3568/` 的原文核。再往前的预告是 QEMU 仿真线：它给了不开板也能把启动链跑起来的路，课程化的链接等它落成之后挂在这里。

手边有板的读者，烧写与救砖的工具操作按仓库的 [QUICK_START](../../../QUICK_START.md) 走，教程就不单独开工具课了，这是课纲定过的。教程要是对不上你的现场，咱们欢迎你去仓库的 issue 区报，串口原文贴上去就是最好的现场。

咱们查证据链的时候，document 的四个目录各管一层：

- `notes/` 是按天的流水笔记，取证源，不删也不去重。
- `pitfalls/` 是回溯提炼的事故叙事，按故障域分篇，每篇带定论与串口原文。
- `tutorial/` 是面向读者的成功路径，你在读的就是。
- `logs/` 是串口与构建的原始输出，教程里的引文都从这截。

RK3568 线的入口都在下面，你按需要挑着用：

- 启动与板级移植：[notes/36](../../notes/36-2026-07-22-rk3568-multiboard-and-mainline-build.md)（多板框架与 binman 接线）、[notes/40](../../notes/40-2026-07-26-rk3568-first-boot-and-next-push.md)（首启全记录）、[notes/41](../../notes/41-2026-07-26-rk3568-atk-mainline-dt-port-plan.md)（DT 移植方案）、[notes/42](../../notes/42-2026-07-26-rk3568-mainline-handoff-rtl8852bs-next.md)（交接状态表）。
- 原厂对照与 rootfs：[notes/37](../../notes/37-2026-07-23-rk3568-android-sdk-build-flow.md)（Android SDK 解剖）、[notes/38](../../notes/38-2026-07-24-rk3568-rootfs-mainline-equivalence.md)（rootfs 等价对照）、[notes/39](../../notes/39-2026-07-24-qt6webengine-buildroot-port-feasibility.md)（Qt6WebEngine 可行性）。
- 仿真线：notes/59 至 notes/66（rk3568-lite 从立项到 bootm 加 FIT 的收尾）。
- 串口三份：[202607260911.txt](../../logs/rk3568/202607260911.txt)、[202607261232.txt](../../logs/rk3568/202607261232.txt)、[202607261311.txt](../../logs/rk3568/202607261311.txt)。
- 板配置实物与活文档：[boards/rk3568-atk/](../../../boards/rk3568-atk/)（board.yaml、parameter、RKBOOT ini、ITS、boot 脚本、kernel.config、补丁 series），[sdk-diff-rk3568](../../sdk-diff-rk3568.md)。

状态的口径全仓统一。四档（🟢 verified、🟡 partial、⚪ planned、🔴 blocked）管的是工程证据，完整定义见[三板教学路线](../../planning/)的首页。本章的三档（已课程化、有素材未课程化、不抢跑）管的是课程化进度，而跟四档对不齐：一卷可以挂着四档里的 🟡 partial，同时在本章的三档里还是有素材未课程化。卷级的工程状态以 planning 那一页为准，章级的进度以本章上面的进度表为准，正文里咱们就不重复报了。

入口咱们按读者的来历分三类：

- 从 RK3506B 卷过来的读者，工具链、buildroot、forge 都在手，直接进[第一章](01_boot)就行，增量就是 AArch64 那一层。
- 做过原厂 BSP、想系统学主线驱动框架的读者，把本章与 01、02 两章读全，板上的事实就都在眼前了，后面的章节咱们写一章挂一章。
- 嵌入式新手，回 [RK3506B 教程](../boot/)打地基，那一卷的五段是完整课。

## 档案与证据：全卷的版本指纹

咱们引的版本号都回到这些源头，你复现构建时拿表里的版本对着核：

| 件 | 版本 | 出处 |
|---|---|---|
| U-Boot | 2026.07-rc4-00043-g5ca1a73c7d30（pin `5ca1a73c`） | board.yaml 的 sources.uboot，板上 banner |
| Linux | 主线 v7.1（板上构建号 #8，2026-07-26 13:05:43） | 13:11 串口 |
| DDR 固件 | rkbin v1.25（1560 MHz 档） | 09:11 串口 |
| SPL | 原厂 rk356x_spl v1.14 | 09:11 串口的 banner |
| BL31 | rkbin v1.46（built Sep 20 2025） | 09:11 串口的 NOTICE |
| rootfs | buildroot 2026.08-git | notes/40 |
| eMMC | C9A611，58.3 GiB，HS200 | 13:11 串口 |

板上 banner 尾巴上的 `-dirty` 不是脏数据，咱们查过它的来由：它就是工程债段里那行没 quilt 化的 defconfig 改动，01 章的翻车五有完整的解释。

所以本卷现在的正戏是启动首启那一章，外加板级 DT 的那一轮移植。咱们从 BootROM 一路跑到 busybox `login:` 的整条链开始。
