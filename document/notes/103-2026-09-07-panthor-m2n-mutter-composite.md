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

## 2. kernel panic 根因（已锁定，修复=下轮工程）

**真凶 = 长 BQL 持有触发的宿主 NMI 硬锁死**：第三次复现现场拿到
决定性证据——`Watchdog detected hard LOCKUP on cpu 4`。机制：3840×2160
等大 draw 的光栅化 = 数千万次 address_space 访问在 **BQL 下单线程**
跑数秒，TCG vCPU 线程全程不让出 → host PMU watchdog NMI 判死 →
内核 panic（此前 DABT/NULL 各种形态都是它的下游）。证据链：

- FSQUAD off 稳定 / 像素上限(≤1920×1080)在位稳定（2M px ≈ 1-2s
  勉强不触发）/ 撤上限即崩（8.3M px ≈ 数秒必触发）
- 崩溃 boot 的日志尾巴无异常写入（最后 raster=48×48 图标，bp 全部
  合法）——不是内存腐蚀，推翻初版的 misparse 假设
- **壁纸链完整因果**：1920×1080 下采样 draw 采样的纹理=3840×2160
  AFBC（非 staging）→ 上载被上限拦 → 3840 纹理空 → 1920 写零 →
  合成 blit 搬黑 → 屏黑。链路要通就必须跑 8.3M px 上载
- **修复方向**：raster 分片异步化——RUN_FRAGMENT 只入队
  {stage,参数}，qemu_bh 每次处理 N 行（BQL 片间让出），完成后提交。
  fence 时序（fake-completion 先行）记录为 sim 已知偏差

## 3. 前轮遗留的修正

- 上轮"701px 文字行"：GDM 640×480 模式下的产物；本轮 1024×600
  模式未再现——来源仍开放（note 102 已 soften，维持）

## 4. 资产

- `va_pa_bound()` 写路径严格翻译；raster_imgs LRU；VOPSCAN 打点
  （scanout 源变化去重）；GPUQUAD spanfail/toobig/consume-PA 取证
- 稳定工作形态：`GPUDBG=1 FSQUAD=1 GDM=1`（上限在位）
