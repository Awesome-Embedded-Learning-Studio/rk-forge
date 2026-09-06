# Note 94 · panthor M2i：blit src 结构匹配——锚点反查破案

日期：2026-09-06 · 战役七第十三篇 · 上一节：note 93（SRT 侦察未竟）

## 0. 摘要

note 93 的 SRT 链迷宫被**锚点反查**一举破解：以已知 src 图像基址 VA 为锚，
扫 GPU 堆区（FBD±32MB，逐页穿表）找持有它的内存——全堆**仅两处**：
FBD 的 RT Writeback Base（已知）和 **0x7fffffffd000+8**——后者就是纹理
plane 描述符链的终点，实测格式：**64B，image 基址@+8、RowStride@+16
（2 的幂 0x400..0x100000）、尺寸@+24 高半=((H-1)<<16)|(W-1)**，位于
批池区（SPD_2=regs[20] 邻域）。据此实现 `find_src_plane`：SPD_2±0x8000
结构匹配扫描（尺寸==dst 且唯一命中）——**blit src 从 recency 启发式升级
为描述符结构定位**，gbf×2 + gc 全 PASS，GPUBLIT 标 `parsed`。

## 1. 锚点反查三轮（GPUANCH 仪器）

| 轮 | 窗口 | 命中 |
|---|---|---|
| 1 | SRT/FBD ±0x1800/0x800 | 单发：FBD+0xE0（RT1 Base，已知自明） |
| 2 | ±0x8000 + 模糊匹配（同页+低位 flag） | 仍单发——SRT 链不持有裸基址 |
| 3 | FBD±32MB 全堆 | **+0x7fffffffd000+8**（SPD_2 下 0x20，批池） |

命中处 64B 原文（飞机残骸）：
```
w0=00000420 0200011a  w1=00007ffffffe3000(基址!)  w2=0x400(stride!)
w3=000f000f 00000000(16×16!)  w5=00007fffffffc000(邻接资源)
```
SRT 链（note 93）的 0x40 载体 w5 指向本区——链是通的，只是中间格式
没对上；结构匹配绕开了中间层直取终点。

## 2. 实现（hw/arm/rk3588-lite.c）

`find_src_plane(center=regs[20], w, h)`：SPD_2±0x8000 逐页（va_pa_user
穿表）扫 64B 对齐候选，判据 = w1∈堆 VA 段 + w2 为 2 的幂 [0x400,
0x100000] + w3 高半 == dst 尺寸编码；**唯一命中才用**（多义=弃权回退）。
try_blit 顺序：parsed → last_img 启发式回退 → 弃。`blit_src_parsed`
计数（qom 可查），GPUBLIT 打 `parsed/heur` 标。

## 3. 验收（净机）

```
GPUBLIT 16x16 bf=1 src=15cc0000(parsed) dst=15cc2000 stride=400
GPUBLIT 16x16 bf=1 src=1589d000(parsed) dst=77c2000  stride=400
gbf VERDICT: PASS ×2 连跑；gc PASS；Bad page/WARN = 0
```

## 4. 边界与下一刀

- 结构匹配窗锚定 SPD_2（fragment 批池）——多纹理/多 RT 场景的歧义
  由"唯一命中"门挡住（弃权回退），代价是那些场景仍走启发式。
- w3 尺寸判据绑 RGBA8 假设（bpp=4 的 stride 幂次）；其他格式进门时
  会被尺寸/stride 判据滤掉（不误拷，只是回退）。
- M2j 候选：①把 SRT 0x40 载体→plane 的中间格式对齐（消掉扫描，换
  纯指针链）；②AFBC clear（64×64 前置）；③常量色 FS（桌面可见）。
- note 93 的"链未竟"结论被本篇推进到"链通、中间格式仍缺一环"。
