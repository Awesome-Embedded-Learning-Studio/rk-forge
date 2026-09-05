# Note 93 · panthor M2i 侦察：SRT 链三层挖掘（未竟，仪器落库）

日期：2026-09-06 · 战役七第十二篇 · 上一节：note 92（M2h 真 blit 像素）

## 0. 摘要

为把 blit src 从 last_img 启发式换成真纹理解析（M2i），对 SRT（Shader
Resource Table）链做了三层挖掘。**结论：链路比预期深，未完全破解；但
格式地图大幅推进，GPUSRT 取证仪器落库**。启发式 blit（note 92）继续
作为能力交付。

## 1. 已确证（v1 dump + 双对齐 A/B）

| 层 | 格式 | 证据 |
|---|---|---|
| SRT 基址 | `regs[4] & ~0x3f`（低 3 位 flag，64 对齐） | v0/v1 双 dump：v0 干净解析、v1 错位 |
| SRE 条目 | **16B**：`{addr56 \| tag(0x01<<56), size32}` | 4 项：{tex,0x40},{sampler,0x20},{0,0},{sampler?,0x20} |
| SRE→目标 | 0x40=纹理载体 64B（v10.xml 的 32B "Resource" 结构与内存不符——以内存为准） | sz==0x40 过滤 |

注意：v10.xml Resource 结构（32B、Size@w2、contains_desc@w1:24）与实测
16B 布局不符——mesa 26 的 SRT 打包用了别的路径（hw_runner 的 SRE 写法
与 xml 有出入），**以内存 dump 为权威**。

## 2. 未竟：0x40 载体层的迷宫

64B 载体的实测内容（跨 boot 不稳定）：
- 跑 A：w4=`0x10_00000019`、w5=`0x7ffffffd32c0`（指向 FBO A 邻域！）
- 跑 B：w5=`0x7fffffeba2c0`（指回 SRT 自身 -0x20）；其内容 =
  `00802081_00802081` 重复——**0x0080xxxx 是 MCU fw 私有堆 VA 模式**
  （csffw blob 同款），疑似占位/Null 描述符对。
- 既不是 v10.xml Texture（W/H@w1 应为 0x000f000f）也不是 Generic Plane
  直出。存在中间层或 per-lod surface 数组，尚未定位稳定字段。

## 3. 仪器（GPUSRT，随补丁落库）

RUN_IDVS 时：SRT 双原始 dump + sz==0x40 项的 64B 原文 + 二级跟随
（w5 → 64B → w4 surf → plane w2/w4）。下次会话直接从 dump 续挖，
不用再改代码。

## 4. 下刀建议（M2i 续）

1. **对 0x40 载体做结构对齐扫描**：在 FBO A 已知 VA（GPUFBG 的 base）
   附近反查——哪个描述符字段的值 == base VA，即纹理→image 的锚点；
   以锚点反推字段位（比对多 boot 的 dump）。
2. 或换路：**RUN_FULLSCREEN 的 DCD 直挂**（note 91：DCD=指令字段所指
   寄存器，链短一截）——blitter 的 fullscreen 模式可能绕开 SRT。
3. AFBC clear（64×64 FBO 前置）与 SRT 无关，可并行推进。

## 5. 边界

- M2h 的启发式 blit 在净机/GDM 双负载下稳定（note 92 验收），本侦察
  不影响现有能力。
- GPUSRT 只在 GPURUN 环境下打点，默认零开销。

## 6. 后续（同日）

锚点反查破案——plane 终点格式实锤、结构匹配落地，见 note 94。本文
"链未竟"推进为"链通、中间格式缺一环"。
