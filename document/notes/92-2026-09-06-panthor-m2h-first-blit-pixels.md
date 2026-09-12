# Note 92 · panthor M2h：第一个真 blit 像素——数据搬运落地

日期：2026-09-06 · 战役七第十一篇 · 上一节：note 91（M2h 侦察）

## 0. 摘要

**glBlitFramebuffer 的 GPU blit 在模型里真实执行了**：FBO A（U-tiled，
clear 铺红）→ RUN_IDVS blit job → 执行器按 **u-interleave 位重排**（pan_
tiling.c 权威移植）逐像素 detile 读 A / retile 写 B → CPU 回读 B 的
256 像素全红，**VERDICT: PASS ×3 连跑**。这是 clear word 铺设之外的第一种
真数据搬运——GPU 模型的读写序与 mesa 的软 detile **双向吻合**。

## 1. 实现三件套（hw/arm/rk3588-lite.c）

1. **u-interleave 寻址**：`bit_dup[y&15] ^ space4[x&15]` = tile 内像素序；
   tile 首址 = base + (y>>4)·stride + (x>>4)·1024（bpp=4）。
2. **try_blit**（RUN_FRAGMENT 前置）：src=设备状态里"最近一次 clear 铺过的
   图"（last_img_va/w/h/stride/bf，进 vmstate），dst=本 FBD 的 RGBA8 RT
   （bf=1 tiled 或 bf=2 线性），同尺寸 1:1 逐像素拷贝；命中则 clear 路径
   让位。
3. **Clean Tile Write Enable（RT w1 bit31）分家**：clear job 置位、blit
   dst 不置（pan_fb.c `clean_tile_write_enable`）——clear 路径只认真
   clear，try_blit 见到置位即拒。这是"陈旧 last_img 误吞第二个进程的
   clear"（净机实锤：连跑第二轮 gc/gbf 全 FAIL）的根修，也顺带修掉了
   M2c 以来 clear 路径误铺 blit dst 的老毛病。

## 2. 验收（净机，panthor 在）

| 项 | 结果 |
|---|---|
| gbf.py（glBlitFramebuffer A→B + 全 256 像素回读） | **PASS ×3 连跑** |
| gc.py（clear+readback 回归） | PASS ×2 |
| GPUBLIT 触发 | 3 次（每次 blit 一发） |
| Bad page / panthor WARN | 0 |
| 落点链 | `GPUBLIT 16x16 bf=1 src=14996000 dst=14968000 stride=400` |

## 3. 过程坑（按发现序）

1. **64×64 FBO 是 AFBC（bf=12）**：mesa 对 ≥ 某尺寸的 FBO 选 AFBC 压缩
   ——clear/blit 都只能跳过。16×16 才是 bf=1。AFBC 是后续大关。
2. **gb.py 段错误乌龙**：readback 缓冲区只给了 W×4 字节（应 W×4×4），
   mesa 写爆 python 堆 → 分配器随机崩。教训：**堆损坏形态的崩溃先查自己
   测试脚本的缓冲区大小**（gdb 栈全在 python 帧 = 写爆发生在别处）。
3. **stdout 缓冲吞现场**：segfault 丢缓冲输出，崩点定位要用
   PYTHONUNBUFFERED=1。
4. **16×16 readback 走 CPU detile**（无 GPU job）——逼 GPU blit 必须用
   显式 glBlitFramebuffer（GLES3 context：EGL attrib 0x3098,3）。
5. **陈旧 last_img**：跨进程 VA 复用 + 尺寸相同 → 误判。Clean Tile 位
   分家后连跑稳定。

## 4. 诚实边界

- **blit src 是启发式**（"最近 clear 的图"）：单客户端单 FBO 场景精确；
  多 FBO 交错/多进程下可能搬错源。正道 = SRT 链解析纹理描述符
  （note 91 §3，SRT_2=regs[4] 的表项格式已 dump 在案）。
- 同尺寸门限（w/h/bf 必须相等）+ 只搬第一个命中 RT。
- draw job 的 RUN_FRAGMENT（clean_tile=0）也会被 try_blit 命中——
  把陈旧图搬进 draw target。draw 本来就无输出，影响=多了一层假象；
  M2i 的 SRT 解析会一并收掉。
- AFBC（bf=12/13）完全跳过。

## 5. 下一刀（M2i 候选）

1. **SRT 链解析**（把 blit src 从启发式换成真纹理描述符：SRT_2 表项
   {tagged_ptr,size} → 纹理描述符 → image plane base+布局）——同时解锁
   draw 场景的采样源。
2. RUN_IDVS 的 DCD/顶点解析（r57/r58=DCD0/1，dump 已有）。
3. AFBC clear（64×64 FBO 的前置关卡）。
4. 常量色 FS（桌面可见的最后一程，note 76 判据）。
