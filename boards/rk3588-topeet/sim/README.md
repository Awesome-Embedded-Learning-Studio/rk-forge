# rk3588-topeet sim 研究线

`rk3588-lite` —— **异构最小机器**（4×Cortex-A55 + 4×Cortex-A76，全组织首台
异构仿真），机器本体在 `third_party/qemu/hw/arm/rk3588-lite.c`（补丁经
`../rk3568-atk/sim/qemu-sim-machines.patch` 入库，服务两板）。

拉起/断言脚本共用 `../rk3568-atk/sim/boot-smoke.py`（Python 跨平台）：

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite           # 交互直入（initramfs shell）
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite linux --check   # 8 核异构三断言
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite rootfs --check  # 真板 DTS + Ubuntu 真根合体
```

| 文件 | 作用 |
|---|---|
| rk3588-lite.dts | 八节点异构最小 DTS（A55@0x0-0x300 + A76@0x400-0x700） |

board 模式已通（真板 DTS 三断言，modify_dtb 把 uart2 从 FIQ 调试器还给 8250）；
uboot/fit 待 SCMI 仿真课题（rk3588 U-Boot 靠 BL31 的 SCMI 服务，笔记 68 §3）。叙事见
[notes/67](../../../document/notes/67-2026-08-26-rk3588-lite-heterogeneous-ubuntu.md)。
