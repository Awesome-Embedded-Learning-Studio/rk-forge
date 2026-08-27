# rk3568-atk sim

rk3568-lite 板卡资产。入口 `smoke.py`（uboot/fit/rootfs/board/linux/virt），
共用机制见 [sim/](../../../sim/)。

| 文件 | 作用 |
|---|---|
| smoke.py | 本板入口（模式表 + 提示；机制来自 sim/engine.py） |
| rk3568-lite.dts | 七节点最小 DTS，只描述已建模设备（dtb 自动重建） |
