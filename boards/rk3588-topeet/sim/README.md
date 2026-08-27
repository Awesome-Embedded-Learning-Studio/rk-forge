# rk3588-topeet sim

rk3588-lite（4×A55 + 4×A76 异构）板卡资产。入口 `smoke.py`
（ubuntu/rootfs/board/linux；uboot/fit 待 SCMI 课题，见
[notes/68](../../../document/notes/68-2026-08-26-rk3588-real-dtb-full-port.md)），
共用机制见 [sim/](../../../sim/)。

| 文件 | 作用 |
|---|---|
| smoke.py | 本板入口（模式表；机制来自 sim/engine.py） |
| rk3588-lite.dts | 八节点异构最小 DTS（A55@0x0-0x300 + A76@0x400-0x700，dtb 自动重建） |
