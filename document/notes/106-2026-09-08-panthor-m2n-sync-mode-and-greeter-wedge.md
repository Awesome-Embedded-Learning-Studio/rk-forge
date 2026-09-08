# Note 106 · panthor M2n：SYNC 稳定写模式 + 毒=异步机制 + greeter 僵局

日期：2026-09-08 · 战役七第二十五篇 · 上一节：note 105（界内全证+NULL 重开）

## 0. 摘要

**矩阵缺格填上，写内容全面无罪**：`FSQUAD_SYNC=1`（raster 内联同步
跑完，零延迟混淆）+ 紧式 body = **561 job 全程稳定过会话启动段**。
同地址、同内容、同量的写——同步稳、异步崩 ⇒ **毒=异步机制本身**
（BH 延迟/完成面时序），非写内容、非越界（与 note 105 界内全证
互印）。**SYNC 成为 M2n 稳定工作形态**。

## 1. 判别矩阵（终版）

| 模式 | 写 | 延迟 | 结果 |
|---|---|---|---|
| FSQUAD=0（无 dock） | 无 | — | 稳（5min+，shell 活） |
| NOWRITE | 无（快跳） | 微 | 稳 |
| **SYNC + 紧式** | 有（内联） | **零** | **稳（561 job）** |
| ASYNC + 紧式 | 有（BH 分片） | 毫秒级 | 崩（~326 job，PID1/lockup） |

异步与同步的差异面：①completion 挂起（保序队列放行时机）
②BH 上下文写 ③vCPU 在片间运行观察半成品缓冲。下一刀=async-去
hold（立即完成+raster 继续）二分 ①与②③。

## 2. greeter 僵局（显示点不亮的直接原因）

- SYNC 稳定轮：会话 shell（--mode=ubuntu）启动 12s 后 DisplayConfig
  连接关闭（又崩了一层）→ gdm 回退 greeter（--mode=gdm，存活）
- greeter 认卡（card0 atomic ✓ selected primary ✓）但 **DSI-1
  enabled=disabled、CRTC 全静、KMS 线程 do_sys_poll 等事件**；
  gnome-session/idle-monitor 等 DBus 接口**全部 25s 超时**=greeter
  主循环卡死（非崩溃）
- 手动 `echo add > sys/.../DSI-1/uevent` 无效——不是热插拔缺失
- 疑点（下轮首刀）：mutter 首帧 pageflip/vblank 事件路径——
  原子提交后等翻转完成事件，VOP 模型的中断/事件未达则永久等；
  战役五形态（llvmpipe+rockchipdrm 原子翻页）曾经工作，需对比
  该路径差异（panthor 内核/启动参数 drm_client_lib.active=none？）

## 3. 持久化 journal 方法（本轮另立）

- journald conf.d：Storage=persistent + SyncIntervalSec=5 +
  **Compress=no**（RAM 中明文）→ 崩溃后 pmemsave 转储里
  `MESSAGE=` 正则直读（本轮 1053 条复活）
- 但磁盘 journal 会跨 boot 旋转，-b -1 不可靠——RAM 明文法为准

## 4. 工作形态定稿

- **受控**：净机 FSQUAD=1（11/11）
- **GDM 稳定写**：`FSQUAD=1 FSQUAD_SYNC=1 GDM=1`（本轮验证）
- 崩溃研究：默认（异步）；NOWRITE=零写对照


## 5. 追加：greeter 僵局第一层剥开（活机 strace/loginctl）

- **KMS 线程**：ppoll(eventfd + /dev/dri/card0)——等 DRM 事件 ✓ 正常
- **主线程**：6s 零系统调用=卡死在 futex（JS/GLib 层）
- **logind 会话态（僵局第一层）**：`c1 gdm-greeter seat0 tty1
  Active=NO`——会话从未激活！`loginctl activate c1` 成功置
  Active=yes，但老 shell 已错过初始化窗口不回头；pkill 踢壳未生效
  （进程 1036 存活）。会话激活缺位的最可能机制：console=hvc0 下
  VT1 从未成为前台（logind 的 VT 激活路径）——**GDM 机 bootargs
  常规化（去 console=hvc0 或加 VT 自动切换）是下轮一刀**
- 修正认知：DBus 全超时=shell 主循环卡死的下游；主循环卡死的
  触发层（等 session-active？）与激活实验兼容但不充分——需要
  bootargs 修正后 fresh 轮验证（若 shell 从头就 Active 则初始化
  一次通过）
