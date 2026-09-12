# Note 96 · panthor M2k：AFBC 写路径 + VOP 解码——AFBC 基建全通

日期：2026-09-06 · 战役七第十五篇 · 上一节：note 95（M2j AFBC clear+读）

## 0. 摘要

M2j 的读侧补上写侧，桌面冲刺的 AFBC 基建闭环：

1. **AFBC dst write**（try_blit 的 bf=12 分支）：per-superblock 双形态——
   全同色 → solid header（真规范：payload 全 0 + 色@+8）；否则 body+
   header（**本模型布局**：header.offset=body 相对偏移、sizes 全 1
   （真规范"未压缩子块"编码）、body=16×16 线性 RGBA 在 header 区后
   64B 对齐按 sb 序排布）。边缘半 sb 跳过（诚实边界）。
2. **blit dst 登记为 last_img**——readback 必须读 blit 结果而非 src
   （A→B 后读 B：之前会错读 A）。
3. **VOP scanout AFBC 解码**：fb 首 16B 为 solid/header 形态时按 sb
   解码（solid→填色 / body→线性读，与 GPU 写路径对称）；RGBA→pixman
   x8r8g8b8 摆位。全黑线性帧误判=全黑 solid 等价，无害。

**验收**：64×64 A(clear)→B(blit AFBC 写)→readback B——**坏点 0 PASS**
（AFBC 读写回环）；gbf(16 tiled) PASS、gc PASS、零损坏。mutter 侧
（GDM 机）：mutter 合成 dst=1024×600 bf=12 实锤（scanout FBO 也是
AFBC，VOP2 硬解），桌面仍黑——**合成是 shader 采样，我们的引擎正确
弃权**（整图 1:1 语义不适用于多窗口合成）。

## 1. mutter 合成 dst 形态（GPUDBG 放开 blit dst 打印后首次可见）

```
1024x600 rt1 bf=12 base=7ffff5800000 stride=400 clr=0   ← scanout FBO
 512x512 rt1 bf=13 ... stride=1000                      ← 窗口纹理（AFBC Tiled!）
 1027x35 rt1 bf=12 ... stride=410                       ← damage 条带
```

## 2. M2l 路线判据（桌面可见的最后判定）

- mutter 每帧：条带渲染（shader）→ 合成到 scanout（shader 采样窗口
  纹理）。两个环节都是真 shader 执行——**note 76 的 9-24 人月判据
  对"桌面可见"仍然成立**，AFBC 基建只完成了显示侧。
- 可选捷径（未验证）：若 mutter 存在 direct scanout/flip 路径（全屏
  客户端 buffer 直接上屏），整图语义可能适用——留待观察。
- 常量色 FS（glestriangle 的 RUN_IDVS 已贯通）依旧是下一个真里程碑：
  需要解析 FAU 常量或最小 Valhall 解释器。

## 3. 边界

- AFBC body 布局是 sim 约定（真规范 body 是压缩流）——读写两侧都是
  本模型，自洽；真机/真 GPU 不通用（诚实边界，note 76 纪律）。
- find_src_plane 的 heur/parsed 与 AFBC plane 的 parsed 识别仍未对上
  （本轮回环走 heur）——不阻碍能力。
- VOP 解码的 solid 误判仅"黑帧等价"，无错误内容风险。
