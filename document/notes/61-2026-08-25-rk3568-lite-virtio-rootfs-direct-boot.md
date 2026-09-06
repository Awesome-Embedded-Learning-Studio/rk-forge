# 61 — rk3568-lite 第二里程碑：virtio 存储 + rootfs 直启（2026-08-25）

> 首启（[60 号笔记](60-2026-08-25-rk3568-lite-qemu-machine-first-boot.md)）同日接着干：
> 机器加 virtio-mmio 传输层，`rootfs.ext4` 以 virtio-blk 挂 `/dev/vda`，
> 从「initramfs 冒烟 shell」跨到「真根文件系统直启」。半天，两断言 PASS。

## 0. 结论

| 项 | 结果 |
|---|---|
| 里程碑 | ✅ 内核挂真 ext4 根 → 真 rootfs shell → sentinel → poweroff，断言两条 PASS |
| 机器改动 | 4× virtio-mmio transport：`sysbus_create_simple("virtio-mmio", 0xfea00000+i*0x200, gpio 160+i)` + Kconfig select VIRTIO_MMIO/VIRTIO_BLK |
| DTS 改动 | 四个 `virtio,mmio` 节点（0xfea00000+ / SPI 160+），与机器一一对应 |
| 验收命令 | `QEMU=third_party/qemu/build/qemu-system-aarch64 boards/rk3568-atk/sim/boot-smoke.sh rk3568-lite rootfs` |
| 断言 | `VFS: Mounted root \(ext4 filesystem\)` / `RK3568-ROOTFS-SHELL-OK` |
| 回归 | M0 smoke 模式（initramfs 三断言）保持全绿 |

## 1. 为什么先做 virtio 而不是别的

- 内核 `.config` 里 `VIRTIO_BLK/VIRTIO_MMIO/VIRTIO_NET` 全 =y——**零重编**；
- `VIRTIO_MMIO_CMDLINE_DEVICES` 关闭，设备只认 DTB——正好匹配「DTS 驱动」路线；
- 60 号笔记的需求探测器首采为 0：当前工作负载不再拉新需求，**下一个设备由
  下一个里程碑拉出**——rootfs 直启就是选定的下一个工作负载；
- virtio 是「替身」教学线的起点：将来真 SDHCI 进来替换时，「替身 vs 真硬件」
  对比自成一章。

## 2. 选址与接线（sim-only，诚实标注）

真 RK3568 没有 virtio。地址选 `0xfea00000+0x200*i`、SPI 160+：外设区空闲
切片，高于真板实际 SPI 用量，机器注释和 DTS 注释都标了 sim-only。transport
数量取 4（盘/网/console 备用各一，留一格）。

## 3. 两个坑（都留在 boot-smoke.sh 注释里）

1. **grep BRE 的 `\(` 是分组不是字面括号**：日志里明明有 `Mounted root
   (ext4 filesystem)` 却断言 FAIL——假阴性比假阳性更隐蔽，统一改 `grep -qE`。
2. **`init=/bin/sh` 的自动出口必须 fifo 喂 stdin**：普通文件当 stdin，QEMU
   开工时读到 EOF 就关闭字符设备，25 秒后写入的命令永远不可见。fifo 的
   阻塞读会等数据，问题消失。

## 4. 下一步候选（按需添加，不开平行线）

- CRU 影子 + U-Boot proper：教启动链，需求由 U-Boot 工作负载拉出
  （fake PLL lock 坑位清单在 tobyc11/qemu-rk3399）；
- 真 SDHCI 模型：替换 virtio 替身，教真存储；
- evidence/forge verify 接口：双模式断言挂进 L1 雏形 + 第一条 sim 能力证据。
