# sim — Rockchip 仿真研究线

rk3568-lite / rk3588-lite 最小 QEMU 机器模型。**每板一个入口**
（`boards/<board>/sim/smoke.py`，板由位置 implied），共用机制在
`sim/engine.py`（QEMU 发现 / dtb 新鲜度 / 断言 / SOAK 浸泡），机器本体补丁
`qemu-sim-machines.patch` 施加于 `third_party/qemu`（v11.1.0）。叙事见
[notes/59](../document/notes/59-2026-08-24-rk3568-qemu-sim-m0-day0.md)～[70](../document/notes/70-2026-08-27-rk3588-systemd-ubuntu-login.md)。

全部工具纯 Python（仅标准库），Windows 原生可跑（QEMU fork 的 MSYS2 构建待课题）。

## 拉起

```bash
python3 boards/rk3568-atk/sim/smoke.py                  # U-Boot 交互（默认）
python3 boards/rk3568-atk/sim/smoke.py fit --check      # bootm 起 forge FIT
python3 boards/rk3588-topeet/sim/smoke.py               # Ubuntu 完整开机到 login
SOAK=120 python3 boards/rk3588-topeet/sim/smoke.py board --check   # 存活浸泡
```

| 模式 | rk3568-atk | rk3588-topeet |
|---|---|---|
| 默认 | uboot（U-Boot shell / booti 接力真根） | ubuntu（systemd 开机到串口 login） |
| fit | bootm 起 forge FIT（真板同款） | 待 SCMI 课题 |
| rootfs | virtio 真根直启 | 真板 DTS + Ubuntu 合体 |
| board | 真板 DTS 直启 | 真板 DTS 直启（8 核异构） |
| linux / virt | initramfs shell / Day-0 参考 | initramfs shell |

交互退出 `Ctrl-A x`；`SMP=1` 降核；`QEMU=` 覆盖；dtb/initramfs 按新鲜度自动重建。

## 一次性构建

```bash
sudo apt install meson ninja-build libglib2.0-dev libpixman-1-dev device-tree-compiler
cd third_party/qemu
git clone --depth 1 --branch v11.1.0 https://github.com/qemu/qemu .
git apply ../../sim/qemu-sim-machines.patch
mkdir -p build && cd build && ../configure --target-list=aarch64-softmmu && ninja
```

弹药由 `forge build` / `forge stage` 产出。

调试惯例：QEMU `-d unimp,guest_errors` 是需求探测器；未分配 MMIO 写在 ARM TCG
下是 external abort，哑铺图必须用 unimp；给 DTB 种节点时 interrupts 细胞数随
目标 GIC（rk3568=3，rk3588=4）。
