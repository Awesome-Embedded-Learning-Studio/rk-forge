# Note 114 · panthor M2n：参照图错案 + 快照三门投票——脸区悬案的主体破案

日期：2026-09-12 · 战役七第三十三篇 · 上一节：note 113（校验武器化）

## 0. 摘要

**脸区悬案的主体破案：参照图根本是错的。** greeter 实际显示的壁纸是
`warty-final-ubuntu.png`（rootfs 构建日落盘、gdm 默认），而 note 110-113
一路用 `cnusr25-Simple_Raccoon_Dark.png` 当判据——两者同为暗紫色系
（背景块差 22-25 "接近但永不过线"），脸区自然"全变体全读法不匹配"。
span dump 铁证：staging 内容 vs warty **原位逐字节 mad=0.00、delta=(0,0,0)**。
顺带翻案："greeter 调光 -10" = 两壁纸的色差（换对参照后 offset=[0,0,0]）。
修复快照链两处后：**结构域 st_p50=25.2 首次过线（≤40）**，色偏归零；
剩 bg_p90=33.7——顶带存在 ~240×240px 图像块的 2D 置换（块内完好），
y 置换来源已定界为两假设（见 §5）。

## 1. 破案链（工具全部落库）

| 步 | 证据 | 结论 |
|---|---|---|
| STGDUMPFACE（脸区 6MB+逐 AS 翻译） | reg1 翻译=+704MB foreign；reg2=+2MB 恒移；strips-hex 见 UTF-16 文本 | 线性 PA 读在 12MB 后越界到别人的页；"稳定结构化数据"=外来内存 |
| gems（串口） | 全 VM 仅一个 >10MB BO：45MB AFBC(mip11) 3840×2160=壁纸纹理本体；另 10×2MB tiler heap | 33MB 线性 staging 是短命上传 BO，画完即释放回收（十块 tiler heap≈回收页） |
| pmemsave 15min 后重读同 PA | 80.5% 字节已变 | staging 生命周期 << 帧间；extract 时刻是唯一采样窗 |
| **STGDUMPSPAN**（34MB 整段+0-34MB 每 1MB 翻译 delta） | span.0 行识别：**行 50→ref 50 mad=0.00**；换 warty 参照后 300/700/990/1300/1700 全部原位 mad=0 | **staging=warty 原位字节精确**；cnusr25 参照时代的一切"不匹配"作废 |
| gsettings（串口）+ 文件时间戳 | 用户级 picture-uri=adwaita-timed.xml（文件不存在）；warty-final mtime=rootfs 构建日 | greeter 背景=warty-final（Ubuntu 默认链），非 cnusr25 |

## 2. 连环翻案清单（诚实账本）

- "背景像素级吻合 5-9"：两壁纸都是暗紫底，色差被当成"吻合"。
- "greeter 调光恒偏 [-11,-9,-10]"：**不存在**。正确参照下 offset=[0,0,0]。
- "脸区与全部 8 变体不匹配（65-188）"：测的 8 个变体不含 warty。
- note 112 "STGCROP 完美/MCP 圆眼三角鼻"：MCP 幻觉（已定谳）×错误参照双重污染。
- "tiled 快照更糟（bg_p90=92）"：以错误参照量化，结论存疑（方向未必错，数值作废）。

## 3. 修复一：快照三门投票（display 链 last-wins 根修）

症状：reg1（好快照）落地 15ms 后被 reg2（回收残页，nb6=15-64 不等）
无条件顶掉——注册路径先 `g_free(bg_screen); bg_screen=NULL`，任何后续
注册的 extract-snap 都"首样本"身份直通。修法（三门一致）：

- 注册处不再清空 bg_screen（候选与在位者竞争）；
- extract-snap：64 点非黑 nb6 **严格更优**才换（首样本须 nb6≥48）；
- stg-timer（+500ms 权威采用）同样改为投票制——BO 释放后的回收样本
  永远赢不了在位好样本；
- painter 的 nb6>old6 原有投票补写 `bg_nb6` 登记。

实测：`stg-extract-snap-rej nb6=64 (keep 64)`——reg2 垃圾被挡下。

## 4. 修复二：快照读路径 PA 线性→owner-AS 逐页缝合

extract-snap 与 stg-timer 原来直读 `spp/bg_pa + 线性偏移`。span-xlate
证明 staging 的 VA→PA 映射存在 2MB 段级恒移与 foreign 段（+704MB/+2MB
两形态），线性读在段界后拼进别人的页。两处均改走
`rk3588_tex_read_px`（内部逐页翻译+页缓存），AS 用注册期多点探针的
owner（bg_as）并带基址自证（同 painter 防线）。painter 本就走 tex_read_px。

## 5. 剩余悬案（已定界，下一号刀口）

现状：底 2/3 近乎完美（行带块差 1.6-1.9），顶带 avg 41-50。顶带 2D
块匹配显示 **~240×240 图像像素的块内置换**（每块内部 mad 0.5-2.9 完好，
位移散布 ±(120-450)px、含 dy）。staging 内存侧同构（span 行识别：
行 50 原位精确、行 300 foreign、行 700+ 行完好但 y 位移——**整行完好、
x 对齐、y 置换**）。且 +15ms→5s 采样恒定（sb 不变）= 不是上传竞速的
中间态，是终态。

两假设（对账可分）：

- **(a) 我们自己的 raster 写置换**：3840×2160 FBD 的 rt1=线性 3840×2160
  （VA 7ffff7c00000），我们的 rjob 经逐页翻译写它——若目标 BO 的
  VA→PA 是 2MB 段散布（136 行/段），写出的图像即 y 段位置换，其页被
  回收进下一代 staging 后表现为"整行完好但错位"。刀口：GPUWRITELOG
  scatter 审计 + 置换边界与 2MB 段界（136 行）的对齐检验 + 三个 3840
  FBD 的 rt PA 与各 staging PA 的包含关系表。
- **(b) mutter 双阶段上传**（CPU 写 staging1→GPU 拷 staging2）中我们
  对中间 job 的采样/写入语义错。刀口同上，看写者是谁。

辅助事实：greeter 合成会直接采样 AFBC 纹理（ptype=6 plane 出现在
pending 列表，头格式完好=我们写的）——线性→AFBC→采样回环自洽。

## 6. 仪器与脚本（全部纯标准库落库）

- `STGDUMPSPAN=<前缀>`：每次注册 dump spp 起 34MB + 0-34MB 每 1MB
  逐 AS 翻译 delta（-1=无映射），序号防覆盖。
- `STGTIMERDUMP=<前缀>`：stg-timer 每拍快照，序号化（原单文件覆盖）。
- stg-timer 节拍改 15/30/60/120/240→500ms 指数（上传前沿测量）。
- `sim/face_probe.py`（指纹/位移/MAD）、`sim/span_probe.py`（行识别：
  恒偏补偿全行搜索）、`sim/block_probe.py`（2D 块置换表）。
- 参照默认全部换 `warty-final-ubuntu.png`。

## 7. 判决记录（verify_screen.py，note 113 协议）

| boot | 形态 | verdict | offset | bg_p90 | st_p50 |
|---|---|---|---|---|---|
| 修复前（错误参照 cnusr25） | — | FAIL | [-10,-9,-9] | 22-25 | 62 |
| 修复前（正确参照 warty） | 黑屏（reg2 顶掉） | FAIL | [-101,-38,-72] | 70 | 66 |
| 三门投票+缝合 | warty3/4/6 | FAIL | **[0,0,0]** | 33.7 | **25.2** |

数值未 PASS——按验收协议**不宣称可见**，不邀人眼（等 §5 闭环、PASS
后再走两段式）。

（战役七链：…校验武器化✅→**参照错案破案+快照三门投票✓**→余=y 置换
来源（§5 两假设对账）/UI 层/字形）
