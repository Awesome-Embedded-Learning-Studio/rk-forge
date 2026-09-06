# 72 — VOP2 战役（二）：DRM 管线成立（2026-08-28）

> 三路侦察（workflow 25.7 万 token）改写打法后的一日攻坚。里程碑：
> **`[drm] Initialized rockchip 1.0.0 for display-subsystem` 在仿真里出现**，
> VOP2 + DSI2 双双 bound。一个 fdt_delprop 大坑、一个 AMBA 三连修、
> VOP2 行为影子上线。剩余挂点已冻结定位（runtime PM × commit_wait）。

## 0. 结论

| 项 | 结果 |
|---|---|
| **DRM 管线** | ✅ `bound fdd90000.vop (vop2_component_ops)` + `bound fde20000.dsi (dw_mipi_dsi2_rockchip_ops)` + `Initialized rockchip 1.0.0` |
| AMBA 修正三连 | ✅ 三块 PL330 全部加载（`Loaded driver for PL330 DMAC-241330`）；SPI 从永久 defer 变 PIO 回退 |
| VOP2 行为影子 | ✅ VERSION_INFO=0x40176786 过硬校验；帧中断注入（60fps ticker）让 ISR/CLR 握手真实运转 |
| panel 链 | ✅ dts 层删 vin-supply 后 panel/DSI 无声 probe 成功 |
| 回归 | 两板 board/linux 全绿 |
| 剩余挂点 | modeset 后 runtime PM autosuspend → vop2 ISR `pm_runtime_get_if_in_use` 秒退 → STATUS 挂 0x20 无人清 → `drm_crtc_commit_wait` 死锁（战役三核心） |

## 1. AMBA 修正三连（侦察的三个实锤全兑现）

1. **删 0xfea00000 影子**：真板只有 3 块 dmac，该地址是 virtio transport
   地盘——后加的同优先级区域按 LIFO 遮蔽了全部 4 个 transport（qtest 实锤
   MagicValue=0，rootfs 的 vda 会消失）。
2. **ID 寄存器位置**：内核 amba 总线在 `base+size-0x20`（dtsi reg=0x4000 →
   base+0x3FE0）读 periphid，不是 0xFE0——之前影子根本没被读到，这才是
   「deferred, reason unknown」的真身（amba_match 失败映射为 -EPROBE_DEFER）。
   影子扩为整块 0x4000、稀疏应答。
3. **PID 值**：PID1/PID2 应为 0x13/0x24（我首版写反成 0x33/0x13）。
   加上 CR0（0xE00）=0x1E0070（8 通道/16 事件/无 periph 接口——故意让 SPI
   的 chan_id 超界、xlate 回 NULL、回退 PIO）与 CRD=0xFF00003。

## 2. fdt_delprop 大坑（本轮最贵的一课）

运行时 `fdt_delprop(vin-supply)` 后内核在 **of_clk_init 里活锁**（8 核
trace 显示 `tmigr_active_up`/`__of_find_all_nodes` 死循环；单核同挂）。
摘掉 delprop 立即恢复——实锤。教训：**libfdt 的属性级删除会破坏内核 OF
遍历器依赖的 blob 结构**（节点 nop 是安全的——imx8mp 先例；属性删除不行）。

**正解 = DT 源层手术**：`boards/rk3588-topeet/sim/rk3588-topeet-board.dts`
include 真板 dts + `&vcc3v3_lcd_n { /delete-property/ vin-supply; }`，
dtc 编译保证结构合法。途中还踩一个拼写坑：标签是 `vcc3v3_lcd_n`（下划线），
写错时 dtc 静默建同名新节点、删了个寂寞——编译产物必须回验
（`dtc -I dtb -O dts | grep vin-supply` 计数为零才作数）。

## 3. VOP2 行为影子

侦察结论「四家驱动只有 VOP2 有硬校验」兑现：VERSION_INFO(0x004)=0x40176786。
帧完成机制（rockchip_drm_vop2.c ISR）：FS_FIELD=BIT(5) →
`drm_crtc_handle_vblank` + `send_vblank_event`。影子实现：
- VP_INT_CLR(0xA4+vp*0x10) 写 1 清（驱动写 `irqs<<16|irqs`）
- 60fps QEMU timer 持续对 INT_EN arm 了 BIT(5) 的 VP 置 STATUS + 注 SPI 156
  （与 vop_mmu 共享中断）。探针实录：前 200 tick ISR 正常握手（置位→清零），
  之后 STATUS 挂 0x20 无人清——**ISR 停止响应**，指向 runtime PM
  （`pm_runtime_get_if_in_use` 返回 0 时 ISR 秒退）与 modeset 的死锁闭环。
  这是战役三要解的物理：真扫描输出模型下 runtime PM 挂起/恢复与帧流的交互。

## 4. 侦察情报沉淀（供战役三直接取用）

- QEMU 自带 PL330 真模型可用（CRn/微码/IRQ 全），实例化参照
  exynos4210 `pl330_create()`（orgate 合并 IRQ）——真 DMA 需求出现时再上。
- SPI 真 transfer 需行为模型：TXDR 写→RXFLR 回环+RF_FULL 置位注 IRQ；
  PMIC（rk806 over SPI）在其上是第二个模型层。GPU 也等 PMIC 的 dcdc-reg1。
- fbcon 出现链（已验证到 DRM init）：`drm_dev_register → drm_client_setup →
  drm_fbdev → register_framebuffer → fbcon banner`。
- 诚实清单：vin-supply 手术（dts 层）、0xfea00000 无 dmac（真板本来如此）。

## 5. 复现

```bash
# DRM 管线（会走到 Initialized 后冻结在 modeset——战役三前线）：
third_party/qemu/build/qemu-system-aarch64 -M rk3588-lite -smp 8 -m 2G -nographic \
  -kernel third_party/src/rk3588-topeet/linux/arch/arm64/boot/Image \
  -dtb boards/rk3588-topeet/sim/rk3588-topeet-board.dtb \
  -initrd sim/initramfs-busybox.cpio.gz \
  -append "console=ttyS2 earlycon=uart8250,mmio32,0xfeb50000 rdinit=/init panic=-1 cpuidle.off=1"
```
