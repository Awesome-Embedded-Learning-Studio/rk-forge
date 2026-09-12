# rk3588-topeet sim

rk3588-lite（4×A55 + 4×A76 异构）板卡资产。入口 `smoke.py`
（ubuntu/rootfs/board/linux；uboot/fit 待 SCMI 课题，见
[notes/68](../../../document/notes/68-2026-08-26-rk3588-real-dtb-full-port.md)），
共用机制见 [sim/](../../../sim/)。

| 文件 | 作用 |
|---|---|
| smoke.py | 本板入口（模式表；机制来自 sim/engine.py） |
| rk3588-lite.dts | 八节点异构最小 DTS（A55@0x0-0x300 + A76@0x400-0x700，dtb 自动重建） |

`board`、`rootfs`、`ubuntu`、`desktop` 模式直接加载内核构建产出的
`rk3588-topeet.dtb`，机器模型不再向 FDT 添加 virtio 节点，也不改 UART、FIQ、
显示等硬件节点。QEMU 的通用 direct-kernel loader 仍会填充 `/chosen`、内存和
PSCI 等启动元数据；输入 DTB 与真机完全同源。仿真专用的 block、console 和
可选 GPU 由 `virtio_mmio.device=` kernel cmdline 枚举；真机没有这些启动参数，
因此同一 Image/rootfs/DTB 上不会创建 virtio 设备。

```bash
# 普通板级路径
python3 boards/rk3588-topeet/sim/smoke.py ubuntu

# virgl 加速桌面（QEMU 必须带 virtio-gpu-gl-device）
GUI=1 python3 boards/rk3588-topeet/sim/smoke.py desktop

# 仅验证 virtio-gpu KMS 枚举；2D 后端不会加速 3D
GPU_BACKEND=2d python3 boards/rk3588-topeet/sim/smoke.py gpu-probe --check
```

`desktop` 默认要求本仓 QEMU 编入 virgl/OpenGL；当前宿主若缺
`libvirglrenderer-dev` 和 `libgbm-dev`，QEMU 会明确报告
`virtio-gpu-gl-device` 不存在。`GPU_BACKEND=2d` 只用于枚举/KMS 回归，不能改善
GNOME 的 3D 渲染速度。
