# Note 99 · panthor M2l 达成：常量色 FS 执行——shader 语义的像素

日期：2026-09-06 · 战役七第十八篇 · 上一节：note 98（八变体 diff）

## 0. 摘要

**常量色 fragment shader 的像素出来了，色值来自 guest 内存的 Valhall
指令流**。全屏三角形 draw（RUN_IDVS）→ 执行器扫批池定位 FS 代码 →
解码常量装载指令 → r0/r1 打包 fp16 → RGBA8 → 铺满 FBO → readback
验证。**11 色变体 + 2 回归 = 13/13 PASS**（含 0.5/0.25 非平凡值）。
note 76 证据门认可的"真 shader 语义"首次达成。

## 1. 完整解码链（十变体明文 + ISA.xml 双向验证）

```
FS 代码（批池 SPD_2±0x8000 窗，8B 指令）
  ├─ 锚：ATEST（op=0x7d, dest=r60——十变体恒定）
  ├─ 装载 1：IADD_IMM.i32（op=0x110）imm32=(q>>8)&0xffffffff → dest
  ├─ 装载 2：MOV.i32（op=0x091）src0 高 2 位=11 → LUT[src0&0x3f]
  │           src0 高 2 位=00 → 寄存器 copy（white 的 r1←r0）
  └─ 输出：BLEND（op=0x7f）读 r0/r1
约定：r0=(lo16=R, hi16=G)、r1=(lo16=B, hi16=A)，fp16
opcode=bits[56:48]、dest reg=bits[45:40]、dest mode=bits[47:46]（valhall.py 权威）
LUT=ISA.xml 32 条表（idx27=0x3C000000=half(1.0,0.0)、idx0=0.0…）
```

十变体校准（note 98 §5）：imm 低半=R 高半=G 双交换实证；blue 的
装载目标换 r0/r1（编译器换分配）由 dest 位段天然消歧——**不用序列
假设，读 dest 就知道装的是哪对通道**。

## 2. 实现（hw/arm/rk3588-lite.c）

- `rk3588_lite_gpu_extract_fs_color(spd2)`：扫 SPD_2±0x8000，ATEST 锚
  +3 条内解码 r0/r1（IADD_IMM imm / MOV LUT / MOV reg-copy），整数
  fp16→u8（舍入：0.5→128，右移逐位 +1）。
- RUN_IDVS 无条件提取 → `fs_color_pending`；RUN_FRAGMENT **优先于
  blit/clear** 铺色（find_src_plane 会拿 draw FBO 自身 plane 误搬运——
  净机二轮实锤的坑）。
- f16→u8 两个实现坑：double-divide 1024（全黑）；截断 vs 舍入
  （0.5→127≠128）。**数值转换必须带非平凡值验收**（halfred/quarter
  就是为此在矩阵里）。

## 3. 验收（13/13 PASS，净机连续跑）

```
red/blue/green/white/black/halfred/cyan/magenta/cal1/cal2/quarter PASS
gc-clear PASS   gc-blit PASS（回读路径无回归）
GPUFS color=ffff0000 (r0=0 r1=3c003c00)   ← blue 提取示例
```

## 4. 诚实边界（note 76 纪律）

- 覆盖**常量色 FS 类**（mov/immediate 装载 + BLEND 输出）：纯色填充、
 纯色几何。纹理采样/插值/混合/discard 不在列（采样 FS 无常量装载
  模式 → 提取器自动弃权 → 回落 blit/clear 路径，无害）。
- mutter 合成（多纹理采样）仍超出——但**桌面背景/纯色窗口/锁定屏**
  类内容从此路径可达。VOP AFBC 解码（M2k）已备——纯色窗口上屏只差
  mutter 真发这类 job。
- FSCOLOR 环境参数化进 sim/glestriangle.py（期望色自动跟随，变体
  期望硬编码的乌龙不再来）。

## 5. 战役七真像素线全链（收笔）

```
M2c clear word → M2g U-tiled → M2h 真 blit → M2i 结构匹配 src
→ M2j/M2k AFBC 读写+VOP → M2l 常量色 FS ✅
```
从"executor No-Go"（note 76 原判）到 shader 语义像素，全程 dump
实测驱动、零硬编码色值。
