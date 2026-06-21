# Ch4 — I2C/UART：RK3506 的 RMIO 交叉开关

> Ch3 是 out-of-tree 驱动，这章回到主线侧——但 RK3506 的 I2C0/1/2 和 UART2 走一个叫 RMIO 的交叉开关，主线 pinctrl 压根不认识它，得补一个驱动 patch。好在 vendor 有现成的 `rockchip_set_rmio` 可搬，逐行核对几个 gotcha 之后就能点亮。完整记录见 [notes/23](../../notes/23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md)。

## 卡点：RMIO 交叉开关

RK3506 的一部分外设功能（i2c0/1/2、uart2 走 rm_io 引脚）**不通过普通 iomux 寄存器选择**，而是过一个叫 RMIO（remappable IO）的交叉开关，这个开关藏在 PMU GRF 里。这些引脚的 mux 值**超出 iomux 寄存器自己的位宽**（func 18、30~35，都大于 4bit 的 15）。Ch1 那批 Ethernet/MMC/SPI 的引脚 func ≤ 2，不受影响；**只有 I2C/UART2 卡在 RMIO 上**。

主线 `drivers/pinctrl/pinctrl-rockchip.c` **完全没有 RMIO 支持**——`grep rockchip_set_rmio` 实证为零。所以这一档 = DT + 一个约 50 行的驱动 patch，把 vendor 的 `rockchip_set_rmio` 搬进主线。

## 两个 patch

[0007](../../../patches/linux/0007-pinctrl-rockchip-rk3506-rmio-crossbar-mux.patch) 是驱动，三处改：struct `rockchip_pinctrl` 加一个 `regmap_rmio`；probe 里 `syscon_regmap_lookup_by_phandle_optional(np, "rockchip,rmio")` 取它；新增 `rockchip_set_rmio()` 函数（vendor 那个逐字搬，加一个 NULL 守卫），并在 `rockchip_set_mux()` 顶部、verify 之后调用它。逻辑是：按 mux_type 算 iomux_max，`*mux > iomux_max` 时就算出 RMIO 功能号、写 PMU GRF 里的交叉开关寄存器，再把 `*mux` 改成 7（让 iomux 寄存器选 RMIO 功能）。`ctrl->type==RK3506` + rmio syscon 双门控，**不影响其它 SoC**。

[0008](../../../patches/linux/0008-ARM-dts-rockchip-rk3506b-aes-I2C-UART2-RMIO-GT911.patch) 是 DT：SoC 节点 i2c0/1/2（`rockchip,rk3506-i2c` + `rk3399-i2c` fallback）+ uart2（dw-apb-uart，删 dmas 走 PIO）；pinctrl 节点加 `rockchip,rmio = <&grf_pmu>`；RMIO 引脚组（从 vendor 那个一万五千行的 pinctrl-rmio.dtsi 里精简到板用的 8 个：i2c0=rm_io13/14、i2c1=rm_io24/25、i2c2=rm_io4/5、uart2=rm_io26/27）；板级 enable + i2c2 上挂 gt911@0x14。

## 几个靠读源码坐实的 gotcha

这条线有几个坑，全是靠 grep + 读源码确认、没靠猜的：

一是 `rockchip_verify_mux` **不截断 mux 值**——它只查越界/UNROUTED/GPIO_ONLY，不把 mux 限制在 iomux_max 内，所以 mux=30~35 能一路通过到我们的 `rockchip_set_rmio`。要是它截断，整条 RMIO 路径就死了，读源码确认没截才敢写。

二是 i2c 用 `rk3399-i2c` fallback 很巧妙地省事：命中 rk3399 后 `soc_data.grf_offset = -1`，probe 里 `if (grf_offset >= 0)` 为假，就**不要求 `rockchip,grf`、不要求 i2c alias**。alias 还是加了，只为 `/dev/i2c-N` 编号稳定。

三是 `rockchip,rmio = <&grf_pmu>`——RMIO 交叉开关寄存器（偏移 0x80/0x90/0xa4/0xbc）在 grf_pmu 块里，这个 phandle 指向要在 vendor `rk3502.dtsi:1470` 实证确认，不能靠 handoff 转述。

## 板验

[boot-sdl-202606191851](../../logs/boot-sdl-202606191851.txt) 里这批全通：`/sys/bus/i2c/devices/` 列出 `2-0014 i2c-0 i2c-1 i2c-2`、`/dev/i2c-0/1/2` 在、`i2cdetect -y 0/1/2` 三总线全扫完无错、`ff0c0000.serial: ttyS2 irq=35`。goodix 驱动也加载了、去试读 i2c2 上的 0x14。

> GT911 触摸这块是 deferred——goodix 读 config 寄存器 0x8140 得 `-6 (ENXIO)`，因为触摸 IC 在 LCD 排线组件上，作者手头没 LCD。这是硬件不在的预期表现，不是软件回归；i2c2 总线和 RMIO 路径本身是活的（能寻址才会试读），等 LCD 到位 0x14 应答会变成 `UU`。

## 成功长这样

I2C×3 + UART2 通过 RMIO 交叉开关全部上主线，板验通过。到这里 forge 的设备树对 net/spi/mmc/i2c/uart 全自足。最后一章我们点亮音频——codec + 数字接口 + DMA 三件套，把数字链路打通。我们 Ch5 见。
