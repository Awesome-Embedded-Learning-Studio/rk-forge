# 74 — VOP2 战役（四）：GNOME 桌面点亮与冷启动地板（2026-08-29）

> 战役三解放 KMS 用户态后，桌面卡在 mutter 选不出合法 buffer。本役打通
> 最后三环（格式协商 → PMU/IOMMU 供电链 → 中断时序），**Ubuntu 26.04
> GNOME 桌面在 rk3588-lite 仿真里完整点亮**：顶栏活时钟、dock、Ubuntu 橙
> 壁纸，无花屏。随后实测开机到首帧 ~79s 是 TCG 冷启动地板，并定位快照
> 工作流的真实堵点（机器模型缺 vmstate）。

## 0. 结论

| 项 | 结果 |
|---|---|
| **GNOME 桌面点亮** | ✅ gdm 自动登录（rk-forge 用户）→ gnome-shell 50.1 Wayland + llvmpipe 首帧；1024x600 全屏 Cluster0-win0；flip_done/commit 超时 **0**（7 分钟运行） |
| 首帧截图 | ✅ `sim/fbdump.py`：fb=0x7de00000（CMA 直读）、PNG 真彩（125,506 像素原生 Ubuntu 橙 #E95420 校验） |
| 格式协商修复 | ✅ 0020（RK3588 cluster 窗口补 LINEAR modifier）+ 0021（砍掉 AFBC-only 的 XRGB/XBGR2101010）→ mutter 回落到 8bpc，llvmpipe 可产线性格式 buffer |
| PMU/iommu 供电链 | ✅ PMU mem-chain 位翻译表 + DCPHY PLL_LOCK 影子 + repair-status **联合掩码**（own+祖先——genpd 拒绝父断子通，联合掩码是 probe 活命关键，own-bit 版实测 -22 连坐） |
| vop_mmu 毒源 | ✅ SIM-DIAG 0022 定位：`rk_iommu_force_reset` 的 DTE 写读回在未实现模型上 -EFAULT → `runtime_error` 粘滞 → vop 永远 -EINVAL。影子化 MMU 状态寄存器 + FORCE_RESET 语义后闭环 |
| sim 摘除 `iommus` | ✅ 影子 MMU 两级页表翻译对 rockchip gem 的 iova 布局（drm_mm 从 0 起分配）覆盖不全（fb#1 dma=0x0、DTE[2]=0 指不到内核 .text 0x280000）→ 叠加层删 `&vop` 的 `iommus`，dma 直通，fb 物理地址即 CMA 地址。**只动 sim overlay，真板 DTS 不动** |
| DSP_INFO 差一 | ✅ 寄存器存 hact-1/vact-1，QEMU 扫描输出与 fbdump 都 +1（否则 1023x599 对角条纹） |
| **冷启动地板** | ❌↝实测 5 轮：93.2 / 79.1 / 81.0 / 78.9 / 79.0s。guest 侧拉杆（动画关、LP_NUM_THREADS、裁服务、journald 内存化、内核 quiet）**全部无效**——瓶颈是 login→首帧 ~46s 的纯模拟 CPU 计算（llvmpipe JIT + shell 冷启），TCG 物理地板 ≈79s |
| 快照工作流 | ⛔ savevm/loadvm 机制走通，但机器模型 11 个影子设备 **0 个 VMStateDescription**：restore 后 VOP 寄存器归零（fb=None 实证）、watchdog/RCU Stall panic（MTTCG 和单线程都死）。堵点明确：补 vmstate 才能启用 |

## 1. 点亮前的最后三环（因果链）

```
mutter 50.1 choose_onscreen_egl_config 偏好 alphaless_10bpc（XR30 优先）
  → RK3588 cluster 窗口 10bpc 仅 AFBC 合法（rockchip_drm_vop2.c:412 拒 XR30+LINEAR）
  → 而 IN_FORMATS blob 是格式×modifier 笛卡尔积，表达不了这种条件限制
  → 0021 砍格式（kernel 正道）+ 0020 补 LINEAR（能力表自相矛盾的另一半）
  → mutter 回落 XR24 族 → llvmpipe 线性 buffer 成功
DCPHY PLL_STAT0 无 BIT(0) → mipi-dcphy probe 死等 → 0xfeda0000/0x4000 影子补 PLL_LOCK
vop_mmu force_reset 读回 0 → -EFAULT 毒 runtime_error → 0022 printk 定位 → 影子化
iommu 页表翻译半残 → sim overlay 删 iommus（诚实差异第 2 条，见叠加层头注）
100µs 脉冲中断在 TCG 下跑不赢 vCPU 投递 → VOP 改回电平保持模型 → flip 事件闭环
```

## 2. 提速实验全记录（自动化闭环）

工具链：`framehunt.py`（headless 启动 + 串口标记 + fbdump 轮询 + 时间线报告，
`KEEP=1` 留守 / `FAST=1` 内核 quiet / `SMP=` 可调）+ `sercmd.py`（串口 TCP 登录
执行命令，`CMD_TIMEOUT` 放宽 TCG 慢命令）。guest 时间线：内核→gdm 21.9s，
autologin 开门 29s，gnome-shell 首日志 36.6s，首帧 ~50-55s（monotonic）。

| 轮 | 拉杆 | 首帧 |
|---|---|---|
| 基线×2 | 无 | 93.2 / 79.1s |
| 2 | 动画关（dconf system-db）+ LP_NUM_THREADS=8 + 裁 udisks2/upower/ModemManager + journald volatile | 81.0s |
| 3 | + 内核 quiet loglevel=2 + QEMU 去 VOPDBG fprintf | 78.9s |
| 4 | + 摘 0023（每 plane commit 一条 printk） | 79.0s |

结论：**全在噪声内**。用户态 16.3s 就到 graphical.target，胖的是后面
llvmpipe/shell 的模拟计算。accountsservice 是 gdm 硬依赖——mask 它 gdm 直接
exit 1 重启 13 次后躺平（journal 有 `Failed to contact accountsservice` 实证），
裁服务清单里它永远不能动。

## 3. 本役踩的坑（重要：内核直编翻车）

- **`make Image` 直接编 ≠ forge 内核**：树里 .config 曾被换过，直编出 26MB
  残核（forge 产物 46MB），3/3 次卡死在 journald 起动（guest 5.9s，全核
  `cpu_do_idle`——事件永不来型挂死）。正道 = `merge_config.sh`（defconfig +
  boards/rk3588-topeet/kernel.config）→ `olddefconfig` → 注入
  `CONFIG_EXTRA_FIRMWARE_DIR`（Mali CSF 固件内嵌，缺了直接编不过）→ `make
  Image dtbs`。重编后 46.6MB、一次点亮。
- **`__log_buf` 地址随内核变**：klogdump 的 phys 地址是 System.map 换算
  （virt-0xffff800080000000），换内核必须重取，不然 xp 出乱码。
- **restore 换 SMP 数直接拒**：vCPU 数是迁移状态的一部分。
- fbdump 通道序：mutter/llvmpipe 实际下 **XBGR 内存序（R,G,B,X）**，直拷即
  真 RGB；交换与否用 `FBFMT` 环境变量（默认 xb24）。证据法：壁纸橙色像素
  计数（e95420 原生 vs 2054e9 交换）。

## 4. 工具沉淀（全部 Python 纯标准库，sim/）

- `framehunt.py`：首帧狩猎 + 时间线（本轮提速实验主力，KEEP/FAST/SMP）
- `sercmd.py`：串口 TCP 会话客户端（登录态机 + PS1 标记 + CMD_TIMEOUT）
- `snapshot.py`：桌面态快照 create/restore/drop（机制通，等 vmstate 启用，
  头注有堵点记录）
- `gdbfreezegrab.py`：补了端口参数（本役扫挂死全核）
- `gbmprobe.py` / `gbmshim.c`：GBM/EGL 格式与 modifier 判决（战役三遗产）
- `klogdump.py`：`__log_buf` 物理地址随内核更新（坑见上）

## 5. 欠账与下一步

1. **机器模型 vmstate**（快照工作流前置）：给 VOP（regs+fb+ticker）、vop_mmu、
   PMU mem-chain、DCPHY 四个带状态影子补 `VMStateDescription`，之后
   `snapshot.py restore` 才能从 79s 降到秒级。这是下一战役的首选课题。
2. rootfs.ext4 里的本役 in-guest 变更（dconf 动画关、服务 mask、LP_NUM_THREADS、
   journald volatile）——对提速无贡献，留在镜像里无害但不可复现；若要固化应走
   forge stage-rootfs 定制，若不要可在下次 rootfs 重建时自然冲掉。
3. DSI dw-mipi-dsi2 传输影子仍是轮询式（吵）、PL330 无真模型、fbcon 原生路径
   仍未修——老欠账。
4. SIM-DIAG 0022 留守（printk 便宜、未来战役还得用）；0023 已摘（提交
   d16022aba 为 HEAD，0023 的 commit 已 reset 丢弃，series 已更新）。
