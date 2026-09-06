# 82 — panthor 战役开工：侦察定谳 + M-pre0 SCMI agent + **M0 达成**（2026-08-31）

> 战役七（note 76 批准的刀口 B）。本文覆盖：开战侦察、SCMI 影子服务端
> 全链打通、SMCCC conduit 真根因、M-pre0 验收、**GPU 影子 + 假 MCU 一举打到
> M0（render node 出现）**；末尾挂两笔账。

## 0. 结果

| 项 | 结果 |
|---|---|
| **侦察定谳** | ✅ GPU 前置依赖六项里五项已通（见 §1 表），SCMI 是唯一 M0 阻塞——比 note 76 §2.2 预判乐观（regulator 坑被 gt911 战役的 rk806 影子顺带填平） |
| **M-pre0 SCMI agent** | ✅ QEMU 机器兼任 BL31：SMC 钩子 + shmem 交换 + BASE/CLOCK/RESET 三协议，126 条消息全 status=0 |
| **SMCCC 真根因** | ✅ 内核 PSCI_FEATURES 问 0x80000000，QEMU 内建 PSCI 答非支持 → `arm_smccc_1_1_get_conduit()=NONE` → **SCMI 的 SMC 指令根本不会执行**（res 全零兜底路径都走不到，直接 a0=-1）。修法：钩子里兼任应答 SMCCC 1.1 |
| **M0 达成（同日打穿）** | ✅ GPU 影子（ID/features/power）→ 假 MCU（AS0 LPAE 走查 + version 写入 + doorbell ACK 引擎）→ **`Initialized panthor 1.8.0 on minor 1` + `/dev/dri/renderD128`**，全链打印与真机日志逐字一致（§3.5） |
| **挂账 1：restore 迟发锁死** | ⛔ 新二进制+新快照的 loadvm 恢复后 1min 内必现 hard LOCKUP（f03d2bb 同 signature），冷启动稳定；**panthor 嫌疑已排除**（§5） |
| **挂账 2：桌面×panthor 冲突** | ⛔ renderD128 存在后 mutter 的 EGL 开它卡死在未实现 CSG ioctl（gnome-shell 20s 循环崩）；桌面流 cmdline 临时拉黑 `panthor_init`，M1 后撤（§7） |

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

## 3.5 M0：GPU 影子 + 假 MCU 一举打穿（同日晚场）

### 3.5.1 probe 无尾之谜先解

GPU_ID=0 时 `panthor_hw_gpu_id_init` 返 `-ENXIO` **静默退出**（driver core 只打
deferred 不打 ENXIO）——上一轮"probe 无尾"是干净哑败，不是卡死。盖最小影子即可
推进。

### 3.5.2 GPU 影子（v10 经典路线）

GPU_ID=0xa8670005 的 arch major=10 → `panthor_hw_match` 绑 v10 ops（无 PWR_CTRL
子系统，panthor_pwr.c 是 arch≥14 的新抽象）。最小集（真机值 note 76 §2.3）：

- RO fixture：GPU_ID/features/present（SHADER 0x50005/TILER 1/L2 1）；未采寄存器
  保守 0（CORE_FEATURES/REVID/COHERENCY/TEXTURE/THREAD）
- 电源块**全同步**：写 PWRON 立即置 ready（驱动 `block_power_on` 是纯
  readl_poll_timeout）、PWRTRANS 恒 0、PWRACTIVE≈ready
- GPU_CMD soft/hard reset→RAWSTAT|=bit8、flush→bit17——驱动是
  wait_event_timeout + **事后核验 RAWSTAT 的兜底结构**，不拉 IRQ 也过；仍按
  电平（stat=raw&mask）拉 GPU_IRQ/SPI94
- AS 寄存器组 0x2400+（TRANSTAB/MEMATTR/TRANSCFG RW、AS_COMMAND 瞬时完成、
  AS_STATUS 恒不 active）、JOB/MMU IRQ 组（0x1000+/0x2000+，bit31=JOB_GLOBAL_IF）
- 时间戳组 0x88/0x90/0x98 走 QEMU 虚拟钟

结果（冷启 dmesg，与真机日志逐字一致）：

```
Mali-G610 id 0xa867 major 0x0 minor 0x0 status 0x5
Features: L2:0x7120306 Tiler:0x809 Mem:0x301 MMU:0x2830 AS:0xff
shader_present=0x50005 l2_present=0x1 tiler_present=0x1
Firmware git sha: 95a25d71030715381f33105394285e1dcc860a65
```

### 3.5.3 假 MCU（MCU boot + doorbell ACK 引擎）

probe 到 `Failed to boot MCU (status=disabled)` -110（1s 超时）后补齐：

- **MCU boot**：驱动写 MCU_CONTROL=AUTO 后等 JOB_IRQ GLOBAL_IF（超时兜底核验
  STAT）；假 MCU 在写入同步路径里**经 AS0 LPAE 走查**（驱动用 ARM_64_LPAE_S1：
  48VA/40PA、4K 页+2M/1G block、表项 bits[1:0] 01=block/11=table|page）把
  CSF_MCU_SHARED_REGION_START(0x04000000) 的 control.version 写成 0x01050000
  （镜像初值 0；fw_init_ifaces 直读 kmap 的 version，=0 报"Firmware version is
  0"）→ MCU_STATUS=ENABLED → RAWSTAT|=bit31
- **doorbell(0) 引擎**（= note 76 §2.7 toggle/ACK 合同）：autosuspend 的
  `fw_halt_mcu` 走 input.req + CSF_DOORBELL(0)，等待是
  read_poll_timeout_atomic **纯轮询**——ack 必须在 doorbell 写的同一同步路径
  追平。实现：walk control(+8 input_va/+c output_va)→walk input/output→
  `output.ack=input.req`、`output.doorbell_ack=input.doorbell_req`，按 req 的
  GLB_STATE[14:12]（HALT=1）或老式 bit0 同步 MCU_STATUS。首版只答 halt 超时
  循环（15 处/分钟）；补 doorbell 后归零
- **M0 验收（note 76 §3.3 标准全过）**：

```
panthor fb000000.gpu: [drm] CSF FW using interface v1.5.0, Features 0x0 Instrumentation features 0x71
panthor fb000000.gpu: [drm] Using Transparent Hugepage
[drm] Initialized panthor 1.8.0 for fb000000.gpu on minor 1
```

`/dev/dri/renderD128` 存在（udevadm DEVNAME 确认）+ card1。真机对照（note 76
§2.3 表）：CSF 1.5.0 ✓ instrumentation 0x71 ✓ DRM 1.8.0 minor 1 ✓。

## 4. 工作流变化

- 诊断：QEMU 侧 `SCMIDBG=1`（逐消息 stderr）+ qom `scmi-served`/`scmi-errs`
- 补丁导出路径扩容：`git diff HEAD -- hmp-commands.hx hw/arm hw/input hw/intc/arm_gicv3_cpuif.c hw/ssi include/monitor/hmp.h monitor/hmp-cmds target/arm`（18 文件；顺手补上了此前漏导的 gicv3_cpuif/cpu.h/psci.c；未跟踪的 gt911.c/rk806.c 要先 `git add -N`）

## 5. 挂账 1：restore 迟发 hard LOCKUP 复发（f03d2bb 同族）

新二进制 + 新建快照的 restore **必现**：恢复后 ~20-70s hard LOCKUP（`watchdog_hardlockup_check → do_panic_on_target_cpu`，受害核浮动），guest 时间戳在同一快照内逐次一致（TCG 确定性复放）。旧二进制+旧快照今晨稳定 15min+，故嫌疑在本次改动或新快照内容。

- 冷启动稳定：带桌面冷启 80s 首帧 + uptime>165s 多轮无恙
- 法医快照（cmdline 追加 `nmi_watchdog=0 watchdog=0 hardlockup_panic=0`）压制 panic 后验尸：**soft lockup——CPU#4 gnome-shell 在 `do_timerfd_settime` 卡 26s**（lr 在 hrtimer 设定路径）→ 恢复后跨核定时器协作类丢失唤醒，非 SCMI handler 死循环（handler 无循环）
- **panthor 嫌疑已排除**：cmdline 拉黑 `panthor_init`（桌面纯 llvmpipe）后新快照 restore 照样 guest 160s 死
- SMP=1 restore 不可测（快照按 8 核建，loadvm 拒载）
- 待办二分：stash QEMU 改动 → 旧二进制重建快照 restore 对照，定「二进制回归（SMCCC/SCMI）」还是「快照内容时点」

## 6. 挂账 2：桌面×panthor 冲突（M1 领域）

renderD128 存在后 mutter/GNOME 的 EGL 初始化去开它，卡死在未实现的 CSG/queue
ioctl 上：`org.gnome.Shell@gdm.service` 20s 循环崩、VOP 无帧（快照 create 等首帧
超时实锤）。临时解：snapshot.py cmdline 加 `initcall_blacklist=panthor_init`
（sim-only bootargs 自由度，同 smoke.py FAST 档先例；M1 ioctl 打通后撤）。
panthor 研究流走冷启（diag 脚本已顺）。

## 7. M1 展望（下一役）

1. `eglinfo -B`（surfaceless + MESA_LOADER_DRIVER_OVERRIDE=panfrost）——note 76
   §3.4 的 M1 验收；会依次踩 CSG/queue/BO 的 ioctl 族（group create/start、
   tiler heap、fence），影子按 panthor_drv.c ioctl 表补
2. latest_flush ID 页（0x10000）、watchdog PING 的周期 ACK、CSG/CS 生命周期
3. 真机 fixture 补采（CORE_FEATURES/REVID/COHERENCY/THREAD/TEXTURE——note 76
   §六.2 的一次性 debug dump）
4. restore 锁死二分（§5）

## 8. 落库清单

- `third_party/qemu`：target/arm/cpu.h + tcg/psci.c（SMC 钩子）、hw/arm/rk3588-lite.c（scmi 段 + gpu 段：fixture/电源/IRQ/AS/JOB/MMU/MCU/doorbell + vmstate + diag 属性 gpu-reads/gpu-unknown）
- `sim/qemu-sim-machines.patch` 重导（18 文件）
- `sim/snapshot.py`：cmdline 拉黑 panthor_init（§6，M1 后撤）
- 快照已用最终二进制重建（restore 不稳挂账 §5；桌面可用、秒回不可靠）
