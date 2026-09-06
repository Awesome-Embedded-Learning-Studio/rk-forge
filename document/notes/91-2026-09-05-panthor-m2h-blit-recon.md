# Note 91 · panthor M2h 侦察：readback blit 的指令形态与寄存器地图

日期：2026-09-05 深夜 · 战役七第十篇 · 上一节：note 90（M2g draw 流贯通）

## 0. 摘要

为"第二个真像素"（真数据搬运，非 clear word 铺设）选切面：glReadPixels 对
64×64 U-tiled FBO 的 readback 必须走 GPU blitter。实测其指令形态是
**RUN_IDVS(6)+RUN_FRAGMENT(7)+FINISH 双件套**（不是预想的 RUN_FULLSCREEN(8)
——后者 v10 上 mesa 只在 blitter 的特定路径用，`cs_run_fragment` 有
fullscreen 模拟回退）。落成侦察装备：`GPURUN=1` 在 RUN_IDVS/FULLSCREEN
时 dump SR 寄存器面（regs 40-43/56 + DCD 寄存器）。关键地图：**r40 =
FBD 指针**（RUN_FRAGMENT 的 FBD=regs[40] 实证同源，cs_builder.h 的
`CS_RUN_FULLSCREEN_SR_MASK = regs 40-43+56` 权威印证）——blit job 的
r40=0x7fffffeb6380 即 readback 的线性 staging FBO 的 FBD。

## 1. blit job 实测形态（sim/glesblit.py：64×64 clear 红 + readback）

三 job：init → clear（RUN_FRAGMENT 单发，clear-only 执行器可铺）→
**readback blit**（RUN_IDVS 6:1 + RUN_FRAGMENT 7:1 + FINISH_TILING 9:1 +
FINISH_FRAGMENT 11:1 + LOAD_MULTIPLE×2 + BRANCH）。readback 读的是从未
被填充的 staging 线性缓冲 → FAIL（预期边界）。

RUN_IDVS 指令原文：`op=6 flags=0004000c`，字段（v10.xml）：Flags
Override@0、SRT/SPD/TSD/FAU select@40-47（各 1-2 位）、Draw ID@40-47。
**描述符不经指令载荷**——经寄存器文件的 SRT select 间接引用。

## 2. 寄存器地图（M2h 的施工基准）

| 寄存器 | 含义 | 来源 |
|---|---|---|
| regs[40] (0x28) | FBD 指针（FRAGMENT/IDVS/blit 通吃） | M2c 实证 + SR_MASK |
| regs[40-43] | FBD/tiler 块（LOAD_MULTIPLE base=40 mask=3 装载） | note 87 + SR_MASK=range(40,4) |
| regs[56] | v10 追加 SR（v11+ 用） | cs_builder.h |
| RUN_FULLSCREEN 的 DCD | **指令字段[47:40] 是寄存器号**，其值=DCD 指针 | v10.xml CS RUN_FULLSCREEN |

## 3. 下一刀的入口（M2h 主战役）

实现 readback blit = "整图拷贝"（src tiled FBO → dst linear staging）：

1. **SRC 定位**：blit 的 fragment shader 采样源纹理，纹理描述符在 SRT
   （shader resource table）链上。路径：RUN_IDVS 的 Fragment SRT select
   → SRT 基址寄存器（哪个？待从 cs_builder 的 cs_set_state/SRT 布局读）
   → 纹理描述符（v10.xml "Texture"）→ image plane base+布局。
2. **拷贝语义**：同格式整图，bf=1→bf=2 需 **U-interleave detile swizzle**
   （mesa pan_texture.c 的 16×16 u_interleave 位重排，~20 行可移植）。
3. **验收**：glesblit.py 的 4×4 采样块全红 = 第一个真 blit 像素。

替代捷径（如果 SRT 链太深）：DCD 里的 attribute 表（blit 的顶点属性带
src 坐标）或 RUN_FULLSCREEN 路径（pan_csf.c:1926，DCD 直挂寄存器，链短
一截）。

## 4. 资产

- `sim/glesblit.py`（64×64 tiled FBO + clear + 全宽 readback 采样验证）
- `GPURUN=1` 取证开关（RUN_IDVS/FULLSCREEN 的寄存器面 + DCD 64B hex）
- note 90 的 GPUHIST/GPUSEG/GPUFBG 三开关沿用
