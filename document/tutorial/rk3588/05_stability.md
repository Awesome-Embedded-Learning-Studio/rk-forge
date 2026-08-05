# Ch5 — 稳定性调试：抓看不见的 hard-lock（方法论）

> 前四章把 RK3588 跑到了 GNOME 桌面、屏出图、GPU 起来——可一个鬼影从出图起就一直缠着：偶发的硬锁死。有时 DRM 刚接管就冻、有时跑着跑着冻，冻的时候串口连 `ttyFIQ0` 的 debugger 触发串都没反应。这一章不是「修好了」的完成态教程，是调试方法论——怎么把一个看不见报错、抓不到栈的 hard-lock 逼出来、怎么用候选镜像的板验否决错误修复。素材横跨 [notes/51](../../notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)–[56](../../notes/56-2026-08-02-rk3588-ubuntu-user-rootfs-ownership.md)。

> 诚实先说：到本章末尾，硬锁死的因果还在收敛途中——咱们把故障域缩到了 VOP2 的 modeset handoff，补了 vendor 的三项语义（[notes/54](../../notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)），但那版镜像（`2846097b…`）连续冷热启动和桌面长跑的板验还没做完。所以这一章教的是「怎么调试」，不是「已经稳定」。

## hard-lock 难在哪：fiq 无响应意味着什么

普通的 kernel 死锁，`sysrq`、`ttyFIQ0` 的 debugger 多少能给点东西。可咱们这个挂死，连 `ttyFIQ0` 输入触发串都没有响应。这本身就是一条证据。

RK3588 的 `ttyFIQ0` 按 TOPEET vendor 的方式跑在普通 IRQ 模式（内核命令行 `irqchip.gicv3_pseudo_nmi=0`），它依赖 UART IRQ 和 GIC 分发。挂死时连触发串都收不到，说明故障域已经进了下面三者之一：某 CPU 长时间关了本地中断、GIC/UART IRQ 不再投递、或者全局互锁 / 总线 / SoC 级硬锁。这条证据不能区分这三者，但它排除了「系统还能调度、只是 login 或终端卡住」这种轻量故障。

> 这条证据的用法是约束故障域，不是直接定位。咱们后面所有的调试动作，都是在这个约束下做的——既然抓不到栈，就靠「暖重启后从 ramoops 读最后一段 console」+「buddy detector 从另一颗 CPU 观察」这两条不依赖被锁 CPU 的路子。

## 取证机制：ramoops + buddy detector + 硬件 watchdog

既然挂死时抓不到栈，就得在「挂死→重启」这段路上埋点。三件套（[notes/53](../../notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)）。

第一件是 ramoops。借 vendor `rk3588-linux.dtsi` 里同一段保留内存：

```dts
reserved-memory {
    ramoops: ramoops@110000 {
        compatible = "ramoops";
        reg = <0x0 0x00110000 0x0 0x000e0000>;
        record-size = <0x00020000>;
        console-size = <0x00080000>;
    };
};
```

`CONFIG_PSTORE_RAM=y` + `CONFIG_PSTORE_CONSOLE=y`，把 panic 记录和滚动 printk 存到 `0x110000..0x1effff`。这块内存在 watchdog 触发的暖重启里能保留（断电不行，所以挂死后别急着拔电）。

第二件是 buddy hard lockup detector。arm64 开 `CONFIG_HAVE_HARDLOCKUP_DETECTOR_BUDDY`，配上 soft lockup / hung task（60s）/ workqueue stall watchdog，触发就 panic、10 秒后自动重启。buddy detector 的好处是——它由仍在运行的 CPU 检出另一颗被锁的 CPU，不依赖 pseudo-NMI（咱们要保持 vendor ttyFIQ 的 IRQ 行为，不能为抓栈开 pseudo-NMI）。它的边界也要清楚：如果所有 CPU、GIC 或整个 SoC 同时停摆，它也拿不到执行机会。

第三件是 DesignWare watchdog。Ubuntu rootfs 里固化 `RuntimeWatchdogSec=30s`，systemd 打开 RK3588 `feaf0000` 的 DW watchdog 并持续喂狗。全局停摆时约 30 秒后暖重启——这就是「挂死后别断电、等 30–45 秒」的依据。

挂死后的取证流程（[notes/53](../../notes/53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)）：

```sh
# 重启后第一时间读 pstore（别先拔电，按 reset 做暖复位）
find /sys/fs/pstore /var/lib/systemd/pstore -maxdepth 2 -type f -print
for f in /sys/fs/pstore/* /var/lib/systemd/pstore/*; do
    [ -f "$f" ] && { echo "===== $f ====="; cat "$f"; }
done
journalctl -b -1 -k --no-pager | tail -n 300
```

> 如果 45 秒后 watchdog 都没复位系统，说明硬件 watchdog 在那个冻结状态下也拿不到执行机会——这本身又是对故障域的进一步约束（朝 SoC 级硬锁靠）。如果自动重启了但 pstore 只有最后一段 printk、没有栈，说明冻结覆盖了所有能跑 detector 的 CPU/IRQ 路径。这两种「没拿到」的结果都不是白查，它们都在缩小故障域。

## 调试线一：GT911 的 IRQ 为什么永远是 0

触摸这一路是最典型的「误判链 + 候选否决」。GT911 能稳定 probe（`ID 911, version: 1060`），手工读 `0x814e` 能看到 1–3 指坐标变化，可 `IRQ 76` 的计数始终是 0、`event0` 没有事件。触控芯片、I2C2、供电、复位、地址选择、扫描都正常，故障域只剩 INT 事件路径。

第一个反应是：既然 IRQ 不来，那就轮询。这踩出了整条 saga 最大的一次否决（[notes/52](../../notes/52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)）。咱们写了一个 Goodix 的 opt-in polling 模式（hrtimer + 独立 workqueue），配上一个 I²C v5 auto-stop 的状态机改动，候选镜像 `c670a208…`。烧上去——到不了 login，启动就挂死，而且 `rk3x-i2c fd880000: timeout` 刷屏。`fd880000.i2c` 是 RK8602/RK8603 的 CPU 调压总线，不是 GT911 所在的 `feaa0000.i2c`——持续轮询把调频链路上的 I²C 状态机问题暴露了。这版镜像直接废弃，0007/0008 从 series 撤出，patch 文件只留作失败证据。

> ⚠️ 这条教训值得刻在墙上：vendor 源码里有一条实现，不等于 vendor 的正常镜像真跑过那条路径。咱们当初查 TOPEET vendor `gt9xx.c`，发现它就是用 polling（hrtimer + 独立 wq），以为「vendor 都这么做，安全」。后来复核 `topeet-screen-lcds.dts`，发现 reference 的正常配置是 `#define LCD_TYPE_MIPI1`（启用 I²C3 上的 FT5x06），GT911 节点和轮询驱动根本没进那个镜像——也就是说，「vendor 源码这么写」和「vendor 正常配置验证过这条路径」是两回事，不能拿前者当后者的证据。

退回到救援基线（`377cfa26…`，只含 0001–0006），重新审 IRQ 线。在板上对 GPIO3_C0 做寄存器级取证：写 0 清 `0x814e` 后，立即、10ms、110ms、1.1s 四次检查，都是 `GPIO3_C0: in lo, IRQ 76: 0`。空闲态应该是高（`0x804d=0x8d` 低两位为 1，下降沿模式），可实测是低。pinctrl 寄存器给出真相：

```
pin 112 (gpio3-16): input bias pull down (1 ohms)
```

PC0 被 IOC 配成了内部下拉，把 Goodix INT 的空闲态固定在低电平——下降沿永远等不到。vendor 的 GT9xx 驱动也没在 GT911 节点声明 pinctrl bias，所以 reference 默认镜像不能为这条线路反证。正解只改板级 DT，不动 Goodix / I²C 全局路径：加一个 `gt911_int` pinctrl group 把 GPIO3_C0 配成 `pcfg_pull_up`，`interrupts` 从误导性的 `LEVEL_LOW` 校正成控制器实际用的 `EDGE_FALLING`。这版（`eca691e0…`，后来和锁死取证合成 `5f479634…`）才是触摸 IRQ 的正解。

## 调试线二：GT911 的坐标为什么错位

IRQ 通了，事件来了，可触摸位置不对。这一线（[notes/55](../../notes/55-2026-08-02-rk3588-gt911-landscape-axis-fix.md)）是「五点测试法」否决错误修复的典型。

根因是 DTS 用 LCD 尺寸覆盖了 GT911 原生范围（`touchscreen-size-x=1024` / `size-y=600`）。可 GT911 配置寄存器 `0x8047` 实际返回 `60 58 02 00 04 05 8d 00`——原生 X 是 `0x0258=600`、原生 Y 是 `0x0400=1024`，原生是 600×1024，不是 1024×600。这里 600×1024 是控制器两个物理轴的数值分辨率，不代表触摸玻璃是竖屏装——输入消费端会归一化到显示区。

第一次修（`2fa62f8f…`）删了尺寸覆盖，但错误地加了 `touchscreen-swapped-x-y`。五点实测（左上/右上/右下/左下/中心）发现事件坐标沿对角线转置了——swap 生效了，但不该 swap。把五点坐标反交换，正好还原芯片原始数据：物理左右对应原生 X 0..599，物理上下对应原生 Y 0..1023，轴方向本来就是对的。此前只凭键盘区域一组事件就断言「X 对应纵轴」，是错的结论。

正解是 GT911 节点既不覆盖尺寸、也不加 swap/invert，让主线 `goodix_read_config()` 发布真实的 X 0..599 / Y 0..1023，桌面输入栈按显示尺寸归一化（`0010` patch）。

> 这一线教的是一个验收规矩：触摸坐标的对错，不能凭一组事件断，要用五点物理点击（四角 + 中心）实测。任何 swap / invert 的修复，都要过五点这一关，否则容易把「对的轴方向」改成「转置的」。

## 调试线三：VOP2 handoff 与 vblank timeout

最后一线，也是离硬锁因果最近的一条（[notes/54](../../notes/54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)）。用 ramoops + buddy detector 抓到的最早异常，不是 watchdog 栈，而是 DRM 启动阶段连续三次：

```
rockchip-drm display-subsystem: [CRTC:83:video_port2] vblank wait timed out
```

随后 CPU6 的 buddy detector 在约 16 秒报告 CPU7 hard lock。`nomodeset` 或 `fbcon=disable` 能避开早期冻结——这把故障域明确指向 VOP / DSI 的 modeset handoff。

逐项比 vendor `rk3588s.dtsi` 和主线 VOP2 驱动，确认主线漏了 vendor 的三项硬件 handoff 语义：VOP 的 ACLK 要固定 750 MHz、VP2 的 `DCLK_VOP2_SRC` 要以 `PLL_V0PLL` 为父、vendor 在 timing commit 后会脉冲对应的 `dclk_vpN` reset 再开 vblank。主线基础 DTS 没有这六路 reset 描述、主线 VOP2 驱动也没去获取或脉冲 `dclk_vpN`——所以单纯把 `vp2→dsi0` graph 接通，不等于 vendor 的硬件 handoff，vblank 等不到，硬锁。修复落在 `0009` patch（详见 [LCD 章](02_lcd#坑之四-vop2-handoff-硬锁-vendor-三项语义漏候选镜像-未定稳)）。

## 镜像演进与候选纪律

这条 saga 烧了至少七个镜像，每一个都有 SHA 记录、有否决理由。把它们列出来，是为了说清楚「候选镜像」这个工作纪律：

| 镜像 SHA | 内容 | 结局 |
|---|---|---|
| `c670a208` | 0007(I²C v5) + 0008(GT911 polling) | ❌ 启动挂死到不了 login，废弃 |
| `377cfa26` | 救援基线（撤 0007/0008，只留 0001–0006） | ✅ 能启动，作为后续候选的基线 |
| `eca691e0` | +GT911 pull-up + falling-edge DTS | → 被 53 组合取代 |
| `5f479634` | +ramoops/watchdog 取证 + GT911 DTS | 待板验（锁死取证候选） |
| `2fa62f8f` | GT911 swap-x-y | ❌ 五点板验否定（对角线转置） |
| `af26a389` | 无 swap GT911（正解） | → 被 56 取代（缺桌面用户） |
| `2846097b` | +VOP2 handoff（0009） | 候选，稳定性板验未完 |

> 纪律是这样的：每一版镜像都过一道静态门禁（从 v7.1 干净树 `git am` patch 通过、关键源码与构建树逐字节一致、DTB 反编译确认、RKAF/RKFW round-trip 自检），但静态门禁过了不等于板验过——`c670a208` 静态全绿，真机到不了 login。所以「源码层正确」和「板上行为正确」之间，必须有一道真机板验，没过的镜像只能叫「候选」，不能叫「稳定」。咱们全程没把任何一版候选写成「稳定支持」，就是这个规矩。

## 当前状态（诚实账）

到这一章写完时，硬锁死的因果收敛到了 VOP2 handoff（`0009`），但它和 GT911 的最终板验都没闭环。`2846097b…`（VOP2 handoff）和 `5f479634…`（锁死取证 + GT911）都是待烧候选，首轮板验要看 `dmesg | grep -iE 'vblank|dclk reset|timeout|Hard LOCKUP'` 不再出现 VP2 vblank timeout、连续多轮启动和桌面运行无硬锁。

> 还有一条诚实的自我纠偏：[notes/51](../../notes/51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md) 曾一度认为挂死是 `fan53555` 错绑 RK8602/RK8603 调压器 + I²C 超时，移植了 vendor `rk860x-regulator` + 双 reset domain 当结论——后来发现仍有间歇挂死，稳定结论撤回。这也是调试 saga 的一部分：把一个看着像真凶的东西（RK860X）修了，挂死减轻但没消失，说明它不是唯一因。这条教训和本章的主题一致——hard-lock 的因果往往不是单一的，每修一处都要重新评估「还挂不挂」，别急着宣布解决。

所以这一章的 takeaway 不是「RK3588 稳定了」，而是：抓 hard-lock 靠 ramoops + buddy + watchdog 这套不依赖被锁 CPU 的取证机制；否决错误修复靠「源码存在≠板验」+「五点实测」+「静态门禁过后还要真机板验」这三条纪律。稳定性那一刀，等连续板验通过后再回来把这一章的状态从「候选」改成「稳定」。
