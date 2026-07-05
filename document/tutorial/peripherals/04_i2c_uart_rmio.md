# Ch4 — I2C/UART：RK3506 的 RMIO 交叉开关

> Ch3 把主线侧的 out-of-tree 驱动收了尾，这章还是停在主线侧，但要对付一个主线 pinctrl 压根不认识的东西——RK3506 的 RMIO 交叉开关。板上的 I2C0/1/2 和 UART2 都走这个交叉开关出 pad，主线 `pinctrl-rockchip` 里 grep 不到任何 `rockchip_set_rmio` 的痕迹，所以这章的活儿就是补一段约 50 行的驱动 patch + 一坨 DT，把 vendor 那条 `rockchip_set_rmio` 搬进主线、把板用的 8 个 rm_io 引脚组写进设备树。完整记录见 [notes/23](../../notes/23-2026-06-19-peripheral-bringup-a2-rmio-i2c-uart2.md)。

## 卡点：为什么 I2C 和 UART2 卡在一个"交叉开关"上

RK3506 的引脚复用有个反直觉的设计。Ch1 那批 Ethernet / MMC / SPI 的 pad，func 值都 ≤ 2，写进 iomux 寄存器的低 4 位就完事——这是 Rockchip 的常规路径。可 I2C0/1/2 和 UART2 不一样：它们走的是另一套叫 RMIO（remappable IO）的交叉开关，藏在 PMU GRF 里，不在 iomux 寄存器的位宽内。表现在 DT 上就是这些引脚的 mux 值会**超出 iomux 寄存器的位宽**：i2c0 的 SCL/SDA 是 func 30/31，i2c1 是 32/33，i2c2 是 34/35，uart2 是 18/19——4-bit 的 iomux 寄存器最大才 15，这些值根本塞不进去。

物理上怎么回事呢？iomux 寄存器只控制 pad 跟哪个外设控制器"连"，而 RMIO 这层 crossbar 控制的是 rm_ioNN 这组 pad 上**到底是哪一个外设功能被路由过来**。所以一个 rm_io pad 想用 I2C，得先由 RMIO 交叉开关把 i2c0（或 i2c1/2）的功能号拨到这根 pad 上，再让 iomux 寄存器把 pad 切到"听 RMIO 的"那一档（也就是 mux=7）。两步都得做，少一步 pad 上就没信号。

主线 `drivers/pinctrl/pinctrl-rockchip.c` 对这套是零支持——`grep rockchip_set_rmio` 实证为空。但主线已经把 RK3506 的 bank 数据和 iomux 路径都上游化了（`regmap_ioc1`、`rk3506_pin_banks[]` 都在），缺的就是 RMIO 交叉开关这一块。所以这一档的活儿很清晰：DT 加一个 phandle + 8 个引脚组，驱动加一个 `rockchip_set_rmio()`，把 vendor 那段逻辑逐行搬过来。

## 两个 patch

[0007](../../../patches/linux/0007-pinctrl-rockchip-rk3506-rmio-crossbar-mux.patch) 是驱动 patch，三处改。先是 `struct rockchip_pinctrl` 加一个 `regmap_rmio` 字段，紧跟 `regmap_ioc1`；probe 里用 `syscon_regmap_lookup_by_phape_optional(np, "rockchip,rmio")` 取它——`_optional` 是关键，没指这个 phandle 的 SoC 直接拿到 NULL，不会因我们加了字段就把别的 SoC 搞挂。然后是新增的 `rockchip_set_rmio()`，从 vendor `:1271` 逐字搬，加一个 `if (!regmap) return -ENODEV;` 的 NULL 守卫，再在 `rockchip_set_mux()` 顶部、`rockchip_verify_mux` 之后调用它。整段函数 `ctrl->type == RK3506` + rmio syscon 双门控，**不影响任何其它 SoC**——别的 SoC 既不是 RK3506，DT 里也不会有 `rockchip,rmio`，函数进去就走 default 分支原样返回。

[0008](../../../patches/linux/0008-ARM-dts-rockchip-rk3506b-aes-I2C-UART2-RMIO-GT911.patch) 是 DT patch。SoC 级 `rk3506.dtsi` 加 i2c0/1/2（ff040000/ff050000/ff060000）和 uart2（ff0c0000，dw-apb-uart，**删 dmas 走 PIO**——Ch5 会讲为什么 vendor 那套 5-cell DMA 编码绑不上主线 pl330）；pinctrl 节点加那行关键的 `rockchip,rmio = <&grf_pmu>`；然后是 8 个 RMIO 引脚组。板级 `rk3506b-aes.dts` 把四个控制器 `status = "okay"` enable 出来，i2c2 上挂一颗 GT911 触摸（goodix 驱动，@0x14）。

## RMIO 在 DT 里长什么样

先把 pinctrl 节点那行 phandle 单独说，它是整条链的命脉：

```dts
pinctrl: pinctrl {
    rockchip,grf = <&ioc_grf>;
    rockchip,ioc1 = <&ioc1>;
    rockchip,pmu = <&ioc_pmu>;
    rockchip,rmio = <&grf_pmu>;   /* RMIO 交叉开关寄存器在 grf_pmu 里 */
    ...
};
```

这个 `<&grf_pmu>` 不能瞎指——RMIO 的交叉开关寄存器（偏移 0x80 / 0x90 / 0xa4 / 0xbc）就物理落在 grf_pmu 块（ff910000）里。指错了写出去的位置就完全不对，板上一根 I2C 都不会应答。这个指向是从 vendor `rk3502.dtsi:1470` 实证确认的，不能靠 handoff 转述——转述错一字符就是一晚上排查。

引脚组那边，从 vendor 那份一万五千行的 `rk3506-pinctrl-rmio.dtsi` 里精简到这块 AES 板真用到的 8 个：i2c0 走 rm_io13/14、i2c1 走 rm_io24/25、i2c2 走 rm_io4/5、uart2 走 rm_io26/27。看一对就够，其余都同构：

```dts
i2c0 {
    /omit-if-no-ref/
    rm_io13_i2c0_scl: rm-io13-i2c0-scl {
        /* bank0/pin13/func30(pull_none)：func30 = i2c0_scl 经 RMIO 路由 */
        rockchip,pins = <0 RK_PB5 30 &pcfg_pull_none>;
    };
    /omit-if-no-ref/
    rm_io14_i2c0_sda: rm-io14-i2c0-sda {
        rockchip,pins = <0 RK_PB6 31 &pcfg_pull_none>;
    };
};
```

`<0 RK_PB5 30 ...>` 这四元组是 bank0 / pin13（PB5 在 bank0 里就是 pin 13）/ func 30 / pcfg。func 30 这个数大于 4-bit iomux 的 15，正是触发 `rockchip_set_rmio` 走交叉开关路径的条件——`*mux > iomux_max` 就算出 `function = *mux - iomux_max`，把功能号写给 grf_pmu 的交叉开关寄存器，再把 `*mux` 改写成 7 让 iomux 寄存器选 RMIO 那一档。板上 `dtc -I dtb -O dts` 反编译 `rk3506b-aes.dtb` 逐位核对过，8 个 rmio 组的 `<bank pin func pcfg>` 三元组跟 vendor 完全一致。

板级 enable 就是几行 `status = "okay"` 加 pinctrl-0 引上面定义的组：

```dts
&i2c2 {
    status = "okay";
    pinctrl-names = "default";
    pinctrl-0 = <&rm_io4_i2c2_scl &rm_io5_i2c2_sda>;

    touchscreen@14 {
        compatible = "goodix,gt911";
        reg = <0x14>;
        interrupt-parent = <&gpio0>;
        interrupts = <RK_PA6 IRQ_TYPE_LEVEL_LOW>;
        irq-gpios = <&gpio0 RK_PA6 IRQ_TYPE_LEVEL_LOW>;
        reset-gpios = <&gpio0 RK_PA7 GPIO_ACTIVE_HIGH>;
        status = "okay";
    };
};
```

GT911 那颗触摸 IC 在 LCD 排线组件上，作者手头没 LCD，所以这颗 deferred——但 i2c2 总线和 RMIO 路径本身是活的，能寻址才会试读。

## 几个靠读源码坐实的 gotcha

这条线有几个坑，全是 grep + 读源码确认的，没靠猜。猜一次就要赌一次板上的应答对不对，划不来。

`rockchip_verify_mux` **不截断 mux 值**——它只查 `iomux_num > 3` / `IOMUX_UNROUTED` / `IOMUX_GPIO_ONLY`，不把 mux 限制在 iomux_max 内。这点读源码确认了才敢写：func 30/31/32/33/34/35 能一路通过到我们的 `rockchip_set_rmio`，整个 RMIO 路径才活。要是 verify_mux 把 mux 截到 15，我们后面那段交叉开关逻辑就永远进不去，板上一根线都点不亮，而且失败的方式是"DT 写对了、驱动加载了、就是没应答"——这种哑失败排查最费时间。

主线 `rk3506_pin_banks[]`（`pinctrl-rockchip.c:5103`）里 bank0 / bank1 全是 `IOMUX_WIDTH_4BIT`，没有 UNROUTED / GPIO_ONLY——这是 verify_mux 放行的前提。bank0 还带 `IOMUX_SOURCE_PMU`（iomux 写到 ioc_pmu），bank1 是纯 `IOMUX_WIDTH_4BIT`（iomux 写 ioc1，主线已有路径）。换句话说，主线侧 iomux 这一半早就齐了，**只差 RMIO 交叉开关这一块**，0007 补上就闭环。

i2c 那边用了 `rk3399-i2c` fallback，省了一大堆属性。`compatible = "rockchip,rk3506-i2c", "rockchip,rk3399-i2c"` 命中 rk3399 后，i2c-rk3x 驱动里 `rk3399_soc_data.grf_offset = -1`（`i2c-rk3x.c:1199`），probe 里 `if (soc_data->grf_offset >= 0)` 为假，于是**不要求 `rockchip,grf`、不要求 i2c alias**。alias 我们还是加了（i2c0/1/2），但只为 `/dev/i2c-N` 编号稳定，不是为了 probe 通过。⚠️ 这里千万别用 `rk3066` / `rk3188` / `rk1126` 这种 `grf_offset >= 0` 的 SoC 当 fallback——它们会要求每个 i2c 节点都带 `rockchip,grf` phandle + alias，否则 probe 报 `needs 'rockchip,grf' property`，又是一个哑失败。

## 板验

[boot-sdl-202606191851](../../logs/boot-sdl-202606191851.txt) 里这批全过。三层验证都跑了：probe 层 `dmesg | grep` 看到 `ff0c0000.serial: ttyS2 irq=35`（uart2）+ `Goodix-TS 2-0014`（goodix 驱动加载）——i2c adapter 注册成功时是安静的（rk3x-i2c 不打 dmesg），但 sysfs 有设备即证 probe；设备层 `/sys/bus/i2c/devices/` 列出 `2-0014 i2c-0 i2c-1 i2c-2`、`/dev/i2c-0/1/2` 都在；功能层 `i2cdetect -y 0/1/2` 三总线全扫完无错。goodix 试读 config 寄存器 0x8140 得 `-6 (ENXIO)`——这是触摸 IC 不在的预期表现，不是软件回归；等 LCD 到位 0x14 应答会变成 `UU`，那时再回头收尾触摸。

## 成功长这样

```
ff0c0000.serial: ttyS2 at MMIO 0xff0c0000 (irq = 35, base_baud = ...) is a 16550A
Goodix-TS 2-0014: i2c-core: of_i2c: registered Goodix-TS, 2-0014
...
# ls /sys/bus/i2c/devices/
2-0014  i2c-0  i2c-1  i2c-2
# i2cdetect -y 0
     0  1  2  3  ...
30: -- -- -- -- ...
# i2cdetect -y 2
     0  1  2  3  ...
50: -- -- -- 54 ...
```

I2C×3 + UART2 通过 RMIO 交叉开关全部上主线，板验通过。到这里 forge 的设备树对 net / spi / mmc / i2c / uart 全自足。最后一章我们点亮音频——codec + 数字接口 + DMA 三件套，把数字链路打通，Ch5 见。
