# 82 — panthor 战役开工：侦察定谳 + M-pre0 SCMI agent 落地（2026-08-31）

> 战役七（note 76 批准的刀口 B）。本文覆盖：开战侦察、SCMI 影子服务端
> 全链打通、SMCCC conduit 真根因、M-pre0 验收；末尾挂两笔账。

## 0. 结果

| 项 | 结果 |
|---|---|
| **侦察定谳** | ✅ GPU 前置依赖六项里五项已通（见 §1 表），SCMI 是唯一 M0 阻塞——比 note 76 §2.2 预判乐观（regulator 坑被 gt911 战役的 rk806 影子顺带填平） |
| **M-pre0 SCMI agent** | ✅ QEMU 机器兼任 BL31：SMC 钩子 + shmem 交换 + BASE/CLOCK/RESET 三协议，126 条消息全 status=0 |
| **SMCCC 真根因** | ✅ 内核 PSCI_FEATURES 问 0x80000000，QEMU 内建 PSCI 答非支持 → `arm_smccc_1_1_get_conduit()=NONE` → **SCMI 的 SMC 指令根本不会执行**（res 全零兜底路径都走不到，直接 a0=-1）。修法：钩子里兼任应答 SMCCC 1.1 |
| **panthor 首入 probe** | ✅ `panthor fb000000.gpu: [drm] clock rate = 198000000` + `EM: created perf domain` + runtime PM resume 无错；probe 停在 MMIO 前（GPU_ID=0 零毯区）= M0 入口 |
| **挂账 1：restore 迟发锁死** | ⛔ 新二进制+新快照的 loadvm 在恢复后 ~19-23s 必现 hard LOCKUP（f03d2bb 同 signature），冷启动稳定；快照工作流暂不可用，详见 §5 |
| **挂账 2：panthor probe 无尾** | ⛔ clock/EM 两行后无任何错误行——clean fail 该有 "Invalid GPU ID"，疑似卡在零毯区上的轮询；见 §6 |

## 1. 侦察：GPU 依赖审计（谁挡了 panthor）

boot 后（snapshot restore 形态）逐项取证：

| 依赖 | 状态 | 证据 |
|---|---|---|
| SCMI clock（`assigned-clocks = <&scmi_clk 5>` 200MHz） | ❌ 唯一阻塞 | dmesg：`shmem_tx_prepare` WARN → `Timeout waiting for a free TX channel` → `probe -95`；零行 panthor |
| power-domains `pd_gpu` | ✅ 已通 | clk_summary 里 `power-domain@12` 已是 clk_gpu/coregroup/stacks 三条 CRU 时钟的消费者 |
| `mali-supply vdd_gpu_s0` | ✅ 已通 | `/sys/class/regulator` 26 条全注册（rk806 全轨，gt911 战役遗产），vdd_gpu_s0=regulator.5 |
| CRU 三条 GPU 时钟 | ✅ 已通 | clk_summary 164MHz 在跑（CRU 影子） |
| IRQ 92/93/94 | ✅ 通路在 | GIC 影子已被 VOP 验证 |
| MMIO 0xfb000000 | ❌ 零毯区 | `unimplemented-device` 0xf0000000/0x10000000 低优先级毯区覆盖（rk3588-lite.c:1680 段）——这就是 M0 本体 |

关键 DT 事实（rk3588-base.dtsi + topeet 增补）：

- `firmware/scmi`：`compatible="arm,scmi-smc"`、**`arm,smc-id=0x82000010`**、`shmem=<&scmi_shmem>`
- `scmi_shmem`：**reserved-memory 里 0x10f000/0x100 no-map 的 DRAM 洞**（不是 SRAM MMIO！）→ QEMU agent 直接 `cpu_physical_memory_*` 读写 guest RAM，零新增内存区
- 协议节点：`protocol@14`（clock，ids 0-10：CPUL/DSU/CPUB01/CPUB23/DDR/**GPU=5**/NPU/SBUS/…）、`protocol@16`（reset，TRNG 用 SCMI_SRST_H_TRNG_NS=48）
- deferred 名单里 `rockchip-rk3588-cpufreq`（等 rk860 CPU 供电芯，I2C0/1 无影子的独立病）与 `fe378000.rng`（同源）与本役无关

## 2. QEMU 侧实现（三层）

### 2.1 SMC 钩子（target/arm 通用管线）

- `target/arm/cpu.h`：`typedef bool (*ArmSmcHandlerFn)(ARMCPU*, uint32_t); extern ArmSmcHandlerFn arm_smc_handler;`
- `target/arm/tcg/psci.c` `arm_handle_psci_call()` 顶部：非 NULL 即先于 PSCI 分发调用；handler 返 true = 已处理（自写 x0）
- 分发链考证：translate-a64 `trans_SMC` → `gen_exception_insn_el(s,4,…)`（**PC 已由翻译器推进**，钩子只写返回值）→ `arm_cpu_do_interrupt` 的 psci 分支。SMP 能起 = PSCI SMC 通路本身健康

### 2.2 SCMI agent（hw/arm/rk3588-lite.c 新段）

- 机器 init：注册钩子、频率表取量程下限、**0x10f004 预写 FREE 位**（真机是 BL31 在内核前干的活）；post_load 同样重置 FREE
- 合同（= 内核 drivers/firmware/arm_scmi/ 源码，**驱动即规格**）：
  - shmem 布局 `struct scmi_shared_mem`：+0x04 channel_status(bit0=FREE)、+0x14 length(4+payload)、+0x18 msg_header(id[7:0] type[9:8] proto[17:10] token[27:18])、+0x1c payload(status 打头)
  - polling 模式：应答须在 **SMC 返回前**落内存，最后置 FREE；x0=0（SMCCC SUCCESS）
  - 报告版本刻意压低（BASE/CLOCK 2.0、RESET 1.0）：低于内核支持上限就不触发 NEGOTIATE，避开 v3 扩展名/CONFIG_GET 族
- BASE(0x10)：VERSION/ATTRIBUTES/**byte0=proto数 byte1=agent数（见 §3 坑）**/MSG_ATTR/VENDOR/SUB_VENDOR/IMPL_VER/**LIST_PROTOCOLS（必须回 {0x14,0x16}，协议表就靠它建）**/AGENT/NOTIFY
- CLOCK(0x14)：VERSION/ATTRIBUTES(11 条)/MSG_ATTR/CLOCK_ATTRIBUTES(name+enable)/DESCRIBE_RATES(**线性三元组 flags=3|BIT(12)=0x1003**，min/max/step)/RATE_SET(夹量程存储)/RATE_GET/CONFIG_SET/NAME_GET
- RESET(0x16)：VERSION/ATTRIBUTES(64 域，覆到 48)/DOMAIN_ATTRIBUTES/RESET
- 时钟名 **scmi_ 前缀**：CLOCK_ATTRIBUTES 的 name 走 `clk_register`，与 CRU 同名直接 -EEXIST 丢注册（首轮实测 clk_gpu 撞名）
- vmstate：`rate[11]+enabled` 入机器级 VMState；诊断属性 `scmi-served`/`scmi-errs`；`SCMIDBG=1` 逐消息打 stderr

### 2.3 SMCCC 1.1 应答（本次最深的坑）

失败链全程有源码实证：

1. 内核 `psci_init_smccc()` → `psci_features(0x80000000)`（SMC #0x8400000a, x1=0x80000000）
2. QEMU 内建 PSCI 的 FEATURES 内层 switch **按被查 fid 走 default → NOT_SUPPORTED**（它只认 PSCI 函数族，不认 SMCCC 架构函数）
3. 内核放弃查询 → `smccc_version` 停在 1.0 → `arm_smccc_1_1_get_conduit()` 永远返回 **NONE**
4. SCMI transport 的 `arm_smccc_1_1_invoke()` 走 `__fail_smccc_1_1`：**res->a0=-1 填完拉倒，SMC 指令根本不执行**（SCMIDBG 钩子 204s 零命中 0x82000010 实锤）
5. `smc_send_message` 见 a0≠0 → -EOPNOTSUPP 快速失败（dmesg 5ms 时序吻合）；channel 停 busy → 下一发 60ms FREE 自旋 WARN → probe -95

真机 BL31 会答 SMCCC 1.1，所以真机无此坑。修法在钩子里兼任：

- `fid=0x8400000a && x1=0x80000000` → 0（可查）
- `fid=0x80000000` → 0x80010000（**报 1.1 不报 1.2**，避开 SOC_ID 探测路径）

副作用面：SMCCC 活了之后内核多出 ARCH_FEATURES/TRNG 探测 SMC（fid=82000003/80000001 等），全部落 PSCI default → -1，无害。

## 3. M-pre0 验收记录

修复链上的另一发：BASE ATTRIBUTES 我先按 spec 位域填 `[23:16]`，内核 `struct scmi_msg_resp_base_attributes` 却是 **u8 num_protocols; u8 num_agents**（byte0/byte1）→ 读成 proto=1，列 2 个协议触发 `No. Returned protocols > Total protocols.` → 协议表清空 → `protocol 20/22 not implemented` → clock provider 没建。改 byte 布局后：

```
[5.017] arm-scmi.3.auto: SCMI Protocol v2.0 'rk-forge:sim' Firmware version 0x1
[5.222] panthor fb000000.gpu: [drm] clock rate = 198000000
[5.235] panthor fb000000.gpu: EM: created perf domain
[5.239] SIM-DIAG: rpm_callback: dev=fb000000.gpu runtime_error=0 set   ← runtime PM resume 无错
```

- `devices_deferred` 里 **fb000000.gpu 消失**（只剩 cpufreq/rng 两个无关项）
- SCMI 逐消息日志：**126 条 fid=0x82000010 全 status=0**（CLOCK ATTRIBUTES×10、RATE_GET×7、RESET 域查询×64 …）
- 注：`clock rate = 198000000` 是 panthor drm 层读的 CRU clk_gpu（非 SCMI 值），无碍

M-pre0 通过，M0 入口就位。

## 4. 工作流变化

- 诊断：QEMU 侧 `SCMIDBG=1`（逐消息 stderr）+ qom `scmi-served`/`scmi-errs`
- 补丁导出路径扩容：`git diff HEAD -- hmp-commands.hx hw/arm hw/input hw/intc/arm_gicv3_cpuif.c hw/ssi include/monitor/hmp.h monitor/hmp-cmds target/arm`（18 文件；顺手补上了此前漏导的 gicv3_cpuif/cpu.h/psci.c；未跟踪的 gt911.c/rk806.c 要先 `git add -N`）

## 5. 挂账 1：restore 迟发 hard LOCKUP 复发（f03d2bb 同族）

新二进制 + 新建快照的 restore **必现**：恢复后 ~19-23s hard LOCKUP（`watchdog_hardlockup_check → do_panic_on_target_cpu`，受害核 1/2/4 浮动），guest 时间戳在同一快照内逐次一致（TCG 确定性复放）。旧二进制+旧快照今晨稳定 15min+，故**嫌疑在本次改动或新快照内容**。

- 冷启动稳定：无桌面负载冷启 uptime>128s 无恙；带桌面冷启 80s 首帧 + 180s savevm 窗口无恙（但没活过 guest 116s+，不能完全排除冷启晚死）
- 法医快照（cmdline 追加 `nmi_watchdog=0 watchdog=0 hardlockup_panic=0`）压制 panic 后验尸：**soft lockup——CPU#4 gnome-shell 在 `do_timerfd_settime` 卡 26s**（lr 在 hrtimer 设定路径）→ 恢复后跨核定时器协作类丢失唤醒，非 SCMI handler 本身死循环
- SMP=1 restore 不可测（快照按 8 核建，loadvm 拒载）
- 待办二分：stash QEMU 改动用旧二进制重建快照 restore ×2 → 定「二进制回归」还是「快照内容时点」；头号嫌疑是 panthor probe 卡在零毯区轮询（见 §6）改变了恢复后早期的核间定时器行为

## 6. 挂账 2：panthor probe 无尾（M0 第一步）

clock/EM 两行后**零输出**：clean fail 应有 "Invalid GPU ID" 之类错误行（GPU_ID=0），没有 → 疑似 probe 卡在某等待（L2 ready 轮询 / IRQ 等待 / coherency 特性读）。下一步（M0 开工序）：

1. boot 后 `cat /sys/kernel/debug/devices_deferred` + 长窗口 dmesg 抓 probe 尾部；确认卡点读 v7.1 `panthor_device_init` 源序
2. 最小 GPU 影子开张：0x000 GPU_ID=0xa8670005 + features/present/ready 三组真机值（note 76 §2.3 表），先让 probe 快速 clean fail/通过
3. 两笔账可能同源：probe 卡轮询 ↔ 恢复后锁死——GPU_ID 影子落地后先复测 restore

## 7. 落库清单

- `third_party/qemu`：target/arm/cpu.h + tcg/psci.c（钩子）、hw/arm/rk3588-lite.c（scmi 段 + 枚举前置 + vmstate + post_load）
- `sim/qemu-sim-machines.patch` 重导（18 文件）
- 快照已用最终二进制重建（restore 不稳挂账 §5）
