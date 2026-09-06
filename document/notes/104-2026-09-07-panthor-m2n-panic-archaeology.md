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
