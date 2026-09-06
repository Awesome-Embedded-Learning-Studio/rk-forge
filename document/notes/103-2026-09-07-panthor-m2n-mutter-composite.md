# Note 103 · panthor M2n-mutter：合成链打通与 kernel panic 边界

日期：2026-09-07 · 战役七第二十二篇 · 上一节：note 102（采样矩阵+bf=13 翻案）

## 0. 摘要

mutter 合成链最后一环**结构上打通**：合成 blit（1024×600 bf=12）经
raster-LRU 回退真正执行（19 次/boot）；壁纸链全程测绘（3840×2160
上载→1920×1080 下采样→1024×600 合成→VOP scanout 源=主 FBO 实证）。
但 **FSQUAD 全开时 kernel 在 ~130s DABT panic**（字形阶段即复现，
与大图写入的因果已证伪——像素上限拦截大写后仍在 62 raster 处崩）。
当前落点=**像素上限（>1920×1080 弃权）稳定配置**，panic 根因开放。

## 1. 合成链全图（本轮实测拼接）

```
CPU 壁纸像素 → staging（线性）
  → GPU blit 上载 → 3840×2160 bf13 纹理（我的 raster 写，8.3M px）
  → mutter 下采样 draw → 1920×1080 bf13（我的 raster 写）
  → 主合成 blit（RUN_FRAGMENT only）→ 1024×600 bf12（try_blit 写）
  → VOP scanout：VOPSCAN mst→PA 与 GPUFBG 主 FBO base→PA 精确一致 ✓
```

关键修：
- **raster-LRU**（8 槽设备态）：合成 blit 的 src（长命 plane 描述符）
  不在批池 ±0x8000 窗——改由写方登记、blit 回退查（GPUBLIT heur ×19）
- **严格写翻译** `va_pa_bound()`（只走绑定 AS）：lenient 版跨 VM 别名
  会给错页（M2e 同族教训，写路径禁用回退扫描）
- consume 打印扩展 rt 的 PA/stride（取证壁纸 job：PA=0x2fe00000 st=0x7800）

## 2. kernel panic 边界（开放问题）

- FSQUAD on + 无像素上限 → ~130s DABT panic（两次复现，VA=内核
  vmalloc+像素值被当指针=结构腐蚀）
- FSQUAD on + >1920×1080 弃权 → **稳定**（330s+ uptime 往返）
- 撤上限（严格翻译在位）→ 仍在 **62 raster（字形阶段）** 崩——
  大图写入非唯一根因；字形写（512² 图集，span ~1.2MB 自洽）如何
  腐蚀内核未解。候选：①图集 bp 误译（cur_as 陈旧？）②字形 draw
  的某个偶发 misparse 目标 ③与字形无关的并发时序（FSQUAD off 稳定
  只证明与 raster 路径相关）
- 下轮刀口：崩前最后 N 个 raster 的 bp/sp dump 比对 plane 声明；
  或上限逐步放宽做二分（1920→2048→…→3840）

## 3. 前轮遗留的修正

- 上轮"701px 文字行"：GDM 640×480 模式下的产物；本轮 1024×600
  模式未再现——来源仍开放（note 102 已 soften，维持）

## 4. 资产

- `va_pa_bound()` 写路径严格翻译；raster_imgs LRU；VOPSCAN 打点
  （scanout 源变化去重）；GPUQUAD spanfail/toobig/consume-PA 取证
- 稳定工作形态：`GPUDBG=1 FSQUAD=1 GDM=1`（上限在位）
