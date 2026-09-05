# Note 89 · panthor M2f：JOB_IRQ bit19 —— 十五分钟 brownout 的真凶

日期：2026-09-05 · 战役七第八篇 · 上一节：note 88（M2e 控制流+AS 绑定+user-doorbell）

## 0. 摘要

M2e 收官后 mutter 持续负载 ~11min 出现 RCU stall 形态的停摆（note 88 §欠账）。
本轮定界推翻"TCG 饥饿/反馈环"两个候选，真凶是 **M2a 时代埋在完成面里的一个
移位 bug**：JOB_IRQ 置位时把 CSG 控制页的**物理地址**当 VA 减基址再移位，
AArch64 `LSL` 对 32 位移位按 mod 32 折叠 → 每次消费稳定落 **bit 19**。内核
`csg_slot_count=8`（blob group_num=8，本轮 GLBCTL 探针实测），19 ≥ 8 →
`sched_process_csg_irq_locked` 的 `drm_WARN_ON` ×67，每次带着 scheduler 锁
走全栈打印 = 15 分钟级别的 brownout（串口假死、命令 60-90s 才回、RCU 报文）。
修成显式 slot 序号 + CSG 存活门后：**零 WARN、4.7 doorbell/s（旧 0.25）、
mutter 并发负载下 glClear 4× PASS**——M2e 的并发像素验收欠账就此收官。

## 1. 现场（复现机：GDM 腿，GPUDBG 带墙钟）

| 证据 | 数值 | 含义 |
|---|---|---|
| 消费节奏 | dt 中位数 5038ms，滴答级规律 | 不是风暴，是 5s 周期环 |
| vCPU host 占用 | 8 核全部 ~5% | **不是**自旋/TCG 饥饿 |
| gdb 全栈 | 8 核全在 `cpu_do_idle` | 内核无任务卡死 |
| marker 往返 | 一度 60-90s，后自愈到 0.1s | 系统活着，深慢 |
| guest 时钟 | ≈1:1（漂移在噪声内） | 不是时间膨胀 |
| dmesg | `WARNING: panthor_sched.c:1789 drm_WARN_ON(csg_id >= csg_slot_count)` ×67 | 唯一异常 |

关键推理链：模型日志显示只置过 slot 0/1 → 数学上 WARN 不可能 → 反推
`csg_slot_count` 或者"位置的不是 0/1"必有一个假设错 → 检查置位代码发现
PA/VA 混用。

## 2. 根因解剖

```c
g->job_rawstat |= 1u << ((csg_ctl - 0x04001000) / 0xa0);   /* M2a 版 */
```

- `csg_ctl` 是 `rk3588_lite_gpu_va_pa()` 的返回值——**物理地址**（如 0x622d000）；
- `(0x622d000 - 0x04001000) / 0xa0 = 0x37553`，C 标准里 `1u << 0x37553` 是 UB，
  x86-64 上按 mod 32 → 19（实测稳定）；AArch64 `LSL Wd` 同样按寄存器宽度取模；
- 于是每次真消费都拉 CSG 事件 bit19 → `process_fw_events_work` 拿 `ffs` 取出
  csg_id=19 → WARN 早退（该位没被正常路径清）→ IRQ 处理循环反复;
- 每发 WARN：scheduler 锁 + `__warn_print` 全栈符号化（TCG 下秒级）×67
  ≈ 十几分钟 brownout。mutter 的 5s 渲染滴答（dt=5038ms 的来源）在期间
  依然断续推进——所以 ins 一直单调涨、串口 echo 活着但输出被拖死。

**为什么 M2a-M2d 都没炸**：那时 CSG 活得短（probe/gc.py 单组单发），WARN
偶发一两发淹没在日志里；M2e 的 user-doorbell 修复让长跑组持续消费后，WARN
按消费速率连续引爆。note 88 记的"多跑楔死不是 M2e 引入"依然成立——它只是
把 M2a 的旧雷持续踩响。

## 3. 修复（hw/arm/rk3588-lite.c）

1. **bit 索引正名**：`cs_consume()` 增加 `unsigned csg` 参数，两个调用方
   （doorbell(1..8) 传 `id-1`，doorbell(0) sweep 传循环变量）显式给 slot；
   `job_rawstat |= 1u << csg`。
2. **CSG 存活门（防 blob 垃圾页假消费）**：sweep 里按 req 状态机推
   `csg_live`——`state==START/RESUME` 或带 `ENDPOINT_CONFIG/STATUS_UPDATE`
   置活，`state==TERMINATE(0)` 且无配置位清活，`SUSPEND(2)` 保持。非活槽
   不消费 ring（只跳过）。blob 静态控制页的随机 VAs 从此最多影响幂等追平。
3. **GLBCTL 探针**：mcu_boot 时打印 glb control 的 in/out VA 与
   `group_num/stride`（runtime 权威值，`0x04001000` 起的 8 组是 blob 铺的）。
4. GPUDB/CONSUME 打点带墙钟 ms 与 dt（本轮主力取证工具）。

`csg_live` 进 vmstate（快照线不受影响）。

## 4. 验收（GDM 腿，panthor 在，8 核）

| 项 | 结果 |
|---|---|
| GLBCTL | `in=4002000 out=4006000 group_num=8 stride=a0` |
| WARN（dmesg grep WARNING.*panthor） | 0（旧 build 同期 67） |
| RCU stall / hung | 0 |
| 消费流 | 1119 消费 / 508s，doorbell 4.7/s（旧 0.25/s，18×） |
| CSG 分布 | slot0 ×1109、slot1 ×2、slot2 ×8（全在 8 槽内） |
| glClear（mutter 并发） | **PASS ×4**（1 发 + 3 连发，VERDICT 全 PASS） |
| 串口 | 命令全程可回（无 60-90s 假死窗） |
| 桌面画面 | 仍全黑（clear-only 边界不变，note 87 §5） |

取证工具沉淀：`/tmp/sercmd2.py`（$/# 双提示符 + 末三行判定韧性版，WSL /tmp
被清后按 sim/sercmd.py 手工重建）；host 侧 gdb 走
`/opt/arm-gnu-toolchain-15.3.rel1-x86_64-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-gdb`
+ monitor `stop` + `gdbserver tcp::1234` + vmlinux（装不了 gdb-multiarch 的
替代路径）。

## 5. 边界与下一步

- brownout ≠ 死锁：自愈过一次（WARN 风暴停了就恢复）。bit19 修复后未再复现。
- 串口短输出偶发丢失（`wc -c` 级别的单 token 会蒸发，多行反而稳）——tty
  层怪癖，取证时用 md5/多行核对，不影响判定。
- 大文件进 guest：3KB 单行 base64 会被 tty 截断（2004/2411），heredoc 多行
  能跑但 md5 会变（行尾/空白级失真）。长期解法：烧进 rootfs 镜像（debugfs
  直写 ext4 免 sudo，待用）。
- M2g 候选（不变）：shader/tiler 深水区（RUN_FULLSCREEN(8)/IDVS(6) 最简 DCD
  纯色 quad）是桌面可见的唯一路径；真机 fixture 补采、PANTHORIOCTL 内核
  打点撤除仍挂账。
