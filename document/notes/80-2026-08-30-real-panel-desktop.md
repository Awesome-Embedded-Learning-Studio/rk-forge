# 80 — 真面板桌面：GNOME 走 VOP2→DSI 全真管线（2026-08-30）

> 战役五。目标：桌面弃 virtio-gpu 虚屏，GNOME 经 rockchipdrm→VOP2→DSI 面板
> 路径扫描输出——真 DTB、iommu 挂着、每个环节都是真家伙。前置：战役二的
> rk806 已把 DSI 供电链解锁（note 79 §7）。

## 0. 结论

| 项 | 结果 |
|---|---|
| **真面板桌面点亮** | ✅ `GPU_BACKEND=vop`：mutter 经 rockchipdrm modeset `card0-DSI-1: connected→enabled`，gnome-shell 起动，VOP 扫描输出推画面，SDL 窗口呈现干净桌面（screendump：1024x600 chroma 8/9、花屏带清零） |
| iommu v2 页表走查 | ✅ vop_mmu 是 **IOMMU v2**（compatible rk3568-iommu → `iommu_data_ops_v2`，of_match 实证）：DTE 索引 **iova>>22**（4MB 段）、DTE_ADDR 寄存器值带 valid 位需掩 `0xfffff000`。修正前恒等回退（fb 读到内核早期区） |
| 逐页缝合扫描输出 | ✅ bo 的物理页**不保证连续**（页表实测跨 4MB DTE 边界拓扑变化、PT1[0] 无效位）——线性 base+stride 映射产生 30% 花屏带（洋红垃圾段）。改为每 4KB 页单独走 iova 翻译后拷连续 staging，任意拓扑正确 |
| smoke.py 形态 | `GPU_BACKEND=vop`：不挂 virtio-gpu；FAST 黑名单按形态条件化（vop 时 rockchipdrm 必须活） |

## 1. 攻坚链（三刀）

```
①GPU_BACKEND=vop：rockchipdrm 独占 DRM → mutter modeset DSI-1 成功（enabled）
    ↓ 但 fb 读到 0x258000（内核早期区）——翻译恒等回退
②v2 页表语义：DTE>>22 + valid 位掩码 → iova→CMA 实址咬合（0x258000→0x273ce000）
    ↓ 但画面 30% 花屏带（洋红）——bo 物理页不连续
③逐页缝合：4KB 粒度走查 + staging 拷贝 → chroma 8/9、洋红清零
```

## 2. 关键取证手段（复用价值）

- `qom-get /machine mmu-dte / mmu-status`（本役新加导出）+ `vop-fb-mst/phys/dsp`
  → 一眼分辨"内核编错地址"vs"翻译没咬合"
- monitor `xp` 直接 dump guest 页表（DTE/PTE）验物理连续性——定位缝合必要性
- PPM 结构分析判花屏类型：顶栏色/白字/壁纸色 = 画面在；均匀洋红带 = 读错段；
  相邻行哈希 = 条纹（跨度错）检测

## 3. 与旧战役的对照（为什么这次成了）

战役四（note 74）当年摘 `iommus` 的三个前提都已翻案：
1. "iommu 页表翻译覆盖不全" → 实为 **v1/v2 语义错配**，v2 走查修正后完全覆盖；
2. "dma 半残 fb_dma=0x0" → 伴随翻译错读的误判；
3. overlay 手术 → 宪法 v2 已禁，真解在 QEMU 侧行为建模。
**当年绕过的每一刀，都以真硬件行为建模的方式正面还清了。**

## 4. 待办

- 冷启动计时（真面板 + llvmpipe，对照 79s/virgl 45s）
- 输入：virtio 键鼠在场（SDL 窗口光标应可用）；gt911 真触摸与真面板的组合终审
- vmstate 快照役（现多了 spi2/i2c2/gpio3/rk806 影子要迁移状态）
- panthor/G610（note 76 预研）——真管线的最后一环：真 GPU
