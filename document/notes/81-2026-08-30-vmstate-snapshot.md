# 81 — vmstate 快照役：9.2 秒回桌面，遗留迟发 hardlockup（2026-08-30）

> 战役六。目标：给全部带状态影子补 VMStateDescription，救活 snapshot.py 的
> savevm/loadvm 工作流（战役四的诊断：影子寄存器归零 → restore 后 ~10s panic）。

## 0. 结果

| 项 | 结果 |
|---|---|
| **vmstate 全量落码** | ✅ 机器级（vop/mmu/cru/pmu/dcphy/gpio/last_req，含 vop 子结构 + post_load 重挂帧定时器并清 last_* 强制重建扫描输出）+ 设备级（i2c2/spi2 post_load 重算 IRQ、rk806、gt911 全字段含 mouse_bridge） |
| **restore 速度** | ✅ **9.2s 出首帧**（冷启动 ~80s → 9.2s，8.7 倍）；桌面画面完整（screendump chroma 8/9），串口 login 提示在 |
| **残留缺陷** | ⛔ restore 后 ~2-4 分钟（guest 时钟 ~130-290s）watchdog 硬锁 panic：CPU2 idle 任务、`watchdog_hardlockup_check → do_panic_on_target_cpu` 栈；**`watchdog=0` 创建参数未抑住**（栈里仍是 hardlockup_check） |

## 1. 修复链上的坑（快照流本身）

- **两槽 cmdline 死局**：snapshot.py 旧 cmdline 只声明 2 个 virtio transport 时
  内核启动后全核 idle 挂死（rootwait 等 vda？六槽全开即活——两/六的差异根因
  未深挖，直接采用与 smoke.py 完全一致的六槽 cmdline）
- 诊断路径：stdio hvc0（socket chardev 单连接+无缓冲坑）、QEMU stderr 的
  I2CDBG 流（证明内核在跑驱动 probe）、gdbfreezegrab（全核 arch_cpu_idle）
- `xp` 读 transport 寄存器见 device id=0 是**红鲱鱼**（正常启动也这样，
  未 probe 的 virtio-mmio 就是 0）

## 1.5 深挖后补（同日晚）：流无恙，单核即稳

- **vmstate 流完好**：restore 开 trace（savevm_state_*/vmstate_*）——397 段全部
  装载成功、无错；机器字段往返正确（vop-fb-phys/dsp、mmu-status/dte 全对）；
  那些 `load_bad` 是可选子段探测的正常噪音
- **guest 是先活后死**：restore 后 ~60s（guest ~100s）cpu0 才被 CPU7 的伙伴
  看门狗判死（`watchdog: CPU7: ... hard LOCKUP on cpu 0`），panic 落在当时
  运行的用户进程（apt-check）上
- **SMP=1 create → SMP=1 restore 稳定 ≥5min**：零 panic、串口应答、QEMU 88%
  在干活；5min 屏幕变黑 = GNOME 空闲息屏（快照流不挂输入设备，预期行为）
- gdbfreezegrab 在 loadvm 后读到多个"毒化 PC"（0xffffbad4…/0xffffbc1a…，
  每次值不同、冻结不动）——**判为 gdbstub 对 halted vCPU 的读取假象**，
  非真实执行状态（guest 同期明明健康）
- 结论：缺陷收敛到**多 vCPU 的跨核/定时器状态恢复**（TCG 多核 savevm 本就是
  人迹罕至路径）；单核形态可用作稳定工作流

## 1.8 二轮攻坚实录（08-31 凌晨）：理论逐一枪毙

| 实验 | 结果 | 枪毙了什么 |
|---|---|---|
| post_load `qemu_cpu_kick` 全核 | 锁死依旧 | "halted vCPU 没被踢醒"论 |
| 冷启动直跑 qcow2（无迁移）8 分钟 | 零锁死 | "qcow2/盘的问题"论 |
| 晚点快照（guest 232s，过了 104s 负载峰） | 恢复后 guest 244s 照锁（这回 cpu3） | "apt-check 负载触发"论 |
| `-accel tcg,thread=single` | 照锁 | "MTTCG 线程模型"论 |
| **`idle=poll`（内核永不 WFI）** | **照锁**（polling 的 CPU 也硬锁） | **"睡死等闹钟"论——最有力的一条** |

**存活事实链**：冷启动任意盘型都好；loadvm 后 ~1-2 分钟，任一 CPU 的定时器中断
投递静默死亡（polling 也一样收不到）→ 伙伴看门狗判死。SMP=1 唯一例外。
定论：**loadvm 缺失某个 per-CPU 运行时链接**——vtimer 的 QEMUTimer 与 GIC
PPI 的运行时通路在恢复后断掉一核（迁移流里字段都在：gt_timer 两枚都装了、
gicr_waker/ienabler0 都装了——但某处运行时重建没发生）。TCG 8 核 savevm
本就是无人走的路，上游缺一环不奇怪。

**下役刀口**：锁死瞬间读该核 CNTV_CTL/CVAL/CNTVCT + 在 gicv3_cpuif_update
挂计数器，看断在"定时器没到期"还是"到期了没送达"。

**现行可用**：SMP=1 快照（稳定）；或日用 FAST 冷启动 45s。idle=poll/watchdog=0
试验参数已从 snapshot.py 撤掉（无效）。

## 2. hardlockup 嫌疑清单（下役入口）

1. **丢失的 pending 状态**：GIC/GICR 迁移了，但某 vCPU 快照时正 WFI 等
   特定事件；load 后事件源（如某影子的定时器/pending 位）没重建 → 那个
   vCPU 永不醒 → buddy watchdog 判死。可对拍：save 前 `stop` 时机、
   post_load 主动 `cpu_interrupt`/Kick 全核
2. TCG tickless idle 假阳性：vCPU 合法长睡被误判（但真机无此象）
3. virtio 设备（blk/console）迁移后 kick 丢失——第一次 I/O 时 vCPU 等中断
4. `watchdog=0` 未生效之谜：查该参数在此内核的实际语义（可能要 `nmi_watchdog=0`
   + `nosoftlockup`），或确认快照 cmdline 真带上去了

## 3. 使用注意

- create ~4.5min（冷启动 73s + savevm ~3.5min 写 1.3GB）；restore 9.2s
- 快照绑基盘内容：rootfs.ext4 / 内核 Image / QEMU 二进制变了就要 drop 重造
- **当前不可用于长会话**（迟发 panic）——适合「快速看一眼桌面态」；
  修复 hardlockup 前，日用仍走 FAST 冷启动（45s）

## 4. 工具

- snapshot.py：六槽 cmdline + FAST + earlycon（诊断口）+ watchdog=0（试验中）
- 验收路径：restore → screendump chroma → 串口 login 探活 → 计时
