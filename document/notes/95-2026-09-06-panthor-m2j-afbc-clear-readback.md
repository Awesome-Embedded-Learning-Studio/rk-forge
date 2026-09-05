# Note 95 · panthor M2j：AFBC clear + readback 全链通

日期：2026-09-06 · 战役七第十四篇 · 上一节：note 94（M2i 结构匹配 src）

## 0. 摘要

桌面可见的第一道墙实测是 **AFBC（bf=12）**：GDM 机上 mutter 的全部 RT
都是 bf=12（1027×35 条带、header 行距 0x410=65 superblock×16B 自洽），
clear/blit 双双跳过。本篇落地：

1. **AFBC clear（硬件语义）**：superblock header 16B union（pan_afbc.h）
   的 **solid color 编码**——payload 字段全 0 + `rgba8888@+8..11`，
   pan_afbc.c 判据 `sizes[0]&0x3f==0`。只写 header 不写 body，每 sb
   三次 store。
2. **AFBC 读路径**：blit 的 src 像素读双形态——sb 头 16B payload 全零
   → solid（色在 +8）；否则按 U-tiled 读。16×16 红 tile 的头 16B 是
   非零像素数据，天然分流。
3. **子区域 readback**：readback 的 staging dst（64×4）比 src plane
   （64×64）矮——尺寸门从"相等"放宽为 **plane ≥ dst**（find_src_plane
   与 last_img 回退同步）。

**验收**：64×64 AFBC FBO clear 红 → glReadPixels 64×4 → 采样坏点 0
**PASS**；gc 回归 PASS；零 Bad page/WARN。

## 1. mutter 实测情报（GDM 机）

```
GPUFBG ... w=1027x35 rt1 bf=12 base=... stride=410 clr=0
```
- mutter 的渲染是 **damage 条带**（1027=1024+3 对齐进 65 sb），不是
  整帧 FBO；
- **clr=0**——mutter 用黑色 clear 再靠合成上色。桌面点亮还需要
  **AFBC dst write**（合成 job 的 RT 也是 bf=12，try_blit 目前 dst
  只认 bf=1/2）+ 真实窗口纹理做 src。

## 2. 过程坑

- **十六进制位数连环坑 ×2**：锚点扫描窗口的基数（0x7fffff00000 少一位
  =窗口低 16 倍全落空）与预对齐（`&~0xfffff` 把中心砍错）——大数
  窗口算术必须机器算，不能心算。
- GPUANCH 探针法（enter/complete 计数）定位"扫描在跑但零命中"→
  实际根因是尺寸门，与仪器无关。
- find_src_plane 放宽后歧义风险由"唯一命中"门兜底（多义→弃权→
  last_img 回退——gb64 走的就是 heur 路）。

## 3. 边界与下一刀（M2k：桌面冲刺）

1. **AFBC dst write**：合成 job 的 bf=12 dst——写 body+header（sim
   自洽布局：uncompressed payload 或按 sb solid 拆分）+ VOP scanout
   的 AFBC 解码（solid→色/raw→body）。
2. **合成 job 的 src=窗口纹理**（AFBC plane 的 parsed 识别——本轮
   heur 路已够单 FBO 场景）。
3. mutter clr=0 意味着纯 clear 路线桌面永远黑——可见性的唯一路径
   就是 ①+②（合成 blit 落地）。

## 4. 资产

- `afbc_clear_sb` 计数（qom 待导出）、AFBC clear/读进补丁
- gb64 场景（64×64 AFBC）随 sim/glesblit.py 参数化（W=H 可调）
