# rk3588-topeet sim 研究线

`rk3588-lite` —— **异构最小机器**（4×Cortex-A55 + 4×Cortex-A76，全组织首台
异构仿真），机器本体在 `third_party/qemu/hw/arm/rk3588-lite.c`（补丁经
`../rk3568-atk/sim/qemu-sim-machines.patch` 入库，服务两板）。

拉起/断言脚本共用 `../rk3568-atk/sim/boot-smoke.py`（Python 跨平台）：

```bash
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite           # 交互直入（initramfs shell）
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite linux --check   # 8 核异构三断言
python3 boards/rk3568-atk/sim/boot-smoke.py rk3588-lite rootfs --check  # Ubuntu 真根直启
```

| 文件 | 作用 |
|---|---|
| rk3588-lite.dts | 八节点异构最小 DTS（A55@0x0-0x300 + A76@0x400-0x700） |

真板控制台是 ttyFIQ0（FIQ 调试器，靠 BL31）——sim 走普通 8250（uart2@
0xfeb50000），board/uboot/fit 模式因此待课题。叙事见
[notes/67](../../../document/notes/67-2026-08-26-rk3588-lite-heterogeneous-ubuntu.md)。
