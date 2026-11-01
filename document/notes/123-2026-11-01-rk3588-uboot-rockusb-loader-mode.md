# 123 — RK3588 U-Boot rockusb（Loader 模式）启用 + reboot loader 复活（2026-11-01）

> 背景：烧录迭代要走 vendor 的 Loader 模式（rockusb）。用户预研结论（全链核实）：
> 主线 U-Boot 自带完整 rockusb 实现，咱们只是没打开。本文记录把预研落成补丁、
> 以及路上踩的三颗雷（一颗是 Kconfig 交互坑，两颗是自己的工艺坑）。
> 板侧验证 hardware-gated，待一次烧录。

## 0. 结论

| 项 | 结果 |
|---|---|
| u-boot series | 3 → 6：0004 defconfig（gadget 五行+FASTBOOT 关+BOOT_MODE_REG）、0005 dtsi OTG peripheral、0006 BOOT_LOADER case |
| 内核 series | +0035：topeet dts 增 `pmu0_grf@fd588000` + reboot-mode 节点（reboot loader 的内核侧另一半）；kernel.config +`SYSCON_REBOOT_MODE=y` |
| 重放/构建 | u-boot 6/6（`5ca1a73c → bbfc9f83`）、linux 20/20 全绿；u-boot.dtb `usb@fc000000` = peripheral/high-speed/okay 实证 |
| 产物 | out/: u-boot.itb（含 rockusb，版本串 `…gbbfc9f83`）+ idbloader.img（23:27 新鲜）+ boot.img 顺手重包成 v7.3.1 内核 FIT |
| 板验 | **通过（2026-11-01 深夜，用户确认）**：Loader 模式链路（烧录→rockusb→reboot loader）成活 |

## 1. 三个补丁的决策记录

**0004（defconfig）**：`USB_GADGET/USB_GADGET_DOWNLOAD/USB_FUNCTION_ROCKUSB/
CMD_ROCKUSB/CMD_USB_MASS_STORAGE` 五行 = generic-rk3588_defconfig 的 gadget delta
（用户已对照核实，同 SoC 现成模板）。外加 `CONFIG_ROCKCHIP_BOOT_MODE_REG=0xfd588080`
——这是隐藏最深的先决条件：**该符号默认 0，而 0 会把 `setup_boot_mode()` 整个编译成
空壳**（boot_mode.c 头部 `#if (CONFIG_ROCKCHIP_BOOT_MODE_REG == 0)`），主线 rk3588
板（jaguar/tiger）全是显式 `=0x0`——FASTBOOT/UMS 的 case 一直都在，只是没人开过门。
0xfd588080 取自 vendor rk3588_defconfig（reference/rk3588/u-boot/configs/:174）。

**0005（dtsi）**：`rk3588-evb1-v10-u-boot.dtsi` 追加 `&usb_host0_xhci
{dr_mode="peripheral"; maximum-speed="high-speed"; phys=<&u2phy0_otg>}`，照抄
u-boot 原生 rk3588-generic.dts 的形态。组合 usbdp PHY 无外设态支持，gadget 走 USB2
OTG phy 封顶 high-speed——与 maskrom 烧录同一个口同一根线。上游 evb dts 本来就
`dr_mode="otg"` 使能，dwc3-generic 会在 gadget 启动时绑成 peripheral。

**0006（boot_mode.c）**：switch 里 FASTBOOT/UMS case 原生在，BOOT_LOADER 被砍。
照邻居形态补 `case BOOT_LOADER: env_set("preboot", "setenv preboot; rockusb 0 mmc 0")`。
`BOOT_LOADER`（=REBOOT_FLAG+1）在主线 `asm/arch-rockchip/boot_mode.h` 里还活着。

## 2. 内核侧（0035）——为什么必须自己补节点

主线 `rk3588-base.dtsi` **没有** fd588000 的节点（只有 pmu1grf@fd58a000），也没有任何
reboot-mode。vendor 侧原型（rk3588s.dtsi:2706）：`pmu0_grf: syscon@fd588000` +
子节点 `reboot-mode {offset=<0x80>; mode-loader=<BOOT_BL_DOWNLOAD>; …}`，
0xfd588000+0x80 = **0xfd588080**，与 u-boot 读的寄存器严丝合缝（三方对齐：vendor
u-boot 常量 = vendor dts 节点 = 我们的 0004/0035 组合）。

主线 dt-binding 头（`rockchip,boot-mode.h`）有 REBOOT_FLAG/NORMAL/BL_DOWNLOAD/
RECOVERY/FASTBOOT，**没有 BOOT_UMS** → `mode-ums = <0x5242C30C>`（REBOOT_FLAG+12，
u-boot boot_mode.h 的值）字面量 + 注释。

## 3. 三颗雷（按杀伤力排序）

**雷 1（Kconfig 交互）**：`USB_GADGET_DOWNLOAD` 一开，`USB_FUNCTION_FASTBOOT` 默认
翻 y，拖出**无默认值**的 hex `FASTBOOT_BUF_ADDR` → syncconfig 停下等人工输入 →
后台任务 stdin 空管道 → **静默挂死**（主 make 8 分钟 CPU 时间为零；产物时间戳不动
是铁证）。generic defconfig 里那行 `# CONFIG_USB_FUNCTION_FASTBOOT is not set` 不是
注释，是功能行——「配置差 5 行」实为 6 行。修法：补上该行。**教训：后台构建挂死先查
`ps -o time`，再看 syncconfig/oldconfig 类进程，八成是交互提问。**

**雷 2（hunk 计数）**：手改补丁加行后忘了同步 `@@ -26,6 +30,15 @@` 的新侧行数
（15→18），git am 按声明行数校验 hunk 体 → 「补丁损坏」拒收。手织 hunk 时行数
头是内容的一部分。

**雷 3（管道吃退出码）**：`cli.py apply … | tail && cli.py build …`——`&&` 判的是
tail 的退出码。apply 失败回滚后 build 照跑，**在裸树上编出了香草 u-boot**，差点当成
rockusb 版交付。修法：`> log 2>&1; rc=$?` 显式判。**教训：forge CLI 的失败语义
（log.die→SystemExit(1)）是真实可靠的，但别用管道把它埋了。**

**顺带**：builder 把产物留在树内，进 out/ 是 `forge pack fit` 的职责——「build 完了
out/ 怎么没变」不是 bug，是漏跑 pack。这次 pack fit 还顺手把 boot.img 重包成了 v7.3.1
内核 FIT（fit-pack 从 linux 树取件）。

## 4. 板侧验证剧本（hardware-gated）

一次烧录（新 u-boot 必须先进板；用现 maskrom 流程或 update.img）：

```
# 串口 u-boot 提示符：
rockusb 0 mmc 0          # → PC: lsusb 见 2207:350b（RKXUSB rockusb）
# PC 侧（rkdeveloptool）：
rkdeveloptool ld         # 应列出 Maskrom/Loader 设备
rkdeveloptool wl 64 out/rk3588-topeet/idbloader.img      # LBA 64
rkdeveloptool wl 16384 out/rk3588-topeet/u-boot.itb     # LBA 16384
# 全盘镜像走 wlx <分区名>，rootfs.ext4 按名写
```

`reboot loader`（P2）触发路径：板上 Linux → reboot(2) RESTART2 参数 "loader" →
syscon-reboot-mode 写 0xfd588080 ← BOOT_BL_DOWNLOAD 魔数 → u-boot preboot =
`rockusb 0 mmc 0`。**userspace 注意**：systemctl/busybox 的 reboot 都不透传 mode
字符串，用裸系统调用一行流（板上 Python 即可）：

```python
# RESTART2 = 0xa1b2c3d4, arg = "loader"
import ctypes; libc = ctypes.CDLL(None)
libc.reboot(ctypes.c_int(0xfee1dead), ctypes.c_int(672274793),
            ctypes.c_int(0xa1b2c3d4), ctypes.c_char_p(b"loader"))
```

（fallback：`devmem 0xfd588080 32 0x5242C301` 后普通 reboot——直接写寄存器，
不依赖 0035。）

## 5. P3（按键进下载）未做——且按键≠Loader，实测定性

板上「Loader/Recovery 开关」的检测点**不在 u-boot**：我们这条链的 TPL 是 vendor
ddrbin blob，按键检测内置其中，命中即跳 `BOOT_BROM_DOWNLOAD` → **maskrom**（板测
实锤：摁键第一反应就是 maskrom；与 ddrbin 逆向结论互证）。u-boot 侧的
`rockchip_dnl_mode_check()`（需 CONFIG_ADC）即便做了，写的也是 BOOT_BROM_DOWNLOAD
——**还是 maskrom，不是 Loader**。

结论：主线栈上「按键 → Loader」天然无路。vendor 板子的按键体验是 vendor u-boot
开了 ADC 检测后自己加戏。真要做按键进 Loader：u-boot 开 CONFIG_ADC + 板级 hook
把 `rockchip_dnl_key_pressed()` 命中后的去向从 dnl(maskrom) 改写成 BOOT_LOADER
（走 preboot=rockusb 那条管线）——P3 加强版，价值有限（maskrom 烧录 + P2 reboot
loader 已覆盖），留档不实施。

**Loader 的真实入口只有两条**：串口 `rockusb 0 mmc 0`；`reboot loader`（RESTART2，
需新 u-boot + 0035 内核节点都在板上）。

## 6. 遗留

- 板验全链（§4）+ TFTP+NFS 起机（notes/122 §5）——同一次串口会话可全验
- out/ 的 update.img 还是旧装配（u-boot/boot.img 已新，assemble 未跑）——TFTP 验证
  通过后按需 `forge assemble`
- 0004 补丁头 diffstat 行数（13）与实际（16）有 3 行偏差——git am 只认 diff 体，
  已验证不影响应用；下次 format-patch 重出时自然修正

取证：/tmp/ubuild3.log（成功轮）、u-boot.dtb fdtget 输出（§0）、
vendor 对照 reference/rk3588/{u-boot,kernel}/。关联 notes/117（直连网络层）、
notes/122（v7.3.1 rebase 同日同链）。
