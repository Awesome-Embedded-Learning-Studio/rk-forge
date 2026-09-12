# 77 — 同 DTB 的 cmdline virtio 桌面路径（2026-08-29）

## 裁决

用户允许用 virtio 改善仿真桌面，但品牌边界不变：**仿真和真机输入同一份
`rk3588-topeet.dtb`**，不维护 sim DTB 分支，也不让 QEMU 注入或改写外设节点。

隔离边界放在 bootargs：QEMU 提供四个 sim-only virtio-mmio transport，Linux
仅在出现 `virtio_mmio.device=` 时创建对应 platform device。真机 bootargs 没有
这些参数，所以新增驱动配置和代码保持休眠，不改变真机设备拓扑。

## 实现

- `smoke.py` 的 board/rootfs/ubuntu/desktop 全部加载内核构建出的真 DTB；
- 删除 `rk3588-lite` 的 virtio FDT 注入、UART enable 和 FIQ disable 修改；
- 开启 virtio-mmio cmdline、virtio-console、virtio-blk 和 virtio-gpu；
- 四个 transport 使用 `0xfea00000 + n*0x200`、GIC SPI 160..163；
- 新语法 `:spi160:` 通过真 DTB 的 GIC irqdomain 把硬件 SPI 映射成 Linux virq；
- transport 强制使用 modern virtio；virtio-gpu 不支持 legacy transport；
- `gpu-probe` 在 guest 内断言 `/sys/class/drm/card0` 和 `/dev/dri/card0`，不靠
  host 命令行猜测设备是否工作。

QEMU direct-kernel loader 会正常写 `/chosen`、内存和 PSCI 启动元数据，因此运行
时 FDT 不追求逐字节不变；硬件外设节点不再由 sim 路径增删或改 status。

## 已验证

- QEMU `qemu-system-aarch64` 重编通过；
- Linux 7.1 Image 重编通过；
- 同一真 DTB 下四个 virtio-mmio IRQ 映射成功，hvc0、virtio-blk 工作；
- Ubuntu 26.04 到达 `graphical.target` 和 login；
- 2D virtio-gpu 在 guest 内创建 DRM `card0`（仅功能验证，无 3D 提速）。

## 尚缺的宿主条件

本机没有 `libvirglrenderer-dev`/`libgbm-dev`，且当前会话没有免密 sudo，故不能
在本轮重配出 `virtio-gpu-gl-device`。在安装依赖、以
`-Dvirglrenderer=enabled -Dopengl=enabled` 重配 QEMU 并跑出桌面首帧前，不宣称
已经获得加速或接近 1:1 真机速度。
