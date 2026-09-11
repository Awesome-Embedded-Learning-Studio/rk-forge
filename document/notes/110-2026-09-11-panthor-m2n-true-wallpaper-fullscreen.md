# Note 110 · panthor M2n：真壁纸全屏可复现——五连修，熊猫现形

日期：2026-09-11 · 战役七第二十九篇 · 上一节：note 109（屏幕垃圾根修）

## 0. 摘要

note 109 双修后屏上仍是 sb 马赛克级色块（253 色，认不出内容）。
本轮沿"细节损失链"五连修，最终 **99.99% 全屏、930 独立色、MCP
清晰辨认"白色熊猫+放射光效+平滑紫渐变、无伪影"**——用户记忆中的
壁纸动物（熊猫）完整上屏，跨 boot 可复现（922/930 色两次）。

## 1. 细节损失链（每环一修）

| 环节 | 损失 | 修 |
|---|---|---|
| ① VOP AFBC 判定门 | 首 sb 非 uniform（body 指针≠0）→ 整缓冲被当线性显示=AFBC 结构字节上屏（横线） | 扫首行前 4 头：全过"64 对齐且<64MB"才按 AFBC 解 |
| ② BG 注册 porder | bf=2 缓冲硬编码 porder=1=被当 U-tile 读（横线） | porder 按 bf：bf=2→2（线性） |
| ③ BG 择优 | 后完成的近全黑 full 挤掉好图（"full≠有内容"）；1 点探针太松 | 8 点命中数择优，后来者须更高 |
| ④ 细节源头 | 中间链全是马赛克/转写——真像素在 CPU 上载的 **staging**（线性大纹理）里 | 大 draw 源 plane=线性≥1024×768 且 8/8 命中 → 直接注册为 BG（绕过全部中间链） |
| ⑤ 读侧散射 | 线性读=PA+偏移跨断页读无关页（上半图下半黑）；stitch 页缓存跨 job 陈旧（8×8 偶发 FAIL） | tex_read_px 全 VA 逐页缝合（9 调用点参数化 sva/tiled）；job 提取入口重置缓存 |

## 2. 关键机制发现

- **staging 即真相**：壁纸链每级转写都损失细节，唯 CPU glTexImage2D
  的 staging 保有全分辨率真像素；识别特征=线性（ptype=1/order=2）
  ≥1024×768 大纹理
- **读侧也要缝合**：note 108 只修了写侧；线性 PA+偏移读大缓冲跨断页
  同样读错页（表现为内容前缀有效、断页后全零）
- **BGFULLRES 回归**：毒根修后 solid/realimg 带宽妥协可解除——
  3840×2160 全采样 358-1230ms（5s 超时内），为中间链保真
- **单槽 stitch 缓存是跨 job 状态**：新进程=新 VM/AS，陈旧翻译=M2e
  同族错页（受控 8×8 偶发 FAIL 的真身）

## 3. 验收

- 受控 9/9 PASS（2/8×3/32/64/128/256 全屏+子区域+偏移；8×8 三连=
  竞态根修验证）
- REALIMG+GDM+BGFULLRES：`staging-BG 3840x2160 stride=3c00` 注册 →
  屏 99.99%/930 色/0 黑行，两次 boot 复现
- MCP 读图：*"白色熊猫图案（圆形眼睛、三角形鼻子，面部特征清晰）+
  放射状光效+深紫渐变背景，颜色过渡平滑、无伪影"*
- 证据：sim/logs/m2n-true-wallpaper.ppm（git）+ Windows 桌面
  gpu-true-wallpaper.png

## 4. 现行达成形态

```
GPUDBG=1 FSQUAD=1 FSQUAD_REALIMG=1 FSQUAD_BGFULLRES=1 GDM=1 \
  setsid nohup python3 sim/resboot.py 7200 > sim/logs/resboot.out 2>&1 &
# ~5min 后 monitor screendump → 99.99% 真壁纸
```

诚实边界：壁纸=staging 直采近似（合成几何仍是 fallback 全屏 quad）；
屏上 UI 元素（greeter 面板/文字）与壁纸的层叠合成未实现——壁纸层
真、上层 UI 仍缺。

（战役七链：…M2n-visible✅→毒根修✅→屏幕垃圾根修✅→**真壁纸全屏✅**
→余=UI 层合成/字形位姿/vt1-nudge/LINEAR）
