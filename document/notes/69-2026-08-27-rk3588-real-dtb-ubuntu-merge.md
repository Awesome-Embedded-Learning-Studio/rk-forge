# 69 — RK3588 真板 DTS + Ubuntu 真根合体（2026-08-27）

> 用户追问「我们不是启动的 Ubuntu 嘛，这个真不处理？」——成立：真板体验的
> 完整形态是**真板 DTS + Ubuntu 真根**同场，此前两者分居（board=真DTS+busybox、
> rootfs=simDTS+Ubuntu）。合体的技术障碍是真板 DTB 没有 virtio 节点（fit 模式
> rootwait 永等的老坑），解法是 modify_dtb **动态补种**。一个跨板大坑收尾。

## 0. 结论

| 项 | 结果 |
|---|---|
| 合体模式 | ✅ rk3588 `rootfs --check` 两断言 PASS（真板 DTS + Ubuntu ext4 + 8 核异构） |
| 嫁接机制 | modify_dtb 里 fdt_add_subnode 种 4 个 virtio_mmio 节点（QEMU 给 DTB 缓冲留 2×+20KB 余量，种得下）；sim DTB 自动跳过防重复 |
| 大坑 | rk3588 GIC 是 **#interrupt-cells = <4>**（带 partition 尾巴），rk3568 是 3——3 细胞的嫁接中断被内核判畸形，`IRQ index 0 not found`，盘不出现、rootwait 永等 |
| 回归 | rk3588 rootfs/board/linux 全绿 |

## 1. 跨板教训：中断细胞数不通用

给 DTB 动态种节点时，`interrupts` 的细胞数跟着目标 GIC 走：rk3568 `<0 160 4>`、
rk3588 `<0 160 4 0>`（第 4 细胞 = PPI partition，SPI 填 0）。写死 3 细胞在
rk3568 上全绿、在 rk3588 上 IRQ 解析 ENXIO——**两板同代码不同结果时，先数
binding 的细胞**。诊断法：让 QEMU 把 modify 后的 DTB 落盘（临时 fopen+fwrite）
fdtdump 验尸，对照真板节点里的 interrupts 格式。

## 2. 复现

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite rootfs --check
# 交互（Ubuntu dash shell）：
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite rootfs
```

真板体验矩阵至此完整：真板 DTS（board）、Ubuntu 真根（rootfs）、两者合体
（rootfs 即是）、U-Boot/bootm 在 rk3568 侧闭环、rk3588 侧等 SCMI 课题（68 号
笔记 §3）。
