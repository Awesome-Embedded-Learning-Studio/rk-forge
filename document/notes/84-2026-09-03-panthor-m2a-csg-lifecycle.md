# 84 — panthor M2a：CSG 生命周期 ACK，噪音归零（2026-09-03）

> 战役七续二。目标：消 context destroy 的 `CSG update request timedout`
> 循环（note 83 §8 遗留），M2a noop 语义（调度/fence 量具，不宣称渲染）。

## 0. 结果

| 项 | 结果 |
|---|---|
| **CSG 生命周期静默** | ✅ 两轮 context create→destroy，`timedout`/`suspend failed` 全零（此前每轮 3 次） |
| **M1 不回退** | ✅ renderer = Mali-G610 MC4 (Panfrost) |
| **探针清偿** | ✅ SIMGRP/SIMGLB/SIMCSG/SIMCSREG/SIMMMAP/SIMMUA/SIMCSGWAIT 全撤；PANTHORIOCTL 保留（M2b submit 踩点用） |

## 1. 两个协议真相（费一刀才见）

1. **CSG update 不敲 doorbell(1..8) 寄存器**：`panthor_fw_ring_csg_doorbells`
   是 toggle **glb input.doorbell_req 的 CSG 位** + 敲 doorbell(0)。第一版
   按 doorbell(1..8) 实现白等一轮（超时纹丝不动）。
2. **doorbell_req 是 toggle 语义（边沿）**：位 1→0 也是事件。第二版按
   `doorbell_req & BIT(csg)` 位值过滤，STATUS_UPDATE 位（mask=0x20）漏 ACK
   （SIMCSGWAIT 探针实证 req=0x31/ack=0x11）。**修=每次 doorbell(0) 对全部
   8 组 CSG 幂等追平**（读当前 req 写 ack，重写无害）。

等待面（panthor_fw_wait_acks）三层兜底（busy-wait 10µs → wait_event →
超时终查）——同步追平即过，无需 IRQ（与 M0 的 halt 合同同款）。

## 2. QEMU 侧改动（hw/arm/rk3588-lite.c doorbell 引擎）

- doorbell(0)：追平 glb ack/doorbell_ack 后，对 CSG0..7 全组幂等追平
  `csg.output.ack = csg.input.req`（START/SUSPEND/TERMINATE/
  ENDPOINT_CONFIG/STATUS_UPDATE 即时完成）
- doorbell(1..8)（user/queue 通道）：walk 对应 CSG control 追平——
  留作 M2b（queue 提交），当前无调用方
- MCU 状态判定保留 glb_req（修掉了 CSG 循环踩 req 变量的 bug）

## 3. M2b 展望（queue 提交 / noop 完成量具）

1. mesa submit 路径：GROUP_SUBMIT（0x49）→ user doorbell → ring buffer
   消费——M2b 最小版：识别 wrapper CS 的 FLUSH/WAIT/CALL/SYNC_ADD、跳过
   CALL 用户段、推进 extract 指针 + 完成信号（sync memory 写 + cs_irq）
2. PANTHORIOCTL 打点直接观测量具（已在位）
3. 反证测试（note 76 §3.5）：目标 BO 填噪点，fake completion 不得宣称渲染

## 4. 落库清单

- `third_party/qemu` hw/arm/rk3588-lite.c：doorbell 引擎（glb CSG 位幂等
  追平 + user doorbell 占位）
- 内核树：全部 SIM* 探针撤除（PANTHORIOCTL 保留，M2b 后统一撤）
