# 52 RK3588 GT911 vendor polling + I²C v5 状态机候选 (2026-08-02)

接 [51](51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)。GT911 已能稳定 probe：
`ID 911, version: 1060`，且手工读取 `0x814e` 能看到 1–3 指坐标变化；但 GPIO3_C0
对应 IRQ 76 的计数始终为 0，`event0` 没有事件。因此触控芯片、I²C2、供电、复位、地址
选择和扫描均正常，故障域只剩 INT 事件路径。

## 被否决的第一版

第一版仅删除 DT 的 `interrupts`，让主线 Goodix 使用 input core 的
`system_freezable_wq` 轮询。启动后出现：

```text
rk3x-i2c fd880000.i2c: timeout, ipd: 0x1b, state: 2
rk3x-i2c fd880000.i2c: timeout, ipd: 0x10, state: 1
cpu cpu4: Failed to set regulator voltages: -110
```

`fd880000.i2c` 是 RK8602/RK8603 CPU big-cluster 调压总线，不是 GT911 所在的
`feaa0000.i2c`。持续触摸轮询暴露了调频链路中的 I²C 状态机问题；该镜像 SHA-256
`cc8e8429565014cf213fafc30426c18facf6e5af0e3f33a1441694300f9b3275` 已废弃，不能再烧。

## vendor 对照结论（板验后的纠偏）

TOPEET vendor `gt9xx.c` 的 `gtp_request_irq()` 在 IRQ 申请后强制进入失败分支，实际使用：

- 首次延迟 1 秒；
- 16 ms `hrtimer`；
- 独立单线程 `goodix_wq`；
- 每轮读坐标并向 `0x814e` 写 0 确认；
- suspend/remove 取消 timer，resume 重启。

但这只能证明 vendor **源码路径**如何实现，不能证明 reference 中的正常 vendor 镜像实际
运行过该路径。随后复核 `topeet-screen-lcds.dts` 发现当前配置为：

```c
//#define LCD_TYPE_LVDS_10_1_1024x600_GT911
#define LCD_TYPE_MIPI1
```

即 reference 正常配置启用的是 I²C3 上的 FT5x06；GT911 节点和轮询驱动并未进入该镜像。
先前把“源码存在”写成“同板正常配置已验证”是不成立的，后续不能再以此作为持续轮询安全性的
依据。

RK3588 vendor `i2c-rk3x.c` 还会识别控制器 v5，启用 `REG_CON1` auto-stop，在发送
START 前直接装载 READ/WRITE 完成中断；它没有主线当前的 `STATE_START` 等待状态。现场
`ipd=0x10,state=1` 正好是主线卡在 START pending 的状态。

## 本次实现

- `0007-i2c-rk3x-port-RK3588-vendor-v5-auto-stop-state-machi.patch`
  - v5 version detection / auto-stop；
  - data-first READ/WRITE 状态机，移除 `STATE_START`；
  - vendor 200 ms + 实际传输长度 timeout；
  - `REG_SCL_OE_DB` SCL-hold debounce；
  - 保留 0004 的双 reset-domain timeout recovery。
- `0008-input-goodix-add-TOPEET-vendor-polling-mode.patch`
  - 新增 opt-in `goodix,polling-mode`；
  - hrtimer + 独立 ordered `goodix_wq`；
  - 完整 probe/suspend/resume/remove 生命周期同步；
  - DT 保留 PC0/PC1 供 reset/address selection，但 polling 模式不申请无效 IRQ。

## 静态闸门与候选

- 从 upstream v7.1 干净树顺序 `git am` 0001–0008：通过；
- 干净树从零构建 `Image + rk3588-topeet.dtb`：通过；
- 干净树/实际构建树的 5 个关键源码及 DTB SHA-256 一致；
- 反编译 DTB 确认 `goodix,polling-mode`、PC0/PC1、电源和 panel phandle 均在；
- `update.img` RKAF+RKFW round-trip 解包：通过；
- Windows 目标文件复算 SHA-256 一致。

已否决候选：

```text
size:    3290329674 bytes
SHA-256: c670a208b5ae650fd42ed1eeb1eb22851b8d2f43ebbaa68bce33c3c189fe2e72
```

真机反馈该镜像会再次随机挂死，随后进一步确认已经无法到达 login，因此不得继续烧录或
作为基线。它同时引入 0007（全局 RK3x I²C v5 状态机）和 0008（GT911 持续轮询）；系统
无法进入用户态，原计划的运行时解绑 A/B 不可执行。在取得新 UART 日志前，不能把启动挂死
单独归因给其中任一项。0007/0008 已从 `series` 和实际源码撤出，patch 文件仅保留失败证据。

## 上板判定

```sh
dmesg | grep -iE 'Goodix|auto-stop|fd880000|cpufreq|Failed to set regulator'
grep -iE 'goodix|gt911' /proc/interrupts
timeout 15s od -An -tx1 -w24 /dev/input/event0
```

原定预期没有通过：用户确认系统再次随机挂死并且到不了 login。当前先重建已验证能启动的
0001–0006 救援基线；必须结合新的完整 ttyFIQ0 日志再决定触摸修复，不能继续生成猜测性
候选。

## 救援基线

已从实际源码撤销 0008、再撤销 0007，并把两项从 `series` 排除。随后完成：

- Linux `Image + rk3588-topeet.dtb` 重新链接；
- v7.1 临时干净树顺序重放 0001–0006；
- I²C、Goodix、RK860X、板级 DTS 等关键源码与实际构建树逐字节比较；
- FIT 重打、RKFW/RKAF assemble 与 round-trip 解包；
- 复制 Windows 固定烧录路径后重新计算 SHA-256。

救援镜像（等待本轮恢复板验，不是触摸最终修复）：

```text
size:    3290329674 bytes
SHA-256: 377cfa2639c4d6d9ef6ae665b0865142f658f71280625c04b514a1551a613e17
path:    C:\Users\CharlieChen\Assets\images\RK3588\update.img
```

## IRQ 线最终取证与板级 DTS 修复候选

在 0001–0006 路径上，GT911 能持续产生原始坐标，但 IRQ 76 始终为 0。先写 0 清除
`0x814e` 后，立即、10 ms、110 ms 和 1.1 s 四次检查均得到：

```text
GT911 status: 0x00
GPIO3_C0:      in lo IRQ
IRQ 76:        0
```

这排除了旧报告未确认、快速重新置位和单纯边沿丢失。`0x804d = 0x8d` 的低两位为 1，
控制器实际使用下降沿模式，空闲 INT 应为高。随后 pinctrl 寄存器取证给出：

```text
pin 112 (gpio3-16): input bias pull down (1 ohms), ... pin output (0 level)
```

这里 `pin output (0 level)` 是 generic pinconf 对 `PIN_CONFIG_LEVEL` 当前读值的显示文本，
不是 GPIO 方向；`debugfs/gpio` 已确认方向为 input。有效证据是 PC0 被 IOC 配成内部下拉，
它会把 Goodix INT 空闲态固定在低电平，使下降沿 IRQ 永远无法产生。vendor GT9xx 驱动也只
把 INT 切回 input，并未在 GT911 节点声明 pinctrl bias；reference 默认 FT5x06 镜像因而
不能为这条 GT911 线路提供反证。

正式候选只修改板级 DTS，不启用轮询、不修改 Goodix/I²C 全局路径：

- 新增 `gt911_int` pinctrl group：GPIO3_C0 / GPIO function / `pcfg_pull_up`；
- GT911 节点引用该 default state；
- `interrupts` 从误导性的 `IRQ_TYPE_LEVEL_LOW` 校正为控制器实际使用的
  `IRQ_TYPE_EDGE_FALLING`。

静态验证：DTB 编译通过；反编译得到 `interrupts = <0x10 0x02>` 并确认 GT911 phandle
指向 pull-up group；从干净 v7.1 顺序重放 0001–0006 后板级 DTS 与实际树逐字节一致；
RKFW/RKAF assemble round-trip 通过；Linux 与 Windows 镜像 SHA-256 一致。

新候选（等待真机验证，不能标记为稳定）：

```text
size:    3290329674 bytes
SHA-256: eca691e0f2da33de3ce57426b5805f54cf84b6429c6a86414a2fa42f74c405d9
path:    C:\Users\CharlieChen\Assets\images\RK3588\update.img
```

上板后首先验证 `pinconf-pins` 为 `input bias pull up`、GPIO3_C0 空闲为 `hi`，再触摸确认
IRQ 76 递增和 `/dev/input/event0` 出现事件。随机系统挂死仍是独立的未结案问题。

> 2026-08-02 后续：`eca691e0…` 未单独板验即被 [53](53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md)
> 的组合候选 `5f479634…` 取代；GT911 DTS 内容不变，组合镜像额外加入锁死取证和硬件
> watchdog。两版都不能在板验前标为稳定。
