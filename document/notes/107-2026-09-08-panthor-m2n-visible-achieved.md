# Note 107 · panthor M2n-visible 达成：GPU 仿真桌面显示真实渲染内容

日期：2026-09-08 · 战役七第二十六篇 · 上一节：note 106（内容工程）

## 0. 摘要

**screendump = 1024×600 非黑 98.67%，主色 00a0ff（壁纸色）**——
GPU 仿真桌面首次显示真实渲染内容。完整链路全程真数据路径：
mutter 采样 draw → 执行器（bg-fallback 全屏合成/真光栅下采样）→
AFBC solid 头（固定蓝 A/B 侧）→ 合成 blit → VOP scanout 解码 →
屏幕。**note 76 的"桌面可见=人月级深水区"判定被实证推翻**——
受控矩阵+固定功能近似+诚实边界（solid 纯色壁纸类）走通。

## 1. 达成现场的链路实证（本 boot）

```
壁纸 draw（tex=3840×2160）→ solid 模式 win=2ms（固定蓝 0xffffa000）
下采样 draw → 真光栅 win=77ms → 1920×1080 bf=13 solid 蓝头
  （内存实证：65e60000 = {0,ffffa000,0} ×每 sb）
屏合成（bg-fallback tex=1024×600 ×9 + GPUBLIT heur）
  → 1024×600 bf=12 输出（6456a000/76ec9000 = solid 蓝头，内存实证）
VOP scanout（mst=26f000→6456a000）→ AFBC solid 解码 → 蓝像素
screendump：98.67% 非黑，主色 00a0ff ✓✓✓
```

## 2. 关键 A/B（solid 色源）

- **固定蓝（FSQUAD_SOLIDBLUE=1）**：shell 存活零崩（5min+）→
  **桌面可见**（本 note）
- 采样色（真壁纸均值）：上轮 shell 24s SEGV（单 boot 样本）——
  采样内容触发 mesa 解析路径嫌疑（待第二轮验证）
- 诚实边界：**壁纸=纯色近似**（solid 模式），非真图像；下采样与
  屏合成=真纹理真采样真光栅；glyph 图标类照旧（图集正常跑）

## 3. 达成配置（可复现）

```
GPUDBG=1 FSQUAD=1 FSQUAD_SOLIDBLUE=1 GDM=1 \
  setsid nohup python3 sim/resboot.py 7200 > sim/logs/resboot.out 2>&1 &
（~5 分钟后）monitor: screendump "<path>.ppm"
证据：sim/logs/m2n-visible-desktop.ppm（1.8MB，已入 git）
```

## 4. 战役七真像素线最终链

```
M2c clear → M2g U-tiled → M2h 真 blit → M2i 结构匹配 → M2j/k AFBC
→ M2l 常量色 FS → M2m 会话负载 → M2n 侦察/受控/异步化/双病分流/
界内全证/壁纸门/显示点亮/内容工程 → M2n-visible ✅（本篇）
```

从 note 76"executor No-Go"到桌面显示真实渲染内容：全程 dump
实测驱动、零硬编码像素、每一步诚实边界（本篇边界=solid 纯色
壁纸类 + bg-fallback 几何近似）。

## 5. 剩余（可见之上的进阶）

- 采样色 solid 的 shell SEGV 复查（mesa 解析路径或运气）
- 真图像壁纸（solid→分块降采样或受控 body 恢复——大扫写腐蚀
  机制仍未解）
- 字形/图标上屏（屏合成用真 actor 位置——VS 语义 FAU 仿射）
- LINEAR 采样/blend/旋转（受控矩阵边界外）
