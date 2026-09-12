# Note 108 · panthor M2n：迟发毒根因定谳并根修——VA 映射散射，线性写即毒

日期：2026-09-10 · 战役七第二十七篇 · 上一节：note 107（桌面可见）

## 0. 摘要

**迟发毒（notes 104-105 全程悬案）根因定谳：GPU BO 的 VA 映射物理
散射，光栅化按 bp+线性偏移写=跨断裂页后落到无关内存。** 战役五的
VOP 早就写着"bo 的 iova 映射不保证物理连续"（所以 scanout 逐页
缝合）——raster 路径从未应用同一条。本轮补齐全部写路径的逐页
缝合，**REALIMG+GDM 机 340s+ 稳定**（scatter 探测器抓到 **485,677
个线性假设错页**≈1.9GB 错向写），受控回归 7/7 绿，真图屏 553 色
（历史最高）。

## 1. 证据链

- `rk3588_lite_gpu_rjob_pa()`（压缩期会话已埋）逐页翻译+GPUW
  scatter 探测（pa != linear 页打点）——本轮 GPUWRITELOG=1 首开：
  **scatter=485,677**（457 job），同机 REALIMG 全写零 panic
- 概率性/壁纸最毒/界内审计全过/SOLIDBLUE 较稳——全部由"分配
  拓扑决定断裂点在 span 内的位置"一次解释
- 早前"页表页中毒"直觉对：错向写恰常落在 GPU 页表页（大量
  PTE 页在堆中）→ 后续翻译再错 → 级联

## 2. 根修（全部写路径逐页缝合）

| 路径 | 修法 |
|---|---|
| rjob 主光栅化 | `rjob_pa()`（已有，压缩期埋） |
| try_blit dst（solid/body 头+线性+tiled） | **本轮**：`rk3588_gstl/gstq`（base VA+偏移） |
| run_fragment clear（bf=2 铺+bf=12/13 头） | **本轮**：同上 |
| fullres 镜像 | 已有（`vop_stl` IOVA 逐页） |
| 旧助手重写 | stitch_pa+gstl/gstq（页缓存 `stitch_vpg/ppg/ok`） |

## 3. 验收

- 受控 7/7 PASS（2..256 全屏+子区域+常色；首轮 FAIL 是老 GDM 机
  占端口、测试跑在 mutter 干扰下的假阴性——查 qemu 进程 env 定谳）
- REALIMG+GDM+GPUWRITELOG：340s+ 零 panic（scatter 48.5 万）
- 真图屏 **553 独立色/47%**（m2n-stitched-realimage.ppm 入 git）
- GDM 重启后显示未回（会话态方差独立问题，与毒无关——机器活）

## 4. 战役七最终账

```
M-pre0→M0→M1→M2a..M2l（shader 语义）→M2m（会话负载）→
M2n：侦察→受控 11/11→异步化→双病分流→界内全证→壁纸门→
显示点亮→内容工程→100% 全屏→**毒根修+缝合写**✅
```
迟发毒曾是三层残局之首——现在归零。余：显示接管确定性（GDM 重启
后偶不回）、字形位姿（FAU RAM 模型）、错源链防伪（文件缓存页当
纹理——缝合修后错向写已灭，但读错源仍可能）。
