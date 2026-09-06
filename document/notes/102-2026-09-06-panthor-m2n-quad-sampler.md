# Note 102 · panthor M2n 达成：quad 采样合成执行器 + 首个可见桌面内容

日期：2026-09-06 · 战役七第二十一篇 · 上一节：note 101（采样 FS 侦察）

## 0. 摘要

**采样 draw 在受控矩阵下真执行**：RUN_IDVS 时从真描述符链提取
（FS 代码 TEX 族门 + SRT_2→Texture→Surfaces→Plane 纹理链 + t2 顶点
Buffer），RUN_FRAGMENT 时光栅化（NDC 轴对齐映射 + NEAREST + 按 RT
bf 提交）。**矩阵 6/7 PASS**（2×2/8×8/32×32/64×64 × 全屏/子区域；
128×128=AFRC 欠账）+ 常量色/clear 回归全绿。FSQUAD=1 门控。

## 1. 实现结构（hw/arm/rk3588-lite.c）

```
RUN_IDVS (case 6, FSQUAD):
  extract_fs_sample:
    门：r33==4 + SPD Binary 首页扫 TEX 族（0x125/128/129/12a/12f）
        + SRT_2 t4 恰 1 纹理 + plane dims 与 Texture 一致
        + plane 类型（1=Generic/6=AFBC；Generic ordering 1=U/2=线性）
    纹理：t4 → Texture{W/H@word1 min-1, Surfaces@+0x10} →
          Plane{Pointer@+8, RowStride@+16, dims@+24hi}
    顶点：t2 Buffer 数组（32B 项，Addr@+8）三候选解析：
          交错 16B / 分离 8B（pos,uv）/（uv,pos）——quad_sane 择优
    TEX_FETCH(0x125) 模式：uv=像素坐标（texelFetch 语义）
RUN_FRAGMENT:
  fs_fill(M2l) > fs_sample_pending 光栅化 > try_blit > clear
  raster_quad：线性 staging 采样 → 按 bf 提交
    （bf=1 U-tile 逐像素 / bf=2 线性 / bf=12 M2k sb 布局）
```

## 2. 根因战果（本轮三连破）

1. **纹理 payload 置换根因**：M2j blit src 三形态判别缺"线性"分支
   ——mesa 纹理上载的 staging 缓冲被当 U-tiled 读 → AFBC body 写进
   置换过的纹理 → 采样错乱。修=find_src_plane 带出 plane 头
   w0[11:8] Clump ordering，blit_read_px 加 ⓪线性形态。连带破案：
   之前"AFBC 32×8 曲线"（渐变明文 256/256 XOR 拟合）其实是这个置换
   的伪像——真身=M2k 自己写的 16×16 线性 body 布局。
2. **mutter 渲染种群**（GDM 机 GPUFBG/GPUQUAD 普查）：字形→512²
   **bf=13 AFRC 图集**（~430 draw/boot）、壁纸→1920×1080 **bf=2 线性**
   （3840×2160 纹理下采样）、主合成→1024×600 bf=12。172+1 draw 的
   RUN_IDVS→RUN_FRAGMENT 配对完美（无 pending 偷渡）。
3. **mutter 顶点约定（已考古）**：novert 类（~570 draw）的 t2 只有
   **一个 32B Buffer=8 浮点 pos-only**（值在变换空间、含 NaN），uv
   由 VS 从 FAU 常量计算——TEX_FETCH 主合成类=**VS 语义 draw**，
   超出固定功能 quad 采样器的类（诚实边界）。mutter 种群三分类：
   ①TEX_SINGLE+NDC 交错顶点（171 draw，本采样器覆盖，但落点是
   AFRC 图集）②TEX_FETCH+变换 pos-only（VS 语义，~570）③纯 blit
   （RUN_FRAGMENT，M2h/i 路径覆盖）。

## 3. 验收矩阵

| 变体 | 结果 |
|---|---|
| TEXSIZE 2/8/32/64 全屏 | PASS×4 |
| 2×2/32×32 子区域 QUAD | PASS×2 |
| 128×128 | FAIL（AFRC bf=13 上载，payload 空→黑；诚实边界） |
| gt 常量色（蓝/半蓝-quarter） | PASS×2 |
| gc clear | PASS |

受控测试 sim/glestexture.py 参数化：TEXSIZE/QUAD/TEXGRAD（渐变
明文攻击探针，x·4/y·4 防混叠——x·8 在 64 宽 mod 256 折叠的坑）。

## 4. 边界（note 76 纪律）

- NEAREST、无 blend、轴对齐 quad、RGBA8；LINEAR/混合/旋转/
  多纹理（t4>1 弃权）不在列
- AFRC（bf=13）纹理/图集读写=欠账（字形路径全卡在这）
- 真 AFBC compressed（非未压缩编码）超出；本模型 AFBC=sim 自洽布局
- mutter novert 类顶点解析未通（§2.3）——桌面可见尚未达成

## 5. 后续追加（同日深夜）：bf=13 翻案 + 全矩阵 + 可见内容

1. **bf=13 = "AFBC Tiled"（u-interleave header 数组），不是 AFRC**——
   旧标签错误（AFRC=Plane type 10，且 sim 的 TEXTURE_FEATURES_0=0
   → bit25=0 → mesa has_afrc=false 根本不会选 AFRC）。加
   `rk3588_afbc_hdr()`（线性/tiled 双寻址）贯穿 raster 提交、try_blit
   写、clear、纹理读、blit 读。
2. **第 4 种顶点形态**：步长 32B 交错（pos@+0、uv@+16 像素坐标）=
   mesa 上载 blit quad（TEX_FETCH）——**novert 类全解**（326 pending
   = 326 raster，零弃权）。
3. **clear 合并**：mesa 把 glClear 并进 draw job 的 FBD（RT bit31），
   staging 先铺 clear word（quad 外=clear 色非残内存——受控测试曾靠
   新鲜页面侥幸的坑）。
4. **受控矩阵 9/9 PASS**（2..256 全屏 + 4 子区域含 0.25..0.75）+
   gt/gc 回归绿。
5. **GPU 仿真上第一个可见桌面内容**：screendump 640×480 出现
   701 像素 0xaaaaaa 文字行（x∈[200,438] y∈[226,238]）——字形管线
   全链贯通（draw→bf=13 图集→合成→VOP）。壁纸已 raster 进自身
   3840×2160 bf=13 缓冲，但合成到 scanout 的最后一环仍黑（下轮）。

## 6. 下一步（M2n-visible 收官）

壁纸/主内容 → scanout 的合成链考古：主合成 draw 的 FBO（640×480/
1024×600 bf=12）由哪条路径写（raster 消费/blit/GPUFBG），src 链
（壁纸 bf=13 tiled 读已修）。screendump 主色统计 >1% 即里程碑。
