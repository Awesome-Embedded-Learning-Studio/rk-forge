# Note 113 · panthor M2n：校验武器化——verify_screen.py 取代 MCP 读图

日期：2026-09-12 · 战役七第三十二篇 · 上一节：note 112（脸区悬案）

## 0. 摘要

用户定调："MCP 的方式太粗糙，有没有更好的办法"→ 把本会话散装了 6 遍
的取证内联脚本固化成 `sim/verify_screen.py`（纯标准库），**内容验收
从 AI 自由心证改为确定性数值判决**。工具首跑即翻案两件：①til2
（tiled 快照）全背景 p90=92，比线性时代（22.4）更糟=用户"看起来
更糟糕了"数值实锤；②此前"背景像素级吻合 5-9"是角落采样的幸存者
偏差。

## 1. 三模式

| 模式 | 命令 | 判据 |
|---|---|---|
| 全屏对照 | `verify_screen.py 屏.ppm --ref 参照.png [--out-dir D]` | 鲁棒中位色偏→64×36 块差→背景域 p90≤20 且结构域 p50≤40=PASS；结构块=参照边缘密度>6 分域；位移场=结构块限界搜索最优偏移（移位/错乱定量）；产出 diff-heat.ppm 供人眼复核（不作判据） |
| 1:1 条带 | `--strips --strip-rows 100,500,990,1500,2000` | 每行原位差+限界位移搜索最优差→`aligned` 逐行定谳（自造 16px 位移注入验证：精确检出） |
| 原始页分类 | `--classify`（输入=二进制 dump） | 每 4KB 页：字节熵/零占比/排版字符（空格>8%+换行）/LPAE 指针特征（词低 2 位=11 >30%）→ zero/sparse/pagetable/text/image/mixed 直方图 |

## 2. 标定坑（已修）

- 紫色图像字节恰落 ASCII 可打印区（0x25-0x6f）→ 裸 ascii 占比把
  图像误判 text；修=text 需排版字符作证（空格+换行/Tab），且
  pagetable 判序提前
- 结构/背景分域用**参照**边缘密度（不是屏的）——屏已碎时用屏自身
  会把碎片当结构

## 3. 判决迁移

- 旧：MCP 读图→"看见浣熊"（两次把差 94 的图读成完美浣熊，note 112）
- 新：verify_screen.py 数值判决；MCP 降级为 diff 热图的可选旁白，
  **永不作判据**
- 受控 glestexture.py 的 PASS/FAIL（guest 内数值判决）不受影响，
  继续作为受控面守门员

## 4. 下轮使用姿势（配合脸区悬案）

```
# 1) 屏对照（每 boot 必跑，替代一切"看起来"）
python3 sim/verify_screen.py sim/logs/X.ppm --ref out/.../cnusr25-Simple_Raccoon_Dark.png
# 2) staging 1:1 条带（STGSTRIPS dump 后）
python3 sim/verify_screen.py sim/logs/strips.ppm --ref 同上 --strips
# 3) 脸区 6MB 原始 dump（待加 STGDUMPFACE）离线分类
python3 sim/verify_screen.py sim/logs/face.bin --classify
```

背景偏移 [-11,-9,-10] 为 greeter 调光恒偏，工具自动估计。

（战役七链：…staging 读路径实验→**校验武器化✓**→余=脸区悬案
（换武器：dump 原始字节+本工具分类）/UI 层/字形）
