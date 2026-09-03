# 86 — panthor M2b：wrapper-CS 解释器，fence 全通桌面渲染循环活（2026-09-03）

> 战役七终章。note 76 §3.5 的 M2a-noop 量具形态（本项目编号 M2b）：
> 调度/fence/swap 量具可用，像素免责。

## 0. 结果

| 项 | 结果 |
|---|---|
| **fence 完成链** | ✅ mutter 的 GROUP_SUBMIT → 假 MCU 消费 ring → SYNC_ADD64 真执行 → SYNC_UPDATE/cs_irq/JOB_IRQ → fence 完成 → `drm_syncobj_wait` 醒 |
| **桌面渲染循环** | ✅ mutter 持续 submit/swap（fb-phys 跨帧翻页 1798967296→710213632），VOP 扫描活动 |
| **反证（免责）** | ✅ screendump 1024×600 **纯黑**——用户段未执行、BO 零初始化，fake completion 未伪装渲染（note 76 §3.5 的验收负面测试） |
| **长稳** | ✅ 12min+ 零 panthor 错误、零 reset、GDM active |
| 12min 冷启动 | ✅ 同机台 GDM 负载冷启动 14min+ 稳（B 役证） |

## 1. 实现（QEMU rk3588-lite.c）

**数据面两条 walk 通道**：
- fw VM（AS0）：接口结构、ring 的 insert/extract 指针
- 用户 VM：ring 内容、syncobj——**AS 扫描**（`va_pa_user`：扫
  as_transtab[1..7] 第一个 walk 成功者，内核 group start 时 program）

**解释器**（`cs_consume`，寄存器文件 192×u64）：
- 识别 v10 编码（mesa genxml）：MOVE48(1)/MOVE32(2) 装寄存器；
  **SYNC_ADD32(37)/SYNC_ADD64(51) 真执行**（addr/data 从寄存器取，
  32/64 位读-改-写 sync 内存）；CALL(32)/WAIT(3)/FLUSH_CACHE2(36)/
  NOP/ERROR_BARRIER(47) 及 RUN_* 一律跳过（M2b 语义）
- 消费循环：extract→insert（环形取模，64K 指令上限）

**完成面**：extract=insert 写回、CS output.ack 追平、CSG input.req ^=
SYNC_UPDATE(bit28)、csg output.cs_irq_req ^= BIT(cs)、job_rawstat |=
BIT(csg) 拉 JOB_IRQ（电平）。

**触发点**：doorbell(0)（内核 submit 走 `panthor_fw_toggle_reqs(csg
doorbell_req)` + ring_csg_doorbells——**还是汇到 glb doorbell(0)**，与
M2a 的 CSG update 同通道；per-CS 响铃 = `csg.in.doorbell_req ^
csg.out.doorbell_ack` 的 toggle 位差）。

## 2. 战役七终局

```
M-pre0(SCMI/SMCCC) → M0(renderD128) → M1(mesa 认 G610)
→ M2a(CSG 生命周期) → M2b(fence 量具，桌面渲染循环活) → [真像素=执行器，No-Go 维持 note 76 裁决]
```

- 全链 5 个里程碑、~6 天战役
- **真像素（M2b-执行器）维持 note 76 No-Go**：wrapper 解释器到用户段
  Valhall 执行之间隔着 1-3 人月的 ISA 解释器工程——当前量具形态已是
  调度/驱动/用户态三层的完整验证平台
- 桌面工作流决策：**snapshot.py 的 panthor_init 拉黑保留**（拉了黑 =
  llvmpipe 慢但可见；放开 = panfrost 快但黑屏——快照是"可用桌面"生产线，
  选可见）。研究机（resboot）不拉黑。

## 3. 挂账转移

- restore 多核 loadvm 锁死（note 85 §3 四方向）
- 真机 fixture 补采（CS features 192 占位等）
- PANTHORIOCTL 打点仍在内核树（战役七全收官，可撤——留 M2b-执行器
  复审时用，或下会话撤）
