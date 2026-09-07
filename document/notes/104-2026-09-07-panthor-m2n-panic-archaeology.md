# Note 104 · panthor M2n：kernel panic 考古（失败矩阵与候选根因）

日期：2026-09-07 · 战役七第二十三篇 · 上一节：note 103（合成链+异步化）

## 0. 摘要

GDM 机 FSQUAD 全开的 kernel panic 做了 7 轮启动矩阵：**5/7 崩溃，
崩点恒在会话启动段（~127-152s），与 sync/async、cap 有无、body
数学无关**——note 103 §2 的"host NMI 硬锁死"与"body 越界"两论均被
证伪（异步分片后仍崩、收紧 body 后仍崩、cap 在位仍崩）。崩溃为
概率性，与 raster 活动总量相关。两个存活根因候选浮出。

## 1. 失败矩阵（7 轮启动）

| # | raster 形态 | cap | body 数学 | 结果 |
|---|---|---|---|---|
| 1 | 同步 | ≤1920×1080 | 线性 | 330s 稳定（当时以为定论） |
| 2 | 同步 | 无 | 线性 | ~130s 崩（DABT） |
| 3 | 同步 | 无 | 线性 | ~128s 崩（NULL+lockup） |
| 4 | 异步 BH | 无 | 线性 | ~128s 崩（10 done 后） |
| 5 | 异步 BH | 有 | 线性 | 240s 稳定（运气） |
| 6 | 异步 BH | 有 | tiled 收紧 | ~143s 崩 |
| 7 | 异步 BH | 有 | 线性（回滚） | ~150s 崩（441 done） |

共同点：崩点都在 mutter 会话启动重负载段（nautilus/gjs 拉起、字形
图集 BO 高频重建）；FSQUAD off 同段稳定（对照已做）。

## 2. 候选根因（按嫌疑排序）

1. **AS 重配置期误译**：会话启动 = CSG 拆建高频，cur_as 可能瞬间
   陈旧 → va_pa_bound 给错页 → 1MB 级写入打中任意内存。与概率性、
   与启动段强相关吻合。刀口：写前双翻译交叉验证（bound+lenient 不
   一致即弃权）+ 崩溃时 dump cur_as/AS 表版本。
2. **异步 UAF 竞态**：fake-completion 先于 raster-done，mutter 在
   fence 后释放 BO → 内核复用该内存 → 迟到的 BH 写穿新主人。刀口：
   completion 挂起到 raster-done（fence 语义对齐；需 completion 队
   列保序）。注：同步版也崩过（#2/#3），若确认则两因并存。
3. body 落点错误（tiled 真实布局未知）：收紧式反而崩（#6 vs #5
   撞运气），真身待硬证据（受控 512² 图集可做变体实验）。

## 3. 已落地资产（全部 commit）

- **异步分片 raster**（BH 128 行/片、16 sb 行/片，片间让出 BQL）
  ——受控矩阵 11/11 PASS（含 gt/gc 回归）
- `rk3588_afbc_body_base()` 助手（线性式为当前稳定形）
- 失败矩阵取证链：raster-done/bp 打点、spanfail、busy-drop、
  consume PA/stride、VOPSCAN
- 稳定工作形态：净机 FSQUAD=1（受控全绿）；GDM 机研究=FSQUAD off

## 4. 下轮刀口（按性价比）

1. 写前双翻译交叉验证（小时级，先堵嫌疑 1）
2. completion 挂起对齐 fence（天级，堵嫌疑 2）
3. 512² 图集 body 落点变体实验（受控、可判别嫌疑 3）


## 5. 追加轮次（同日三轮）：嫌疑收窄到 raster 提交写

- **NOWRITE 判别**（FSQUAD_NOWRITE=1：采样/配对/hold 全跑、提交跳
  过）：**稳定过会话启动段**（827 job）——写有罪定谳
- **completion 挂起**（保序队列，fence 对齐 raster-done）：机制全跑
  通（325 hold）但崩溃依旧——UAF-completion 论证伪
- **全 AS 一致性写翻译** `va_pa_write()`（歧义即弃权）：2 稳 1 崩
  （as-ambig 从未触发）——AS 歧义论证伪；稳定性为运气波动
- Round-3 现场：无 3840 写（spanfail 拒+try_blit 零命中）、431 个
  atlas/图标 raster 后 NULL deref+lockup——**try_blit 合成写亦无罪
  （NOWRITE 轮它照跑）**，嫌疑唯一收敛到 rjob 提交路径
- 逻辑排除后 rjob 写的疑点：bf=13 tiled header 曲线（atlas 实际写
  聚集在 [0,0x2400]+少量 body，量级极小）与 bf=12 图标写（与
  try_blit 同式）——数学上均看不出越界，需要**写日志+金丝雀**级的
  取证（每笔 (bp,span) 记录 + 崩后邻域比对）才能定谳

## 6. 工作形态定稿（本 note 时点）

- 受控（净机）：FSQUAD=1 全绿（11/11）
- GDM 研究：**FSQUAD_NOWRITE=1**（全链路跑、零写风险）或 FSQUAD=0
- 下轮第一刀：rjob 提交写日志 + 金丝雀页扫描；第二刀：512² 图集
  BO 真实大小硬测量（mesa 克隆已失，note 97 §3 重克隆+pan_image
  尺寸链）


## 7. 追加（同日三段）：窗口计时 + 文字行复现 + 壁纸上载活

- **rjob 窗宽取证**（enqueue→done 墙钟）：常态 6ms，最大 377ms（=
  3840×2160 壁纸上载 job 本身）——距 5s JOB_TIMEOUT_MS 两个数量级，
  **job 超时论也不列强嫌**（除非极端主循环阻塞，如取证 pmemsave
  的 4 分钟——那是自找的）
- **崩溃率更新**：最近两轮 writes-on 启动存活（含撤上限轮）——
  10 轮 6 崩 4 活，纯概率；不再声称任何"稳定配置=写安全"
- **壁纸 3840×2160 上载 raster 完成**（win=377ms，bp=2ea00000）——
  上载链通了
- **文字行复现但随后定谳为 simpledrm 启动控制台**：701px @640×480
  （坐标同 note 102）重现，但本轮 **VOPSCAN 零输出=我的 VOP scanout
  从未运行**，console surface 的内容是内核 simpledrm 早期启动控制台
  的残留（rockchipdrm 未接管显示）——**非 GPU 输出**。note 102 的
  "来源未验证"就此定谳（两轮同坐标=同一解释）。GPU 侧链路（图集
  raster✓壁纸上载✓）在显示管线未接管的 boot 里到不了屏。
- 取证装备新增：LOGLEVEL 环境变量（resboot）、GPUWRITELOG、
  win=ms/SLOW-WINDOW、pmemsave 全转储+日志环搜索（2GB 可行；
  monitor 需  清行+引号路径——HMP echo 污染坑）

## 8. 下一步

1. **显示管线接管率**：VOP mode-set（VOPSCAN>0）只在部分 boot 发生
   ——多 boot 采样统计接管条件；无接管=GPU 渲染再好也上不了屏
2. mutter 会话状态漂移：多 boot 采样 1920 下采样/合成 draw 出现
   条件（或主动触发桌面活动：打开应用/窗口）
3. 崩溃概率分布再采样（现 6/10；区分 boot 期 vs 会话期）
