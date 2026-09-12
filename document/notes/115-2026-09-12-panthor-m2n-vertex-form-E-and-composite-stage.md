# Note 115 · panthor M2n：顶点形态 E 破译 + 屏复合 stage 通道贯通

日期：2026-09-12 · 战役七第三十四篇 · 上一节：note 114（参照错案+三门投票）

## 0. 摘要

用户令"修正为对的+写死"驱动。GPUVERTDUMP 取证把 mutter 大纹理
draw 的**真实顶点格式**破译（顶点四形态→+1 形态 E），bg-fallback
满幅假设（越界读/写真身）从主力降为 1 次/boot；屏尺寸复合 draw 的
stage 快照通道全链贯通（solid 豁免+高度门+屏尺寸优先级），但复合
采样 AFBC 纹理的内容=62.6% 黑+亮斑——**AFBC 读写两侧 tiled 布局
不对称**为下一号刀口。受控 glestexture PASS、默认态 st_p50=25.2
无回归。verify_screen.py 默认参照写死 warty（note 114 定谳）。

## 1. 顶点格式破译（GPUVERTDUMP，fallback 触发时 dump 原文）

两种此前被 [-1,1] 门全挡的真实形态（**都是 32B 步长**）：

| 形态 | pos@+0 | +16 区 | 实例 |
|---|---|---|---|
| 缩放空间 | ±49.68/±29.05（∝屏比 1024:600，z@+8≈-50.4、w=ffffffff） | 零/1.0 稀疏 | 壁纸上传 draw（3840 FBD，采样 staging） |
| 像素空间 | (0,0)-(1024,600) | **归一化 uv 含 aspect-crop [0.0198, 0.9787]×[0,1]** | 屏复合 draw（采样 45MB AFBC 纹理→1024×600） |

- 顶点数=t2 array 条目 size 字段（qword 高 32 位，实测 128/116/112B
  =4×32B）——像素空间首顶点合法 (0,0)，不能拿零当缓冲尽头。
- 顶点序=triangle-strip（(−,+)(−,−)(+,−)(+,+)），v0.x=v1.x 过不了
  `f[0]!=f[4]` 门——须重建**规范角序**。
- 同 buffer 可含多 quad（满幅+条带），空间锚点=全 buffer min/max。

## 2. 形态 E 实现（rk3588-lite.c 顶点链第 5 形态）

32B 步长扫描（size 字段定数，NaN/越界断）→ 空间锚点=buffer min/max
→ 满幅守卫（quad 覆盖 ≥0.8 空间，条带弃权走原双维门防拉伸伪影）→
规范角序重建 → uv：+16 区像 uv（∈[0,1] 且非零）则用 buffer uv，
否则恒等映射（TEX_FETCH 像素 uv 预乘纹理尺寸）。实测 31-38 解析/
boot，`bg-fallback tex=3840` 从主力降为 1 次。

## 3. 屏复合 stage 通道（FSQUAD_STAGESNAP=1 门控，默认关）

复合 draw 的 stage[]=**屏内容本尊**（draw 自己的几何+裁剪 uv 采样
出的一帧），是最理想的 bg_screen 源。三处打通：

1. solid 豁免：屏尺寸（w==scan_w×h==scan_h）job 不走 solid 捷径
   （solid 会让 stage=NULL 断源）；
2. 高度门：`h>=768` 把 1024×**600** 挡了——改为 `h>=768 || scr_sized`；
3. 优先级：bg_snap_scr 位——屏尺寸 stage 可顶替非屏尺寸 stage，
   反之不许（上传 draw 的 3840 stage 会先到锁门）。

链路验证：`GPUW stg-snap 1024x600 from 1024x600 (screen)` 触发。

## 4. 剩余刀口：AFBC 读写 tiled 不对称

复合 stage 内容=62.6% 黑+亮斑（非壁纸马赛克）——复合经 tex_read_px
的 ptype=6 AFBC 路径读 45MB 纹理，而纹理由上传 job 的 rjob 提交写
（bf=13 AFBC Tiled）。读写两侧的 `rk3588_afbc_hdr(..., tiled)` 参数
或头/body 寻址不一致=读回黑。**下一号首刀**：对账 tex_read_px
AFBC 分支与 rjob bf=13 提交写的 hdr/body 公式（读写同参自证）；
修好后复合 stage 转正（默认开），屏=复合本尊输出。

## 5. 判决与回归

| 项 | 结果 |
|---|---|
| 受控 glestexture | **VERDICT: PASS**（形态 E 只在四形态全败后兜底=零回归面） |
| 默认态（无 STAGESNAP） | offset=[0,0,0] bg_p90=33.7 st_p50=25.2（与 note 114 持平） |
| STAGESNAP A/B | 复合 stage 上屏=p90 716（AFBC 读黑，§4）→ 默认保持关 |

（战役七链：…参照错案破案+三门投票✓→**顶点形态 E+复合通道贯通**→
余=AFBC 读写对账/staging 平移源/UI 层/字形）
