# Note 105 · panthor M2n：一腐蚀三受害者——崩溃形态大统一

日期：2026-09-07 · 战役七第二十四篇 · 上一节：note 104（panic 考古）

## 0. 摘要

拿到决定性现场：**PID 1（systemd）自身 SIGSEGV → "Attempted to
kill init" panic**（el0_da 完整内核 trace）。与 gnome-shell
background.js SEGV（note 104 §9）、内核 NULL/lockup panic（note 104
全矩阵）并案——**同一腐蚀的三个受害者**，谁先碰到毒页谁死：

| 受害者 | 崩溃形态 | boot 占比感 |
|---|---|---|
| systemd（PID1） | el0_da→kill init→整机 panic（137s 即死） | 部分 boot |
| gnome-shell | background.js:488 SEGV→会话解体 | 部分 boot |
| 内核结构 | NULL/garbage 指针 deref→watchdog lockup | 部分 boot |

受害者随机性解释了崩溃签名的多样性（此前每种形态都被当成独立
线索追）。共同窗口：会话启动段（gdm 拉起、GPU burst）。

## 1. 现场证据（本轮 boot）

```
Kernel panic - not syncing: Attempted to kill init! exitcode=0x8b (=139=SIGSEGV)
CPU: 1 UID: 0 PID: 1 Comm: systemd
Call trace: do_exit ← do_group_exit ← get_signal ← arch_do_signal_or_restart
            ← exit_to_user_mode_loop ← el0_da ← el0t_64_sync
```

- exitcode 0x8b=139=128+11 实锤 SIGSEGV
- init 收到 SIGSEGV = 其自装的 handler 也崩了（double fault →
  force_sig → 直杀）——**core dump 被此路径跳过**（/root/core.*
  未落，debugfs 读 rootfs.ext4 验证）
- 机制推论：腐蚀页=**多进程共享的 file-backed 页**（page cache 的
  libc/代码页谁碰谁死）或任意进程私有页；内核形态=直接命中内核
  内存。共享页假设与"受害者随机"高度吻合

## 2. 嫌疑收口（承接 note 104：rjob 提交写有罪）

- rjob 写的 PA 偶发错误（stale-AS 单映射：VM 销毁不清 as_transtab，
  unanimity 检查不触发——错的唯一映射被放行）
- **下轮首刀：AS 代际取证**——as_transtab 每次更新打 generation，
  rjob enqueue 记录 {bp, 命中 AS 号, gen}；崩后比对致命 job 的 AS
  是否 stale（低代际）。若实锤：VM 销毁清 as_transtab 即根修
- 备选：页共享假设可用崩溃时 dump 的毒页内容反向验证（page cache
  页有文件内容特征）

## 3. core 陷阱状态

- 已武装：sysctl.d（/root/core.%p）+ systemd DefaultLimitCORE=200MB
  （rootfs 内，**不在 git**；rootfs 剩 364M——cap 必要）
- PID1 受害轮永远无 core（force_sig 跳过）；**shell 受害轮会有**
  ——多 boot 重试直到 shell 先死即可捕获；宿主 debugfs 直读
  rootfs.ext4 抠 core（免串口传输，本轮已验证 debugfs 可用）

## 4. 本日纵深（note 101-105 一天）

受控 11/11 → 异步化 → 10+ boot 矩阵四论证伪 → NOWRITE 写有罪 →
用户态镜像 → 壁纸上载链通 → 三受害者统一。剩余：AS 代际取证
（小时级）→ 根修（清 stale AS）→ 桌面可见冲刺。
