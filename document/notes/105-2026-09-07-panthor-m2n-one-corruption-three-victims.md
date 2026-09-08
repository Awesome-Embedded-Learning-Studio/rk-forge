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


## 5. 追加定谳（同日终段）：病分两种 + 图集越界实锤

- **病一号（功能性）已治**：NOWRITE 轮 shell 死于 **SIGABRT——
  Gjs function.cpp:1014 assertion (1==2)**（ubuntu-dock 扩展的
  gjs/GI 兼容破绽，与 GPU 模型无关）。`ubuntu-dock@ubuntu.com`
  已在镜像内改名禁用（**改的是 rootfs 不在 git**）——禁用后
  NOWRITE 轮 **gnome-shell 全程存活** ✓
- **病二号（腐蚀）图集分量实锤**：panthor debugfs **gems** 表
  （/sys/kernel/debug/dri/1/gems，per-BO 真值！）给出 512² 图集
  Render target BO=**1,073,152B**；旧线性 body_base 写
  [0x20000,0x120200) **越界 106KB**=腐蚀根源（此前 WnR=1 内核写
  伪指针 0x00492768_00492790=两像素拼装，受害者为内核 slab/共享页
  随机）。紧式 body_base（4K 对齐头区）已上——图集写界内可证
- **崩溃未止**（紧式后 326 raster 仍崩）→ 下一个越界者：**壁纸
  3840×2160 BO**（AFBC 压缩率 modifier 分配，真实大小 < 裸 33MB，
  我的未压缩 body 写溢出）。同一 gems 方法可测——需要一轮活到
  壁纸加载后的 boot（NOWRITE+无 dock 可活）
- **方法论闭环**：gems 真值 → body 钳制 → 逐 BO 消灭；gpuvas 表
  （VA↔BO 映射）也已就位可做 VA 侧对账

## 6. 战役状态

受控 11/11；shell 存活问题已治（dock）；腐蚀=逐 BO 越界（图集
已钳，壁纸待测）；core 陷阱+双病分流+gems 方法=下轮弹药全齐。


## 7. 追加（次日续）：界内全证 + NULL 重开

- **壁纸 BO 真值**：47,149,056B（45MB，**mip_count=11** 全 mip 链；
  L0 裸 33MB）——我的紧式 L0 写 33.7MB 界内 ✓
- **2GB 崩溃转储对账**（sim/logs 持久化后首轮）：壁纸写界后页全零
  ✓ 无溢出；图集界后 [0x104000,0x106000)=真布局自身数据（真实
  body 起点=0x6000 非我的 0x4000——内容偏 0x2000=图像瑕疵，
  非系统腐蚀）
- **崩溃 boot 全写手审计**：GPUFBG=0、GPUBLIT=0——唯一写手=rjob
  提交（326 图集+1 壁纸+图标），全部界内
- **PID1 死因重开**：本轮签名=**NULL+0x40 解引用**（逻辑 NULL，
  非毒页投毒形态）——systemd 某调用链拿到 NULL 即用。与早轮
  "内核 WnR=1 写像素伪指针"（真腐蚀形态）并存=**多机制或两病**。
  候选：GPU 模型异常状态→uevent/error 路径→systemd 设备管理
  NULL 解引用
- **resboot 日志已迁 sim/logs/**（仓库内，/tmp 清洗免疫）
- 下轮：journalctl 里 systemd 死前最后动作 + NULL 的提供者
  （udev/panthor uevent？）；受控复现 FSQUAD 轮只跑 10s 短窗
  （129s 前）逐步放钱
