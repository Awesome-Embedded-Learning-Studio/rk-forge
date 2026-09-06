# 60 — rk3568-lite QEMU 机器首启全记录（2026-08-25）

> Day 0 绿灯（[59 号笔记](59-2026-08-24-rk3568-qemu-sim-m0-day0.md)）次日，QEMU 骨架从零写到
> **4×A55 全核跑到 busybox shell**。195 行机器文件排掉四个真 bug，每个都有实锤链。
> 计划里 Day 1-5 的活一天走完——「-kernel 直载内核跳过整段 bootloader」省掉了 M2/M3。

## 0. 结论

| 项 | 结果 |
|---|---|
| 机器 | `hw/arm/rk3568-lite.c`（~210 行）+ Kconfig/meson 挂钩，QEMU v11.1.0 fork（third_party/qemu，浅克隆） |
| 首启 | ✅ SMP=1 三断言 PASS → ✅ SMP=4 `Brought up 1 node, 4 CPUs` 三断言 PASS |
| rootfs 直启 | ✅ 同日达成：virtio-mmio×4（0xfea00000+/SPI 160+）+ rootfs.ext4 挂 /dev/vda，断言两条 PASS |
| 已建模 | 4×cortex-a55（mpidr Aff1=index）、GICv3（GICD/GICR）、UART2 serial_mm + DW 组件寄存器 overlay、PSCI/SMC、arch timer PPI 全套、virtio-mmio×4（sim-only） |
| 复现 | `QEMU=third_party/qemu/build/qemu-system-aarch64 boards/rk3568-atk/sim/boot-smoke.sh rk3568-lite` |
| 构建依赖 | `sudo apt install meson ninja-build libglib2.0-dev libpixman-1-dev` + `configure --target-list=aarch64-softmmu` |

## 1. 四个 bug 的排除链

1. **三断言全挂且串口零字节** → 上 `earlycon` + `-d unimp,guest_errors`：内核活着
   （PSCI/GICv3/A55 全识别），死在 `dw8250_setup_port+0x20` 的
   **synchronous external abort**（ESR 0x96000050）。
2. **addr2line 定位**（vmlinux 符号直接查）：崩溃链 `dw8250_setup_port →
   dw8250_detect_rs485_hw → writel(RE_EN)`——DW UART 扩展寄存器（RS485 @0xb4、
   CPR @0xf4、UCV @0xf8）在 serial_mm 只有 8 寄存器×4=0x20 字节的窗口**之外**，
   打进未分配地址 → ARM TCG 对未分配写直接报外部中止。
   修复：UART 0x100 区域先铺 unimp、serial_mm 后加（同优先级后加者胜出标准窗口）。
3. **tty 路径死、console 路径活**（kmsg 探针出、stdout 探针没、fd0 正常打开、
   ttyS2 中断计数 0、arch_timer 计数 273）。第一理论「CPR=0 → 无 UART_CAP_FIFO」
   只对了一半：按驱动源码（注意 **0xf4=CPR、0xf8=UCV**，别记反）给 overlay 配
   `CPR=0x00020002`（FIFO 字段 2×16=32 字节、APB 32 位）——没救活 tty。
4. **QEMU trace 裁决**：`gicv3_dist_set_irq` 显示 UART 中断以 **182 号**进
   distributor——我接的是 gpio 150（`GIC_INTERNAL+118`）。翻 arm_gicv3.c 源码：
   **gpio-in[n] 直接就是 SPI n**（INTID=n+32，见 gicv3_set_irq 注释），加
   GIC_INTERNAL 是画蛇添足。一行改成 `qdev_get_gpio_in(gicdev, 118)` → 立绿。
   （timer PPI 的 `NUM_SPIS + i*32` 基址接法是对的，所以只有 SPI 死。）
5. **四核唤醒**：内核 PSCI CPU_ON 找 mpidr 0x100/0x200/0x300，QEMU 默认
   mp_affinity 是 Aff0=index → "Requesting unknown CPU 256/512/768"。CPU
   realize 前设 `ARM_CPU(cpu)->mp_affinity = i << 8` 对齐 dtsi 拓扑 → 4 核全上。

## 2. 给后续设备的硬事实（demand-driven 下一个设备就用）

| 事实 | 值/出处 |
|---|---|
| gicv3 sysbus gpio-in 语义 | `[0..N-1]` = SPI n；PPI 在 `N + 32*i + ppi`（N=num_irq-32） |
| 未分配 MMIO 写 | ARM TCG 直接 synchronous external abort（不是静默忽略）——哑铺图必须用 unimp |
| DW UART 扩展偏移 | RS485 TCR 0xac / DE 0xb0 / RE 0xb4 / DLF 0xc0 / **CPR 0xf4 / UCV 0xf8** |
| CPR 编码 | FIFO_SIZE = bits[23:16] × 16；RK3568 = 0x00020002（32 字节 FIFO） |
| 8250 主线驱动 TX 全靠 UART 中断 | console 轮询独立——「console 出字、tty 无声」= 中断没通 |
| cortex-a55 cntfrq=24MHz + mp_affinity=i<<8 | 与真板一致 |

## 3. 需求探测器首采（2026-08-25 同日）

跑满 4 核到 shell，`-d unimp,guest_errors` 全程采集：**0 条**。解读：

- 七节点 DTS 纪律成立——内核对未建模区域零触碰，没有隐性依赖；
- 当前里程碑（内核 + initramfs shell）下机器模型**完备**，不存在「被动等待补齐」的设备；
- 下一个需求只能来自下一个里程碑的工作负载，这正是「需要什么，添加什么」循环的预期形态。

## 4. 后续

virtio 存储 + rootfs 直启同日达成，独立成篇见
[61 号笔记](61-2026-08-25-rk3568-lite-virtio-rootfs-direct-boot.md)。
之后的候选线：CRU 影子 + U-Boot proper（教启动链）、真 SDHCI 模型（教真存储，
替换 virtio 替身时成章）。
