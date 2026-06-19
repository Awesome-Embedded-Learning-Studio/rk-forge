# 23 — A2 外设 bring-up：I2C×3 + UART2 via RMIO 交叉开关（2026-06-19）

> **✅ 核心板验通过（2026-06-19 晚，`boot-sdl-202606191851.txt`）**：i2c0/1/2 + uart2 通过 RK3506 **RMIO 交叉开关**全部上主线。板上证据：`/sys/bus/i2c/devices/` = `2-0014 i2c-0 i2c-1 i2c-2`、`/dev/i2c-0/1/2` 在、`i2cdetect -y 0/1/2` 三总线全扫完无错、`ff0c0000.serial: ttyS2 irq=35`、goodix 驱动加载并试读 i2c2 上 0x14。**RMIO 驱动（0007）+ DT（0008）端到端打通**。内核版本串 `7.1.0-00008-g8af1a2739519` 确认跑的就是 0008 commit。
>
> **GT911 触摸 deferred**：用户手头无 LCD，goodix 读 config 寄存器 0x8140 得 `-6 (ENXIO)` → `I2C communication failure`。这是**硬件不在**的预期表现（触摸 IC 在 LCD 排线组件上），**不是软件回归**。有 LCD 时 0x14 应答会显示 `UU`。i2c2 总线本身 + RMIO 路径已证活动（能寻址才会试读）。

## 卡点：RK3506 的 RMIO（remappable IO）交叉开关

RK3506 的部分外设功能（i2c0/1/2、uart2 走 rm_io 引脚）**不通过普通 iomux 寄存器选择**，而是过一个叫 RMIO 的交叉开关（在 PMU GRF 里）。这些引脚的 mux 值**超出 iomux 寄存器自己的位宽**（func 18/30~35，>4bit 的 15）。Ethernet/MMC/SPI 的引脚 func ≤ 2（A1 那批），不受影响；**只有 I2C/UART2 卡在 RMIO 上**。

主线 `drivers/pinctrl/pinctrl-rockchip.c` **完全没有 RMIO 支持**（grep `rockchip_set_rmio` 实证为零）。所以 A2 = DT + 一个 ~50 行驱动 patch，把 vendor 的 `rockchip_set_rmio` 搬进主线。

## 两个 patch

**0007 `pinctrl: rockchip: RK3506 RMIO crossbar mux`（驱动，commit `18adb264a`）**——三处改：
1. `pinctrl-rockchip.h`：`struct rockchip_pinctrl` 加 `struct regmap *regmap_rmio;`（紧跟 `regmap_ioc1`）。
2. `pinctrl-rockchip.c` probe：`info->regmap_rmio = syscon_regmap_lookup_by_phandle_optional(np, "rockchip,rmio");`（紧跟 ioc1 lookup，~4506 行）。
3. `pinctrl-rockchip.c`：新增 `rockchip_set_rmio()` 函数（vendor `:1271` 逐字搬，加一个 `if (!regmap) return -ENODEV;` NULL 守卫），并在 `rockchip_set_mux()` 顶部 `rockchip_verify_mux` 之后、regmap 选择之前调用 `rockchip_set_rmio(bank, pin, &mux)`。

`rockchip_set_rmio` 的逻辑：按 mux_type 算 `iomux_max`（4bit=15/3bit=7/2bit=3）；`*mux > iomux_max` 时 `function = *mux - iomux_max`，写 RMIO 交叉开关寄存器（bank0: `0x80+4*pin`；bank1: pin9-11→`0xbc+4*pin`、pin18-19→`0xa4+4*pin`、pin25-27→`0x90+4*pin`），`data=0x7f0000|function`、`rmask=0x7f007f`，然后把 `*mux` 改成 7（iomux 寄存器选 RMIO 功能）。`ctrl->type==RK3506` + rmio syscon 双门控，**不影响其它 SoC**。

**0008 `ARM: dts: rk3506b-aes: I2C0/1/2 + UART2(RMIO) + GT911`（DT，commit `8af1a2739`）**——`rk3506.dtsi` + `rk3506b-aes.dts`：
- SoC 节点：`i2c0/1/2`（ff04/05/060000，`rockchip,rk3506-i2c`+`rk3399-i2c` fallback）+ `uart2`（ff0c0000，dw-apb-uart，**删 dmas 走 PIO**）。
- pinctrl 节点加 `rockchip,rmio = <&grf_pmu>;`（主线原本只有 grf/ioc1/pmu 三件套）。
- RMIO 引脚组（从 vendor `rk3506-pinctrl-rmio.dtsi` 15787 行里精简到板用的 8 个）：i2c0=rm_io13/14、i2c1=rm_io24/25、i2c2=rm_io4/5、uart2=rm_io26/27。
- 板级 `&i2c0/1/2/&uart2{status=okay}` + i2c2 上挂 gt911@0x14。
- `kernel.config` 加 `CONFIG_TOUCHSCREEN_GOODIX=y`。

## 解决的关键 gotcha（翻车时回查这几条，都靠 grep/读源码坐实，没靠猜）

1. **`rockchip_verify_mux` 不截断 mux 值**。它只查 `iomux_num>3 / IOMUX_UNROUTED / IOMUX_GPIO_ONLY`，**不把 mux 限制在 iomux_max 内**。所以 mux=30/31/32/33/34/35 能一路通过到 `rockchip_set_rmio`。如果它截断，整个 RMIO 路径就死了——读源码确认没截，才敢写。

2. **主线 `rk3506_pin_banks[]`（pinctrl-rockchip.c:5103）bank0/bank1 全是 `IOMUX_WIDTH_4BIT`，没有 UNROUTED/GPIO_ONLY**。这是 verify_mux 放行的前提。bank0 是 `IOMUX_WIDTH_4BIT|IOMUX_SOURCE_PMU`（iomux 写 ioc_pmu），bank1 是纯 `IOMUX_WIDTH_4BIT`（iomux 写 ioc1，主线已有路径）。所以**只差 RMIO 交叉开关这一块**，0007 补上即闭环。

3. **`rockchip,rmio = <&grf_pmu>`**（`rk3502.dtsi:1470` 实证）。RMIO 交叉开关寄存器（偏移 0x80/0x90/0xa4/0xbc）在 grf_pmu 块（ff910000）里。主线 rk3506.dtsi 已有 `grf_pmu` 标签，pinctrl 节点加这个 phandle 即可。

4. **i2c 用 rk3399 fallback 巧妙省事**：`compatible = "rockchip,rk3506-i2c","rockchip,rk3399-i2c"` → i2c-rk3x 命中 rk3399 → `rk3399_soc_data.grf_offset = -1`（i2c-rk3x.c:1199）→ probe 里 `if (soc_data->grf_offset >= 0)` 为假 → **不要求 `rockchip,grf`、不要求 i2c alias**。alias（i2c0/1/2）还是加了，只为 `/dev/i2c-N` 编号稳定。若用了 grf_offset≥0 的 SoC fallback（如 rk3066/rk3188/rk1126），就得给每个 i2c 节点加 `rockchip,grf` + alias，否则 probe 报 "needs 'rockchip,grf' property"。

5. **dtb 反编译逐位核对**：`dtc -I dtb -O dts` 反编译 `rk3506b-aes.dtb`，确认 8 个 rmio 组的 `<bank pin func pcfg>` 三元组跟 vendor 完全一致（如 rm-io13-i2c0-scl = `<0x00 0x0d 0x1e 0x2d>` = bank0/pin13/func30/pcfg_pull_none）。`/omit-if-no-ref` 语义下，被 pinctrl-0 引用的组会保留——反编译确认都在。

## 板验三层（boot-sdl-202606191851.txt）

- **T1 probe**：`dmesg | grep` → `ff0c0000.serial: ttyS2`（uart2）+ `Goodix-TS 2-0014`（goodix 驱动）。i2c adapter 注册无独立 dmesg 行（rk3x-i2c 成功时安静），但 sysfs 有设备即证 probe。
- **T2 设备**：`/sys/bus/i2c/devices/` = `2-0014 i2c-0 i2c-1 i2c-2`；`/dev/i2c-0/1/2`。
- **T3 功能**：`i2cdetect -y 0/1/2` 三总线全扫完无错（i2c0/1 无器件空扫=正常）。goodix 试读 0x8140 → -6（无 LCD）。

## 方法论
- **判主线有没有某功能，grep 函数名/字段名而非凭记忆**。记忆说"主线零 RMIO 支持"是写时的快照；这次我 grep `rockchip_set_rmio` 实证确认函数不在、但 `regmap_ioc1`/RK3506 bank 数据**在**（上游化带进来的）。`regmap_rmio` 字段/lookup 不在 → 正好是我要加的。
- **驱动 probe 的强依赖要读源码门控条件**（`if (grf_offset >= 0)`），别假设"加了 compatible 就 probe"。rk3399 fallback 的 `-1` 省了一堆属性，是查出来的不是猜的。
- **vendor DT 的 phandle 指向要溯源**（`rockchip,rmio=<&grf_pmu>` 在 rk3502.dtsi:1470 实证，不靠 handoff 转述）。

## 现状 + 后续
- A1（Ethernet双口 + SPI + MMC/SD）+ A2（I2C×3 + UART2 + RMIO）**均板上验通**。forge DT 对 net/spi/mmc/i2c/uart 自足。
- **deferred**：GT911 触摸（等 LCD）、uart2 回显（等接线）——硬件 gated，不阻塞。
- next = **B（USB + USB2PHY）**：主线 `phy-rockchip-inno-usb2.c` 缺 rk3506 of_match，需补 USB2PHY 驱动 patch + USB DT。或 **E（Audio）**：主线 `rockchip_sai.c` 已在但 of_match 缺 rk3506 + DMA 硬骨头。
- 接线参考源：vendor `rk3506-pinctrl-rmio.dtsi` + `rk3502.dtsi` + `rk3506b-alientek.dtsi` + `rk3506-evb1-v10.dtsi`。
