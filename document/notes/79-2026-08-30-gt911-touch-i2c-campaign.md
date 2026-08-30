# 79 — GT911 触摸真路径战役（一）：总线/gpio 影子成军，M0 卡在供电链（2026-08-30）

> 目标：宿主鼠标 → 影子 gt911（0x14@i2c2）→ 真 I2C → 真 goodix 驱动 → 输入子系统
> → GNOME——sim 的输入归真，virtio 键鼠退役为 cmdline 休眠备胎。弹药来自家族
> 项目 imx-forge（GT911 寄存器级模型 0008-0016 九连补丁，上游 qemu v11.1 +
> 补丁链干净复现）。

## 0. 战役状态

| 项 | 结果 |
|---|---|
| gt911 设备移植 | ✅ hw/input/gt911.c(+h)：imx-forge 终态全量搬入；INT 路由去 imx 板级硬编码（gpio0/IO9 partial-path）改为名义 GPIO out "gt911-int"；v11.1 API 对齐（event 回调返回 int、class_init const、hw/core/irq.h） |
| rk3x i2c 控制器影子 | ✅ feaa0000（i2c2）sysbus 设备 rk3588-lite-i2c2：CON/CLKDIV/MRXADDR/MRXRADDR/MTXCNT/MRXCNT/IEN/IPD/FCNT + TX@0x100/RX@0x200 FIFO；**时序关键：CON\|START 只 pend INT_START，搬运由 MTXCNT/MRXCNT 写触发**（驱动 handle_start 后才填 FIFO——fill_transmit_buf 首字节预填 i2c 地址）；REGISTER_TX 地址+寄存器字节在 START 相发出，读走 repeated start（QEMU i2c 核心原生支持） |
| gpio3 影子 | ✅ fec40000 rockchip gpio **v2 双字协议**（+0=pin0-15 半字/+4=pin16-31 半字）：dr/ddr/int_en/mask/type/polarity/bothedge/status/raw/eoi(w1c)/ext_port/ver_id；32 输入 qemu_irq + 边沿检测 → bank IRQ（SPI 280） |
| **ver_id 坑** | 🔑 初版把 V2_2 写成字节序颠倒 0xC8190201 → 唯独 gpio3 不 probe（驱动 readl 单读校验版本）。正解 `0x010219C8`。其余 bank 落全零毯区按 V1 probe 反而都活着 |
| 总线枚举 | ✅ `i2c 2-0014` client 成立（/sys/bus/i2c/devices/2-0014/name = gt911），DTB 节点直用 |
| **M0（goodix probe）** | ⛔ 卡在供电链：goodix → AVDD28 → vcc3v3_lcd0_n（已注册）→ vin → **vcc_3v3_s3 = rk806 SPI PMIC dcdc-reg8（未建模，永不注册）** → regulator 核心对 vin 未解析的 rdev 永远 -EPROBE_DEFER（devices_deferred 实证，手动 bind = EAGAIN）。这正是旧 overlay 用 /delete-property/ vin-supply 绕掉的挂账（现禁手术） |
| 次生坑 | goodix 还有 panel 供应者（vendor `panel=<&panel>` phandle，fw_devlink）——同样依赖显示链起活，与供电链同根 |

## 1. M1+ 待续

- M0 收官 = **rk806 SPI PMIC 影子**（spi@feb20000 控制器 + rk806 命令协议最小应答 →
  注册 14 轨 regulators）——这一刀同时解锁显示供电链（panel/背光），是老挂账课题本体
- M0 后按序：M1 HMP `gt911_touch x y` 注点进 GNOME；M2 宿主鼠标真路径
  （设备自带 ABS input handler——usb-tablet 机制，窗口内鼠标即触摸）；M3 退役 virtio tablet
- imx-forge 精化补丁的语义已并入终态（0x814e 读清 INT、release 即报告、
  assert 先高后低保证下降沿）

## 2. 工具与流程沉淀

- imx-forge qemu 资产复现法：`.gitmodules` 指上游 qemu + 钉死 commit 84f0721
  （v11.1.0）→ sparse fetch 该 commit → 16 连补丁顺序全绿 → 终态文件直接拷
- 内核侧规格书三件（建模即对照驱动源码）：i2c-rk3x.c（含 FIFO 首字节=地址）、
  gpio-rockchip.c（v2 双字半区 + ver_id 单读）、goodix.c + 咱们的 0005/0006
- sysfs 手动 bind 强探针：`echo 2-0014 > /sys/bus/i2c/drivers/Goodix-TS/bind`
  （注意大小写）；deferred 真因看 `/sys/kernel/debug/devices_deferred`
- initramfs busybox 无 head/tail——console 取证命令要裸 grep/cat

## 3. 现行文件清单

- third_party/qemu：hw/input/gt911.c、include/hw/input/gt911.h、
  hw/arm/rk3588-lite.c（i2c2/gpio3 影子 + 布线 + HMP 钩子 rk3588_lite_gt911()）、
  Kconfig×2/meson×2/hmp-commands.hx/hmp.h/hmp-cmds.c
- HMP：`gt911_touch x y` / `gt911_release`（M1 的注点工具，待 M0 后验收）
