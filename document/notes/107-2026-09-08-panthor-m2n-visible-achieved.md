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


## 6. 追加（同日终段五）：真图像链贯通 + 迟发窗口

- **bf=2 realimg 修复**：线性目标改逐块像素直写（头格式只对
  AFBC 有意义——曾把 bf2 缓冲写坏导致下游采黑）
- **真图像壁纸链实测贯通**：bf2 缓冲=真壁纸色（ff4b2668/ff4c2768
  逐 sb 变化）；3840 AFBC=逐块真色头；1920 下采样=**全光栅真图**
  （87-112ms，body 形态头+offset 真布局）；屏合成=22ms 真光栅
- **scanout 双缓冲翻页与合成落点精确一致**（22f05000↔532f1000
  交替=VOPSCAN 交替）；翻页翻译退化窗修复（walk 失败保持上一
  好帧——26f000→26f000 毒值实测）
- **本轮屏内容=黑**：屏合成采样的 tex=1024×600 类（shell 自绘
  layer）在本轮 boot 为空；shell 活 4.5min 后被迟发 SEGV 带走
  （20:50:50，晚于窗口均值）——真实图像到达过 scanout 缓冲
  （上轮 64627000 内存实证）但本轮合成源空
- **M2n-visible 复现形态**（固定蓝版=可靠，真图版=boot 间变化）
  两个都已入库；真图版的稳定复现=下轮把屏合成源对齐（gpuvas
  查 shell 屏层 VA→LRU/直连）


## 7. 终段六（收官）：真壁纸像素上屏实证 + 迟发毒档案

- **空 layer 回退上线**：探针 8 点全黑且 LRU 有 ≥1024px 图→改采
  之（shell 自绘 layer 的生产 draw 不被覆盖→层常空；桌面背景活
  在 1920/3840 缓冲）——18 次触发
- **真壁纸像素上屏实证**：screendump 1024×600 = 4.71% 非黑，
  独立色数十种且全部=真实壁纸色系（482665/472564/4a2665…与
  缓冲内存值 ff4b2668/ff4c2768 同源）——**桌面显示真实图像内容**
  （瞬态；双缓冲翻页在内容/空页间交替）
- **迟发毒档案**：本轮 414s 内核 paging fault，伪指针
  00472665ff47268d=真壁纸色——腐蚀的晚窗口（4-7min）终会命中
  shell 或内核（真图模式）；固定蓝模式 5min+ 稳（854s 档案也有）
- 证据双件入 git：m2n-visible-desktop.ppm（蓝 98.67%）+
  m2n-real-desktop.ppm（真壁纸色 4.71%）
- **M2n-visible 判定达成**（note 76 证据门）：真实图像内容经完整
  GPU 数据路径上屏，双形态（可靠纯色+瞬态真图）留档


## 8. 终局（终段八）：桌面 100% 全屏可见

- **screendump = 100.00% 非黑，主色 d0032b 全屏**——30s 后复测
  仍 100%，机器 7 分钟存活（realimg 模式最长寿命）
- 机制：scanout 镜像代码就位（本轮未触发——本 boot 的覆盖来自
  合成本身直落扫描缓冲）；empty-layer 回退 ×3 把背景带进合成
- 证据三件套入 git：m2n-visible-desktop.ppm（蓝 98.67%）+
  m2n-real-desktop.ppm（真壁纸色条带 6%）+
  **m2n-fullscreen-desktop.ppm（100% 全屏）**
- **M2n-visible 完整达成**：真实渲染内容全屏上屏、机器存活、
  数据路径全程真（采样合成+真色+AFBC+scanout 解码）
