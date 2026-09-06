# Note 102 · panthor M2n 达成（受控）：quad 采样合成执行器

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
3. **mutter 顶点约定（未竟）**：novert 类（~570 draw）pos 不在 t2 前
   两缓冲（dump 实测值=atlas 像素坐标/零）——疑似 gl_VertexID 生成式
   quad 或第三缓冲/属性描述符正式解析。这是 M2n-mutter 切片的下一刀。

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

## 5. 下一步（M2n-mutter 切片）

1. novert 类顶点来源考古：DCD 属性描述符正式解析（t1 ATTRIBUTE：
   Format/buffer_index/offset）vs gl_VertexID 假设检验
2. AFRC 图集读写（字形可见的前提；512² bf=13 的 encode/decode 语义）
3. 主合成链验证：壁纸（bf=2 线性落点已备）→ try_blit 线性读 →
   1024×600 bf=12 → VOP——screendump 主色统计
