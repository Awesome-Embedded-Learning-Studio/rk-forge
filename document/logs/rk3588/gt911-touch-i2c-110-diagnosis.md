# RK3588 mainline goodix (GT911) 触摸：probe 读 0x8140 超时 -110 — 诊断交接

> 自包含，给 AI 诊断。GT911 触摸：芯片在、i2c 总线通、手动能读 ID，但 mainline goodix 驱动 probe 时 reset 后读寄存器 -110。两次假设（polarity、rst→input）都错了。

## 2026-08-01 纠偏：先恢复稳定启动基线

追加 200 ms、复位后把 RST 改 input、以及删掉 `irq-gpios`/`reset-gpios` 都不是可接受的最终修复，现已停止沿这些方向继续试。删 GPIO 但保留 `interrupts` 仍会让驱动在 probe 成功后注册触摸 IRQ，不能作为安全隔离。

新一次挂死前出现：

```
cpu cpu4: _set_opp_voltage: failed to set voltage (987500 987500 1000000 mV): -110
cpu cpu4: Failed to set regulator voltages: -110
cpufreq: __target_index: Failed to change cpu frequency: -110
```

这里的 987500 uV 对应 A76 big0 在 2.208 GHz 的 OPP。CPU4 的 `vdd_cpu_big0_s0` 是 i2c0 上的 RK8602@0x42；GT911 是 i2c2@0x14。错误表示 RK8602 调压所需的 I2C 事务超时，不等于 OPP 电压值或 CPU supply phandle 配错。两个独立 I2C 控制器先后出现 `-110` 后，必须先排除触摸 IRQ/系统卡死造成的连带超时；仅凭这三行还不能确定因果。

当前恢复基线：

- `goodix.c` 恢复主线原样，移除板级全局 200 ms 延时；
- DT 恢复 `irq-gpios`，并按主线 Goodix 驱动实际的 0→1 物理复位序列使用 `reset-gpios = <... GPIO_ACTIVE_HIGH>`；
- `touchscreen@14` 暂设 `status = "disabled"`，确保不 probe、不复位、不注册 IRQ；
- 不修改 CPU OPP、RK8602 或 cpufreq，先做单变量启动验证。

判定标准：若此基线不再出现 CPU4/RK8602 `-110`，再单独设计无 IRQ 的触摸读测试；若仍出现，则 GT911 与挂死无关，转查 i2c0/RK8602 的 IRQ、SCL/SDA 和供电。

## 一句话问题

RK3588 + 主线 Linux 7.1，GT911 触摸 on i2c-2 @ 0x14。**i2cdetect 见芯片在 0x14，i2ctransfer 能读到 product-id "911"，但 mainline goodix 驱动 probe 时读 0x8140 超时 -110**。芯片好的，驱动 reset+读序列有问题。

## 硬件 / 软件

- 板：iTOP-RK3588（topeet）。触摸：GT911，i2c-2 @ 0x14，INT=rk gpio3 PC0，RESET=rk gpio3 PC1。
- 内核：主线 Linux 7.1.0，驱动 `drivers/input/touchscreen/goodix.c`（mainline），i2c 控制器 `rk3x-i2c`。
- DT（自写，照 vendor）：
  ```
  &i2c2 { status="okay"; pinctrl-0=<&i2c2m4_xfer>;  /* m4 mux，跟 vendor 一致 */
    touchscreen@14 { compatible="goodix,gt911"; reg=<0x14>;
      interrupt-parent=<&gpio3>; interrupts=<RK_PC0 IRQ_TYPE_LEVEL_LOW>;
      irq-gpios=<&gpio3 RK_PC0 GPIO_ACTIVE_HIGH>;
      reset-gpios=<&gpio3 RK_PC1 GPIO_ACTIVE_HIGH>;  /* 见下：ACTIVE_LOW/High 都试过 */
      touchscreen-size-x=<1024>; touchscreen-size-y=<600>; }; };
  ```

## 关键证据（决定性）

1. **i2cdetect -y 2**：i2c-2 上 `0x14` 有响应（+ 一个 0x0f 别的设备）。→ 芯片在、i2c2 总线通、地址 0x14 对。
2. **i2ctransfer -y 2 w2@0x14 0x81 0x40 r6** → `0x39 0x31 0x31 0x00 0x60 0x10` = ASCII **"911"**（GT911 product-id）。→ **芯片能读**（正确的 16-bit 寄存器协议：写 2 字节 reg-addr，再读 N 字节）。
3. 但 i2cdetect/i2ctransfer 是**驱动 probe 失败放弃后**（devm 释放 GPIO）跑的。驱动 probe 时（reset 后 ~60ms 读）→ **-110 ETIMEDOUT**。

dmesg（每次 boot 必现）：
```
Goodix-TS 2-0014: supply AVDD28 not found, using dummy regulator
Goodix-TS 2-0014: supply VDDIO not found, using dummy regulator
Goodix-TS 2-0014: Error reading 1 bytes from 0x8140: -110   /* t=3.65s */
Goodix-TS 2-0014: Error reading 1 bytes from 0x8140: -110   /* t=4.7s, retry */
Goodix-TS 2-0014: I2C communication failure: -110
Goodix-TS 2-0014: probe with driver Goodix-TS failed with error -110
```

## mainline goodix 的 reset+读 序列（probe 流程）

`goodix_reset_no_int_sync`（复位 + 选 i2c 地址）：
1. `gpiod_direction_output(rst, 0)` — rst=0
2. `msleep(20)`
3. `goodix_irq_direction_output(ts, addr==0x14)` — INT=1（选 0x14）
4. `usleep_range(100,2000)`
5. `gpiod_direction_output(rst, 1)` — rst=1（释放，latch 地址）—— **rst 一直是 OUTPUT**
6. `usleep_range(6000,10000)` — T4: 6-10ms

`goodix_int_sync`（复位后 INT sync）：
7. `goodix_irq_direction_output(ts, 0)` — INT 拉低
8. `msleep(50)` — T5: 50ms
9. `goodix_irq_direction_input(ts)` — **INT 切回 input** ✓

probe：`goodix_reset()`（= 1-9）→ `goodix_i2c_read(0x8140)`（读 ID）→ -110。

`goodix_i2c_read` 用 2 个 i2c_msg（write reg-addr + I2C_M_RD read），跟 `i2ctransfer w2@ rN` 协议一致。

## 已排除 + 两次失败假设

1. **DT 配置全等 vendor**：i2c2、m4 mux、0x14、gpio3 PC0/PC1 都跟 vendor `topeet-screen-lcds.dts` 一致。vendor BSP 能点亮。
2. **reset-gpios polarity ACTIVE_LOW → ACTIVE_HIGH**：mainline 用 gpiod（按 polarity 翻），vendor 用 raw gpio。ACTIVE_HIGH 跟 vendor raw 等价（rst=0→LOW assert，rst=1→HIGH release）。**改了仍 -110**。
3. **rst 复位后切 input**（照 vendor `gtp_reset_guitar` 末尾的 `gpio_direction_input(rst_pin)`）：mainline 一直保持 rst OUTPUT。**改成 input 后仍 -110，而且引入挂死**（rst 浮空无 pull → GT911 reset 不稳 → 死扛 SDA → i2c 卡 → RCU stall，systemd-udevd 卡死）。已 revert。

## 关键矛盾

- i2ctransfer（**不复位**，芯片已 settle）→ 读成功。
- 驱动（**复位后 ~60ms** 读）→ -110。
- int_sync 已正确把 INT 切回 input；rst 驱动 HIGH（释放）。GPIO 状态看起来都对。

## 嫌疑（未定）

1. **时序**：GT911 复位后固件 reboot 可能需要更久，但单纯在 `goodix_reset()` 末尾追加 200 ms 未形成有效修复，且会污染所有使用该主线驱动的设备；当前已撤销。
2. **复位序列本身把芯片搞进不可读状态**（不是单纯时序）——但序列跟 vendor 一致，且 vendor 能点亮。
3. rk3x-i2c 驱动跟 goodix 的 i2c_transfer 有 quirk（但 i2ctransfer 走同一 adapter 能读，不太像）。

## 想问的

1. mainline goodix 驱动 probe 读 GT911 0x8140 必 -110，但 i2ctransfer（驱动放弃后）能读到 "911"——**最可能的原因是时序（复位后读太早）还是复位序列本身？** 有没有已知的 mainline goodix + rk3x-i2c / GT911 的这类坑？
2. vendor `gtp_reset_guitar`（gt9xx.c）跟 mainline `goodix_reset` 序列几乎一样（唯一结构差：vendor 末尾 rst→input，mainline 不——但 rst→input 试过反而挂死）。**还有哪步 vendor 做了 mainline 没做？**（vendor 复位后到读 ID 之间有没有别的 delay/步骤？）
3. 最有效的验证/修法？加 msleep 够吗，还是要改 reset 序列、或用别的方式读 ID（绕过驱动 reset）？

## 关键文件

- mainline 驱动：`drivers/input/touchscreen/goodix.c`（`goodix_reset_no_int_sync` L775、`goodix_int_sync` L749、`goodix_reset` L811、`goodix_i2c_read` L171、probe 读 ID L1083）
- vendor 驱动：`reference/rk3588/kernel/drivers/input/touchscreen/gt9xx/gt9xx.c`（`gtp_reset_guitar` L1110）
- DT：`arch/arm64/boot/dts/rockchip/rk3588-topeet.dts`（&i2c2 touchscreen@14）
