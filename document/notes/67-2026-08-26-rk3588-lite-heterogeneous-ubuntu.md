# 67 — rk3588-lite：全组织首台异构仿真机 + Ubuntu 真根直启（2026-08-26）

> RK3568 收官同日开线、同日双里程碑：4×A55+4×A76 异构 8 核全部点亮（各自
> 报真实 MIDR），Ubuntu 26.04 的 3GiB 真根在仿真机上挂载进 shell。期间挖出
> 一个横跨两板的大坑：**QEMU GICv3 gpio-in 编号语义**。

## 0. 结论

| 项 | 结果 |
|---|---|
| 异构 8 核 | ✅ `Brought up 1 node, 8 CPUs`；A55 报 0x412fd050、A76 报 0x414fd0b1（真 MIDR）；arch_timer PPI 跨 8 核 1300+ 次投递 |
| initramfs shell | ✅ 三断言 PASS（`rk3588-lite linux --check`），busybox 包板无关、与 rk3568 共用 |
| **Ubuntu 真根直启** | ✅ `VFS: Mounted root (ext4)` + shell sentinel（`rk3588-lite rootfs --check`）——真机线的 Ubuntu 26.04 3GiB 镜像进了仿真 |
| 回归 | rk3568 六模式 + rk3588 两模式，八模式全绿 |
| 脚本 | boot-smoke.py 升级双板结构（`[板] [模式] [--check]`） |

## 1. 硬事实（rk3588-base.dtsi / rk3588_common.h）

| 事实 | 值 |
|---|---|
| 异构拓扑 | A55 cpu_l0-3 @ mpidr 0x0/0x100/0x200/0x300；A76 cpu_b0-3 @ 0x400-0x700（`mp_affinity = i << 8` 一式覆盖） |
| UART2 | 0xfeb50000，SPI 333，**4 中断单元**（比 rk3568 多 wake 位，PPI 也要 4 单元） |
| GIC | GICD@0xfe600000 / GICR@0xfe680000（0x100000 = 8 核 redistributor） |
| DRAM | 基址 0（CFG_SYS_SDRAM_BASE=0），U-Boot TEXT_BASE 0x00800000 |
| 真板控制台 | **ttyFIQ0**（FIQ 调试器，topeet dts 把 uart2 的 8250 绑定禁用了）——sim 必须走普通 8250 路线 |

## 2. 大坑：QEMU GICv3 gpio-in 编号语义（横跨两板）

现象：rk3588 内核文本正常（printk 轮询）、用户态全哑（TX/RX 都死）；
`/proc/interrupts`（经 /init 的 kmsg 逐行倒出，cat 整块写会 EINVAL）显示
ttyS2 映射正确但 **0 次投递**，而 arch_timer PPI 1300+ 次。

排查链：SPI 200/333 编号二分（无关）→ IRQ 代理探针（16550 拉线 16 次，
确认设备侧活着；探针副作用太大即撤）→ 读 `hw/intc/arm_gicv3.c` gicv3_set_irq
源码定案：

```c
/* gpio n < num_irq-32 → SPI n → INTID n+32；gpio ≥ → 按 CPU 平铺的 PPI */
gicv3_dist_set_irq(s, irq + GIC_INTERNAL, level);
```

**gpio-in n 传的是 SPI 编号，不是 INTID**。两台机器的 `GIC_INTERNAL + SPI`
写法全部错位 +32。修正后 rk3588 立即全通；**rk3568 同错却一直活着**——它的
内核/用户态走了某条轮询后路（未深究，属于侥幸），修正后回归依旧全绿。
virtio 两板此前「能用」是纯轮询（probe 自述 poll queues），同样受益于修正。

## 3. U-Boot 线待课题（诚实清单）

- 真板 bootcmd 走 FIT/bootm + ttyFIQ0 控制台：sim 无 BL31 → FIQ 调试器不可
  用，uboot/board/fit 模式需先解决控制台方案（改 8250 console 的 dts 覆盖
  或给 FIQ 建模）。
- CRU/PMU/GRF 影子（真板 DTS 模式的需求探测尚未开始，rk3568 的方法论
  平移即可）。

## 4. 复现

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite linux --check   # 异构三断言
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite rootfs --check  # Ubuntu 真根
```
