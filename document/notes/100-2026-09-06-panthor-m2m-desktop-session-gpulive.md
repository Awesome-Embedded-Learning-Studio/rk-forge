# Note 100 · panthor M2m：桌面会话全负载活——采样合成的边界定界

日期：2026-09-06 · 战役七第十九篇 · 上一节：note 99（M2l 常量色 FS）

## 0. 摘要

M2l 引擎上 GDM 机检验：**完整 GNOME 桌面会话（nautilus/gjs）在 GPU
仿真上全负载运行**，GPUBLIT 在 mutter 真实负载下持续工作（60×60/
48×48 AFBC 图标/光标搬运）。桌面仍黑——GPLANES 普查给出决定性否定
情报：**主合成时刻批池无全屏背景 plane**（GNOME 壁纸非 1:1 纹理
actor；全是小 actor + 噪声匹配）。⇒ 桌面可见的剩余路径 = **完整
纹理采样合成**（TEX_SINGLE(0x128) + varying 插值 + blend）——note 76
深水区本体，无捷径可走。

## 1. GDM 机实测（M2l 引擎上）

| 项 | 结果 |
|---|---|
| 会话 | gdm active，nautilus/gjs 活（完整桌面非 greeter） |
| 消费 | 4316+ job 持续（稳） |
| GPUBLIT | mutter 下活跃：60×60/48×48 bf=12 AFBC 搬运（heur 路径） |
| GPUFS | 0——mutter 无常量色 FS job（背景不走 M2l 路径） |
| RUN_IDVS | 0——mutter 合成全走 RUN_FRAGMENT（提取器挂 IDVS 无机会；无碍） |
| screendump | 全黑（scanout 被 clr=0 clear 后无内容写入） |

## 2. GPLANES 普查（主合成 dst=1024×600 时刻）

批池"plane 候选"全为 8×11/1×11/20×20/10×10 级小匹配（多为噪声：
非 plane 数据恰好满足 base∈堆+stride 幂次+dims 编码判据）——
**无 ≥1024×600 的纹理 plane**。GNOME 桌面的可见内容 = 多个小 actor
（窗口条带/图标）逐像素采样合成，不存在"一张全屏背景纹理可拷"。

## 3. M2n（采样合成）的真实规模

需要：
1. **TEX_SINGLE（op=0x128）语义**：坐标→texel 读取（含 wrap/filter）
   ——纹理数据路径已有（M2i plane+M2j 读三形态），缺坐标插值
2. **varying 插值**（VAR_TEX/LD_VAR 族）：顶点属性→每像素坐标
3. **blend**：BLEND 描述符的混合方程
4. 多 actor 的 draw 分发（每 actor 一个 quad + 变换）

这就是 note 76 原判 9-24 人月的"per-pixel shader"本体。已达成的
常量色类（M2l）是其最简退化情形——解码/执行框架（ATEST 锚+装载
解码+r0/r1 约定+BLEND 输出）可直接复用。

## 4. 资产

- `GPLANES`（GPUDBG 门控）：try_blit 时的 plane 候选普查
- `GPUFSX`（GPUDBG 门控）：非匹配 FS 的指令形态 dump（本轮因
  mutter 无 RUN_IDVS 未触发——挂 RUN_FRAGMENT 是下轮修正）
- GDM 会话验收形态：`ps` 查 nautilus/gjs + screendump 主色统计

## 5. 战役七收官状态

真像素线全链 ✅（M2c→M2l）。桌面会话全负载活 ✅（本篇）。桌面
**可见** = M2n 采样合成（深水区，弹药：ISA.xml 指令表、M2i/j 的
纹理读、M2l 的解码框架）。
