# Ch2 — LCD 移植 saga：TC358775 桥 IC 与 9 条 gotcha

> 启动章把板子跑到了 systemd，可桌面是黑的——因为这块屏还没点。这一章是整个 RK3588 移植最深的一条 saga：拖了整整四个镜像才出图，中间踩了「9 条致命 gotcha」「两个 kernel.config blocker」「DSI 视频流没到桥」「VOP2 handoff 硬锁」四道关，每一关都够单独写一篇。完整记录见 [notes/44](../../notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)（驱动+DT）、[notes/45](../../notes/45-2026-07-31-rk3588-lcd-bringup-blockers.md)（两个 blocker）、[notes/47](../../notes/47-2026-08-01-rk3588-lcd-video-fix-tc358775-init-prepare.md)（视频空白真凶）、[notes/54](../../notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)（VOP handoff 硬锁）。

> 诚实先说在前：到本章末尾，屏能出图（企鹅 logo + fb0 花屏），但 VOP2 handoff 的修复当前还是候选镜像（`2846097b…`），连续冷热启动和桌面长跑的稳定性没有闭环。所以这一章写的是「怎么把屏点亮」，不是「显示已经稳定」——稳定性那一刀还差真机多轮板验。

## 这块屏的物理拓扑，为什么这么难

topeet 这块屏是 10.1" 1024×600，但它不是一块直连 DSI 的屏——中间有一颗把 DSI 转成 LVDS 的桥接 IC。信号链是：

```
VOP2 (video_port2) ──OF-graph──► DSI0 控制器 ──► mipidcphy0 ──► DSI PHY 出线 ──► [TC358775 桥 IC] ──► LVDS 屏
                                                                                     GT911 触摸 on i2c2
```

难就难在三处。一是主线内核里没有这颗桥 IC 的驱动（后来发现 `drivers/gpu/drm/bridge/tc358775.c` 其实有一个，但 vendor 没用它，咱们一开始也没认出来）。二是 vendor BSP 用的是私有的 `simple-panel-dsi` + `panel-init-sequence` 绑定——把一整段厂商给的 DSI 初始化字节序列塞进设备树，由 vendor 的 `panel-simple.c` 重放，这套绑定主线没有。三是 vendor SDK 里默认激活的根本不是这块屏，是 MIPI1 那块 800×1280 的 HX8394——照 vendor 默认配置抄会抄错对象。

所以咱们的路线是：写一条 OOT 的 `drm_panel` 驱动（`panel-topeet-dsi.c`），重放 vendor 给的 init-sequence，把主线没有的那套 `simple-panel-dsi` 语义补回来。这条路线的每一步都有坑，咱们按镜像版本一道道过。

## 机制铺垫：DSI panel 的生命周期与 OF-graph

动手前先把两条主线机制画清楚，不然后面的坑看不懂。

第一条是 `drm_panel` 的生命周期。一个 DSI panel 驱动有四个回调：`prepare` / `enable` / `disable` / `unprepare`，上电时 prepare→enable、断电时 disable→unprepare。`prepare` 给 panel 上电和复位（这时 DSI 控制器还在 command mode，能可靠地发初始化命令），`enable` 是在控制器切到 video mode 之后打开显示。init-sequence 该放哪个回调——这个问题是整条 saga 最深的坑，先记住，后面会回来。

第二条是 OF-graph 显示管线。主线用设备树的 endpoint 图把 VOP2 的 video port、DSI 控制器、PHY、panel 串起来（`&dsi0_in` / `&dsi0_out` / `&vp2{endpoint}` 这一套）。vendor BSP 用的是 `&route_dsi0` / `&dsi0_in_vp2{status}` 这种 BSP-only 的简化写法，主线没有——照搬 vendor DT 不会 bind。

## 坑之一：9 条致命 gotcha（错一条，panel 静默不亮）

第一版镜像（基于 [启动章](01_boot) 末尾的 `1d972c21` 加 LCD 代码）烧上去，屏不亮，dmesg 不报错——这种「静默不亮」最难受，因为你不知道哪条错了。把驱动和 DT 落地的过程里，咱们整理出 9 条「错一条就静默」的 gotcha（完整清单见 [notes/44](../../notes/44-2026-07-31-rk3588-lcd-dsi-panel-port.md)）。这 9 条任何一条错了都是同一个症状：panel 静默不亮，dmesg 不报——所以得在写驱动和 DT 时一次性全对，不能靠「先跑起来再逐条试」。为了好记，按主题分三组说。

第一组是 DSI 控制器和 PHY 的符号、命名——这组错一个，控制器根本不 bind。DSI 控制器的 Kconfig 符号是 `ROCKCHIP_DW_MIPI_DSI2`，不是 `_DSI`：RK3588 的 dsi0 compatible 是 `rockchip,rk3588-mipi-dsi2`，由 `dw-mipi-dsi2-rockchip.c` 绑定，编成旧的 `_DSI` 不会绑 dsi0。PHY 节点主线标签是 `mipidcphy0`，vendor 写的 `mipi_dcphy0` 是 BSP-only。还有个改名坑：`MIPI_DSI_MODE_EOT_PACKET` 在主线改叫 `MIPI_DSI_MODE_NO_EOT_PACKET`，语义一样、命名取反。

第二组是 init-sequence 本身的语义——这组错一个，命令发出去桥 IC 收不懂。最反直觉的一条：init-sequence 里的类型码 `0x29` 是 `MIPI_DSI_GENERIC_LONG_WRITE`，不是 DCS；`0x39` 才是 DCS 长写。这块屏的整段 init 全是 `29 ...`，意思是给桥 IC 的寄存器做 generic 写——当 DCS 发就全错了。再一条：1024×600 这段 init-sequence 在 vendor 原文件里不以 DCS wake 命令（`05 .. 11/29`）收尾，vendor 的 `panel-simple.c` 也不自动补——桥 IC 靠自己上电自启动，别手贱给它补 wake。最后，`hfront-porch=1580` 是 vendor 原值（多半是 158 的笔误），先照抄——桥的 init-seq 是为这个 mode 配的，动 mode 要跟桥配置一起动。

第三组是接线和绑定——这组错一个，probe 卡住或拿错对象。panel 本身没有 reset GPIO，reset 靠供电 `vcc3v3_lcd_n`（gpio1 PB3）断电实现；gpio3 PC1 是触摸的 reset，别混。OF-graph 用主线的 `&dsi0_in/&dsi0_out/&vp2{endpoint}`，别用 vendor 的 `&route_dsi0`。触摸绑定是 `goodix,gt911`（vendor 的 `goodix,gt9xx` 不是主线 compatible），属性名是 `irq-gpios`/`reset-gpios`（不是 vendor 的 `touch-gpio`/`reset-gpio`）。

## 坑之二：两个 kernel.config blocker——「符号会自动 select」别信

9 条 gotcha 全对，第二版镜像还是不亮，但这次 dmesg 有线索了：`deferred probe pending`。两个 config blocker，每修一个出一版镜像，演进是这样的：

| MD5 | 改动 | 真机结果 |
|---|---|---|
| `8520c77f` | 9 gotcha 全对齐 | ✅ autoboot；❌ panel deferred（PHY 没编） |
| `69d5d278` | +`PHY_ROCKCHIP_SAMSUNG_DCPHY` | ❌ panel 仍 deferred（BACKLIGHT_PWM=m） |
| `b8d0abf3` | +`BACKLIGHT_PWM=y` | ✅ DRM 起 + panel 背光亮；⏳ 视频没出图 |

第一个 blocker 是 mipidcphy0 的驱动。dmesg 报 `failed to get mipi phy`，`grep PHY_ROCKCHIP_SAMSUNG_DCPHY .config` 是 `is not set`。mipidcphy0（compatible `rockchip,rk3588-mipi-dcphy`）的驱动是 `phy-rockchip-samsung-dcphy.c`，Kconfig 符号 `PHY_ROCKCHIP_SAMSUNG_DCPHY` 默认没开。

⚠️ 这里有个坑过咱们一阵的误判：当初规划时有人说「DSI2 host 会自动 select PHY 符号」——这是错的。DSI2 select 的是 `GENERIC_PHY_MIPI_DPHY` 框架，不是 mipidcphy0 这个具体驱动。框架编进去不等于具体 PHY 驱动编进去。

第二个 blocker 是 `BACKLIGHT_PWM`。PHY 修好后 dmesg 变成 `deferred probe pending: (reason unknown)`，`/sys/class/backlight/` 空，dmesg 一行 backlight 都没有。根因是 `CONFIG_BACKLIGHT_PWM=m`——pwm-backlight 驱动编成模块，而咱们的 rootfs 是 busybox 没 modprobe，模块永远不加载，backlight 设备永不出现，panel 卡在 `drm_panel_of_backlight()` 一直 deferred。`BACKLIGHT_CLASS_DEVICE=y`（框架）不够，得单独 `BACKLIGHT_PWM=y`（具体驱动）。

这两条共同的教训：显示链路上的每一个具体驱动符号，都得逐个 `grep .config` 确认是 `=y`，不能信「会自动 select」。busybox rootfs 无 modprobe，`=m` 等于没有。

到 `b8d0abf3` 这版，DRM 终于起来了，panel 背光亮，connector `card0-DSI-1: connected, enabled, dpms=On, mode=1024x600`。可拿噪点往 fb0 里灌——

```
head -c 2457600 /dev/urandom > /dev/fb0
```

屏还是只有背光，没有雪花。说明 DSI 的视频流根本没到桥。这是下一关，也是最深的坑。

## 坑之三：视频空白——TC358775 桥 IC 与 `.prepare` 生命周期

背光亮、connector enabled、VOP2 在扫描（debugfs 里 `crtc video_port2 active=1`）、dmesg 无报错——可像素没到屏。而且 vendor BSP 用一模一样的 mode、一模一样的 DSI 配置，是能正常显示的。这种「一切都对，就是不出图」，是整条 saga 最折磨人的一关。

排查的前半段走错了方向。咱们让一个子 agent 逐行对照了主线 DSI2 的 core/glue/PHY 驱动和 BSP，从视频模式切换序列、IPI 配置、lane rate、samsung-dcphy power_on 到 GRF 写——结论是主线跟 BSP 寄存器级功能等价，没漏寄存器。这等于排除了「驱动代码 bug」，但问题没解决。把问题凝练成一份自包含诊断文档（[document/logs/rk3588/dsi2-video-blank-diagnosis.md](../../logs/rk3588/dsi2-video-blank-diagnosis.md)）去问，才把真凶逼出来。

真凶有两层。第一层是桥 IC 的身份。那颗桥是 Toshiba TC358775/774 家族（主线 `drivers/gpu/drm/bridge/tc358775.c` 其实有它的驱动，咱们一开始没认出来）。认出桥 IC 才看懂 init-sequence 的 payload 格式：那 6 字节 payload 不是单字节寄存器，是 `[addr_lo, addr_hi, data_le32]`——小端 16-bit 寄存器地址 + 32-bit 数据。解码出来：`04 01 01 00 00 00` 是写寄存器 0x0104（PPI_STARTPPI）=1，`9C 04 31 04 00 00` 是写 0x049C（LVCFG）=0x431（single-link）。认错桥 IC，就根本看不懂自己发的序列。

第二层，也是真正的根因：init-sequence 发错的回调。咱们的 OOT 驱动原本在 `.enable` 里发 init-sequence。可 DSI2 host 在 panel 的 `.enable` 之前就已经切到 video mode 了（`dw-mipi-dsi2.c` 的 `atomic_enable`）——这时候 init 走的是 video-mode 下的 LP 注入，对 TC358775 这种桥不可靠，桥没真正初始化，视频流自然过不去。

正解是把生命周期改成跟 vendor 的 `panel-simple` 一致：init-sequence 放 `.prepare`（供电复位后、DSI2 切 video mode 前，在 command mode 里发），`.enable` 只留延时；exit-sequence 对应地从 `.disable` 挪到 `.unprepare`。改完，`370c0597` 这版镜像——

```
boot logo（企鹅）正常显示 + fb0 灌噪点花屏
```

视频管线全通。这是整条 saga 的转折点。

> 这关的三条教训值得记住。第一，DSI panel/bridge 的 init 一律放 `.prepare`，别放 `.enable`——DSI2 控制器在 enable 前已切 video mode，video-mode LP 注入对桥不可靠；vendor 的 panel-simple 也是 prepare 发，上游 RK3576 DSI2 也踩过同样的坑。第二，payload 格式别想当然，DSI generic long write 的 payload 对不同桥含义不同，TC358775 是 `[addr_lo, addr_hi, data_le32]`，认桥 IC 要看 datasheet 寄存器表。第三，「驱动代码等价」不等于「行为等价」——子 agent 证明了主线跟 BSP 寄存器级等价，可 bug 在 panel 驱动的调用阶段（上层），不在 DSI2 驱动（下层），逐行对寄存器是查不到的。

## 坑之四：VOP2 handoff 硬锁——vendor 三项语义漏（候选镜像，未定稳）

屏出图了，可另一个鬼影一直缠着：偶发的硬锁死。有时 DRM 刚接管 fbcon 就冻住，`nomodeset` 或 `fbcon=disable` 能避开，把故障域指向 VOP/DSI 的 modeset handoff。等到拿 ramoops + watchdog 抓到最早的异常，看到的不是 watchdog 栈，而是 DRM 启动阶段连续三次：

```
rockchip-drm display-subsystem: [CRTC:83:video_port2] vblank wait timed out
```

随后 CPU6 的 buddy hard-lock detector 在约 16 秒报告 CPU7 hard lock。逐项比对 vendor `rk3588s.dtsi` 和主线 VOP2 驱动，确认主线板级移植漏了 vendor 的三项硬件 handoff 语义。一是 VOP 的 ACLK 要固定 750 MHz；二是 VP2 的 `DCLK_VOP2_SRC` 要以 `PLL_V0PLL` 为父时钟；三是最容易漏的——vendor 在视频口 timing/config commit 之后，会脉冲对应的 `dclk_vpN` reset 再开 vblank。主线的基础 DTS 没有这六路 reset 描述，主线 VOP2 驱动也没去获取或脉冲 `dclk_vpN`，所以单纯把 `vp2→dsi0` 的 graph 接通，并不等价于 vendor 的硬件 handoff——于是 vblank 等不到，硬锁。

修复落在 `0009-drm-rockchip-align-RK3588-VOP2-dclk-handoff-with-BSP.patch`：板级 `&vop` 加 ACLK 750 MHz + AXI/AHB/VP0-3 DCLK resets，板级 `&vp2` 把 `DCLK_VOP2_SRC` 指到 `PLL_V0PLL`，主线 VOP2 驱动按名字获取 optional `dclk_vpN` reset、在 timing commit 后 assert 10 µs 再 deassert。这版候选镜像的 SHA 是 `2846097b…`。

> ⚠️ 这版是因果收敛后的候选，不是稳定镜像。它在源码层过了可复现门禁（从 v7.1 空树依次 `git am` 0001–0006、0009 通过；DTS/VOP2/I²C/Goodix/RK860X/FIQ 七个关键文件与构建树逐字节一致；pack→assemble round-trip 自检通过），但连续冷热启动和桌面长跑的板验还没做。首轮板验要看的是 `dmesg | grep -iE 'vblank|dclk reset|timeout|Hard LOCKUP'` 不再出现 VP2 vblank timeout。在多轮板验通过前，咱们不把它写成「稳定支持」。

> 还有两条相关的诚实账。一是 `0007`（I²C v5 auto-stop）和 `0008`（GT911 polling）这两个曾经的候选，组合镜像 `c670a208…` 已经被真机否决（启动挂死），现在故意从 series 排除，patch 文件只留作失败证据。二是 vendor reference 里正常默认屏其实是 MIPI1/FT5x06，并没有启用这块 LVDS 1024×600/GT911 路径——所以它不能当作 GT911 polling 已板验的证据。触摸这一路，咱们只保留了 GT911 的 pull-up + falling-edge 最小 IRQ 修复，触摸的完整板验等系统稳定后单独做。

## canonical：显示相关的关键配置

把这一章涉及的关键件集中放这儿：

```
# patches/rk3588-topeet/linux/
#   0001-drm-panel-topeet-dsi-driver.patch    OOT panel 驱动（prepare 发 init）
#   0002-arm64-dts-rk3588-topeet-panel.patch  板 DT（OF-graph + panel@0 + 触摸）
#   0009-drm-rockchip-align-RK3588-VOP2-dclk-handoff-with-BSP.patch  VOP handoff（候选）

# board/rk3588-topeet/kernel.config（显示相关，全 =y，别 =m）
CONFIG_ROCKCHIP_DW_MIPI_DSI2=y        # dsi0 控制器（NOT _DSI）
CONFIG_PHY_ROCKCHIP_SAMSUNG_DCPHY=y   # mipidcphy0（别信自动 select）
CONFIG_DRM_MIPI_DSI=y
CONFIG_DRM_PANEL_TOPEET_DSI=y
CONFIG_BACKLIGHT_CLASS_DEVICE=y
CONFIG_BACKLIGHT_PWM=y                # 别 =m（busybox 无 modprobe）
CONFIG_TOUCHSCREEN_GOODIX=y
```

panel 驱动的生命周期定型为：`.prepare` = 上电 + 发 init-sequence；`.enable` = 延时；`.disable` = 延时；`.unprepare` = 发 exit-sequence + 断电。init 失败要 `regulator_disable` 回滚。

## 成功长这样（与候选的诚实状态）

出图那一版（`370c0597`）的真机表现：

```
rockchip-drm display-subsystem: bound fdd90000.vop (ops vop2_component_ops)
rockchip-drm display-subsystem: bound fde20000.dsi (ops dw_mipi_dsi2_rockchip_ops)
[drm] Initialized rockchip 1.0.0 for display-subsystem on minor 0
rockchip-drm: fb0: rockchipdrmfb frame buffer device
...（企鹅 logo 显示，fb0 灌噪点花屏——视频管线通了）
```

VOP handoff 修复后的候选（`2846097b…`）在源码层过了可复现门禁，但真机稳定性板验未完。所以这一章的诚实结论是：屏能点亮、视频管线能通，但显示子系统的连续稳定性还在收敛途中。下一章咱们先把 GPU 桌面跑起来——那是另一段关于固件时机的故事。
