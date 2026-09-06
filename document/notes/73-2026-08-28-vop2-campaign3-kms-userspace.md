# 73 — VOP2 战役（三）：KMS 用户态解放、gdm 上机与屏幕狩猎（2026-08-28）

> 战役二把 DRM 管线点亮到 `Initialized` 后，首个 modeset 死锁。本役绕开死锁
> 解放 KMS 用户态路径，**gdm（GNOME Display Manager）在仿真里启动**，并建成
> 屏幕截图管线（VOP 扫描输出 → QEMU monitor → PNG）。桌面竞态仍在狩猎中。

## 0. 结论

| 项 | 结果 |
|---|---|
| fbcon 死锁根因链 | modeset 提交的 flip_done 依赖 FS_FIELD 中断，而 runtime PM `put_sync` 后 ISR 在 `pm_runtime_get_if_in_use` 处秒退；TCG 时序下 spurious-disable 后中断静默 → `drm_crtc_commit_wait` 永等（gdbstub 全核取证：8 核全 idle，无自旋死锁——是事件永不来） |
| **fbdev client 绕过** | ✅ `drm_client_lib.active=none`（模块名 `drm_client_lib`，此前 `drm.active`/`drm_client.active` 均无效）→ 系统完整存活到 shell + 干净关机，`card0-DSI-1` connector 在位 |
| **Ubuntu + DRM 共存** | ✅ rootfs 模式两断言 PASS；`Started gdm.service` + `Reached target graphical.target`（GNOME Display Manager 仿真首启） |
| **fb 导出 + 截图管线** | ✅ VOP 影子扩到 0x4000（窗口寄存器在 0x1000+，此前只 0x1000 全打到毯子）；Cluster0-win0 YRGB_MST/DSP_INFO/VIR 走 qom 属性导出；`sim/fbdump.py`（monitor qom-get + xp → 纯标准库 PNG） |
| 竞态欠账 | genpd_power_off 工作队列互锁 → hung_task 恐慌（guest 124s，约 8 成概率）；一次竞态幸存者跑到 login+gdm；mem chain 镜像（0x1f0/0x1f8）与 sysctl 参数未根治；自动化狩猎循环已部署 |

## 1. 取证工具箱（本役沉淀，皆入 sim/）

- `gdbfreezegrab.py`：纯标准库 GDB 远程协议客户端，盲扫 vCPU 1..8 读
  PC/LR/SP → addr2line。本役用它拿到「8 核全部 arch_cpu_idle」的关键裁决。
- QEMU monitor 速记：`info registers` 只给单核；gdbstub `qfThreadInfo` 只报
  1 线程（盲扫 1..8 才全）；`xp` 用物理地址（KIMAGE 区符号 virt-0xffff800080000000）。
- `fbdump.py`：屏幕截图（见上）。三个寄存器含义：YRGB_MST=fb 物理地址、
  DSP_INFO=高[28:16]/宽[12:0] 打包、VIR=每行字节数/4。

## 2. 死锁的完整解剖（供战役四直接开工）

```
drm_client_modeset_commit（fbdev 首个 modeset）
  → drm_atomic_helper_wait_for_dependencies → drm_crtc_commit_wait（等 flip_done）
  → flip_done 需要 ISR 的 FS_FIELD → drm_crtc_handle_vblank + send_vblank_event
  → 但 vop2_crtc_atomic_disable 尾部 pm_runtime_put_sync 已挂起设备
  → ISR 第一行 pm_runtime_get_if_in_use==0 → return IRQ_NONE
  → 电平中断反复 pending/秒退 → 内核 spurious 检测 disable 该 IRQ → 全静默
```

**真硬件为何不挂**：fbdev 提交链在真机微秒级完成，put_sync 尚未发生/或
vblank 已在手。**TCG 时序差**是根因（与 SOAK 教训同族）。候选根治：
autosuspend 延迟拉长（真板无害）、或 flip_done 的无中断兜底路径。

## 3. genpd 竞态（当前狩猎目标）

gdm 启动路径上 `genpd_power_off_work_fn`（PD 下电）与 modeset 持锁互锁，
hung_task 60 秒后恐慌（CONFIG_BOOTPARAM_HUNG_TASK_PANIC=1 且无 cmdline 参数
可关——`hung_task_timeout_secs` 被内核拒识，`sysctl.kernel.` 前缀实测无效）。
已试：mem chain 镜像（0x1f8←mem_pwr 同极性、0x1f0←~mem_pwr）未见效。
**约 2 成概率竞态幸存**到 login+gdm——狩猎脚本（多 boot×多 dump）自动化抢截图。

## 4. 复现

```bash
# KMS 用户态 + gdm（需要 rootfs.ext4 独占；竞态可能 124s 恐慌，重试）
QEMU=... python3 boards/rk3588-topeet/sim/smoke.py rootfs --check   # 绕过参数已固化
# 截图（另一终端，QEMU 带 -monitor tcp:4444）
python3 sim/fbdump.py screen.png
# 冻结取证（QEMU 带 -gdb tcp::1234）
python3 sim/gdbfreezegrab.py
```

## 5. 挂账

fbcon 原生路径根治（autosuspend/无中断 flip_done）、genpd 互锁根因、
SPI 行为模型 + rk806 PMIC（GPU 等它）、真 PL330、SCMI、MSYS2。
