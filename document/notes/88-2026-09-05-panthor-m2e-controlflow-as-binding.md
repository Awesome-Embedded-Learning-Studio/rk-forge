# 88 — panthor M2e：控制流指令 + 权威 AS 绑定 + 用户门铃修复（2026-09-05）

> 战役七续。三件事：BRANCH/JUMP/ADD_IMM 实装（编码从 mesa v10.xml +
> cs_builder.h 取证）、多 VM walk 穿表修复（AS 权威绑定）、以及一个
> **M2b 时代就存在的调度楔死**的根因定位与修复（用户门铃被忽略）。

## 0. 结果

| 项 | 结果 |
|---|---|
| BRANCH(22)/JUMP(33)/ADD_IMM(16/17) | ✅ 实装（编码权威取证，见 §1） |
| 多 VM 穿表 bug | ✅ 根修：walk 走组绑定 AS（99.7-100% 命中，fail=0） |
| glClear 连续多跑 | ✅ **单机连跑 4 次 PASS**（M2c/M2d 从未做到，见 §3） |
| note 87 "多 VM FBD walk 失败" | ✅ 重定性：垃圾 FBD 0xFFFB6D83 = 穿错 VM 的 LOAD_MULTIPLE 读错页（非 walk 引擎缺陷） |
| mutter 负载 | 111 job 消费、walk_as_ok=2000/2007；**~11min RCU stall 停摆（未闭环，M2f）** |

## 1. 指令编码取证（mesa genxml v10.xml + cs_builder.h）

- **BRANCH(22)**：Offset 16 位有符号@0（**指令单位**）、Condition 4 位@28
  （Lequal/Greater/Equal/Nequal/Less/Gequal/Always，对 `(u32)regs[value]`
  与 0 比较，有序比较按有符号）、Value 寄存器@40。跳转目标 =
  本条位置 + 1 + offset（cs_builder `cs_set_label`：`offset = target -
  next_pos - 1`，实测三处一致）。
- **JUMP(33)**：Address 寄存器@40、Length@32 **字节**（`cs_wrap_chunk`：
  `*length_patch = pos * 8`）。mesa chunk 溢出链 = MOVE48 装新缓冲地址 +
  MOVE32 装长度 + JUMP 换段——解释器实现为递归换段。
- **ADD_IMM32/64(16/17)**：imm 有符号 32@0、src@40、dst@48。
- glClear 的 CS **一个分支都没有**（op-branch=0）；BRANCH 只在 mutter
  流里出现（op-branch=2~19）。note 87 "if/else 双装载恰好=else 路径"
  的侥幸对 glClear 无关，对 mutter 也不再依赖。

## 2. 多 VM 穿表：从"扫表碰运气"到"权威绑定"

**症状**：mutter 在跑时 glClear readback 全零（无 GL 错误）；
note 87 的 mutter FBD walk 失败（fbd=0x7ffffe4e5380 walk 不通）。

**根因**：`va_pa_user` 扫 AS1..7 取"第一个 walk 成功者"。多 VM 的堆区
VA（0x7fff_xxxx）高度别名——别的 VM 的表也能"成功"walk 同一 VA，
落到错误物理页：clear 写进别的 VM 的 BO（readback 全零）、LOAD_MULTIPLE
读别人的内存当寄存器值（垃圾 FBD 0xFFFB6D83）。

**修复（协议真相）**：内核 `csg_slot_prog_locked`（panthor_sched.c:1457）
把 `panthor_vm_as(group->vm)` 写进 **CSG input iface +0x50 的 config 字段**
——固件本来就知道每组用哪个 AS。`cs_consume` 入口读它设 `cur_as`，
walk **只走该表**（真固件语义：组在绑定 AS 上下文里执行）；未绑定才
回退 MRU 扫描+换出影子环（实测形同虚设：99.7-100% 走权威表）。

## 3. 调度楔死根因：用户门铃被忽略（M2b 以来隐藏）

**症状**：同一 boot 第二次跑 gc.py 起 job timeout——GROUP_SUBMIT 内核侧
ret=0，但假 MCU 一个门铃都收不到（GPUDB 痕迹实证）。

**A/B 归因**：GPUM2D=1（回退 M2d 语义）同样复现——**预存在缺陷**，
非 M2e 回归。

**根因（内核源码取证）**：on-slot submit 直接写
`CSF_DOORBELL(queue->doorbell_id)`（panthor_sched.c `group_submit_locked`），
**不 toggle csg doorbell_req**；假 MCU 只在 doorbell(0) 的
`req^ack` 位差里找活干。组的第一个 job 靠 START 路径（`csg_slot_prog`
会 toggle）被 doorbell(0) sweep 碰到；**第二个 job 起永远无人消费**→
fence 不完成 → job timeout → 严重时 RCU stall panic。

**修复**：doorbell(id≠0) = 该组（doorbell_id=csg_id+1）的 queue 门铃，
直接扫该组 8 个 CS 消费（insert==extract 幂等追平）。

**验收**：干净机 gc.py 连跑 4 次 PASS（每次新 fd=新 VM=新组，覆盖
START 路径 + 用户门铃路径 + 多 VM 绑定）。

## 4. 边界（诚实声明）

- **mutter 持续负载 ~11min RCU stall 停摆未闭环**（M2f 首选课题）：
  TCG 8 核 + 每帧同步消费（每条指令 4 级页表 walk）可能把 rcu_preempt
  饿死——负载饥饿还是协议反馈环未定；mutter+glClear 并发像素验收
  因此未完成
- 桌面仍不可见（shader/tiler 深水区，note 76 原判不变；screendump 仍黑）
- BRANCH 有序比较的有符号性未实测（mesa 只用 Always/Nequal/EQUAL 类）
- MRU 扫描+影子环回退路径现在是事实死代码（保留作诊断）

## 5. 装备与流程

- **GPUM2D=1**：回退 M2d 解释器语义（A/B 开关）；**GPUDBG=1**：stderr
  门铃/消费级打点（/tmp/scmi-dbg.log）
- 新 qom 诊断：gpu-walk-ok/as-ok/fail/fail-va、gpu-rf-fbd-fail/va、
  op-branch/jump/add-imm32
- /tmp/sercmd2.py 重写适配 rk-forge/rk-forge 登录（仓库 sim/sercmd.py
  仍是 root 版，勿直接用）
- qemu 树 git 操作危险实录：`git show :file > file` 排查法会写空文件
  （index 与工作区状态交错），本次靠 /tmp 手工备份救回——对
  third_party/qemu 只做只读 git 查询
