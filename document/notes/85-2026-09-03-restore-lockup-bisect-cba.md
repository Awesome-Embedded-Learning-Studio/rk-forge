# 85 — CBA 三连：桌面负载验成色 + restore 锁死定界（2026-09-03）

> 战役七续三（M2a 后）。C=桌面×panthor 快测、B=restore 迟发锁死二分。
> A（M2b wrapper CS 解释器）留下一役。

## 0. 结果

| 项 | 结果 |
|---|---|
| **C：桌面×panthor** | ✅ mutter/gjs 真实负载下 M1/M2a 成色全过：context 建立、443 次 GROUP_SUBMIT、零 CSG 错误、零崩溃。卡点=`drm_syncobj_array_wait_timeout`（等 fence）——**M2b 的验收规格直接到手**：fake completion（推进 extract + 写 syncobj）→ mutter swap → VOP 出帧 |
| **B：锁死定界三连** | ✅ SMP=8 冷启动（GDM 负载 14min+）稳；SMP=8 restore ~7s（guest）内 5 核 cpuif 冻结死；SMP=1 restore 稳（9min+）→ **多核 loadvm 恢复缺陷**（f03d2bb 同族新形态），SMP=1 快照工作流恢复可用（桌面 8.8s 回） |
| 工具 | `sim/forensic_restore.py`（法医 restore + diag 采集）；`sim/resboot.py` 加 `GDM=1` 开关 |

## 1. C 细节：mutter 的真实序列

GDM 放开（`GDM=1 python3 sim/resboot.py`）后 gnome-shell 全活：
EGL context（M1 能力）→ GROUP_SUBMIT(0x49) ×443（其一 -22 后重试过）→
`drm_syncobj_array_wait_timeout` 挂起等完成。**没有 submit 层错误**——
ring buffer 无人消费是唯一缺口（预期内：假 MCU 不跑 CS）。
vop-fb-phys=0（无扫描输出，mutter 不 swap）。

## 2. B 细节：死亡现场

- 复现：guest 100s（= 快照 93s + **恢复后仅 ~7s**）CPU4 报 CPU5 hard LOCKUP
- panic 压制不生效（hardlockup_panic=0 没拦住 nmi_panic——待查为何）
- **diag 采集**（qom diag-cpuif-N）：146s→210s 增量——**核 0/1/4/5/7 冻结**
  （+0），核 2/3/6 仍 +123k；fb 同步冻结
- **gdbfreezegrab 全核现场**（毒化 PC 教训不适用：核在跑非 halted）：
  - cpu5 卡 `arch_timer_read_cntvct_el0`（`__arch_counter_get_cntvct_stable`
    的 seq 重试循环——**CNTVCT 稳定读永不收敛**）
  - cpu3/4/6 在 `_raw_spin_lock`/`smp_call_function_many_cond` 等锁
    （持锁者疑为 timer 读卡死者）
  - 其余 panic-park/idle
- klogdump 直读失败（__log_buf 物理换算 0x3429140 读到 rodata 字典表——
  内核重编后 KIMAGE 偏移漂移，重算规则待修——B 挂账）

## 3. 裁决与下一步

**多核 loadvm 恢复期缺陷**（f03d2bb 修了 vtimer raw-write 再武装；本形态
更早更深：恢复后数秒内 5 核中断投递冻结）。深挖方向：

1. 死核寄存器解锁地址（queued spinlock 的 pending/locked 字段）找持锁者
2. CNTVCT 稳定读卡死 = seqcount 在恢复后被打成永久不一致？读 cntvct_seq
   与 victim 现场
3. TCG loadvm 的 cross-CPU 中断路由（上游人迹罕至区）——qemu-devel 检索
   loadvm+gicv3 已知问题
4. klogdump 地址重算规则修掉（`__log_buf` virt→phys 不再恒 -0x80000000）

**工作流现状**：桌面秒回 = SMP=1（稳定）；SMP=8 研究/战役 = 冷启 resboot
（不依赖快照）。两者并行不受影响。
