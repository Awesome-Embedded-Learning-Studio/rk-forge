# 51 RK3588 ttyFIQ0 假挂死：RK860X 绑定 + I²C 超时恢复修复 (2026-08-01)

接 [48](48-2026-08-01-rk3588-gpu-firmware-embedded-gnome-desktop.md)：系统已经能进
GNOME，但切到 vendor `ttyFIQ0` 后出现无法输入、过一会乱码、整机像挂死；启动末尾同时出现
CPU4/CPU6 调压 `-110`。本篇记录一次重要纠偏：**FIQ console 已成功工作，真正故障在
RK8602/RK8603 调压器及其 I²C 总线恢复链路。**

## 现场证据

主日志：`document/logs/rk3588/202608012117.txt`。

ttyFIQ0 路径实际已注册：

```text
Registered FIQ tty driver
could not install nmi irq handler
console [ttyFIQ0] enabled
Registered fiq debugger ttyFIQ0
```

`irqchip.gicv3_pseudo_nmi=0` 与板级 `rockchip,irq-mode-enable = <1>` 跟 vendor 启动方式
一致。vendor FIQ debugger 本来就会在 NMI 不可用时使用 IRQ handler；所以
`could not install nmi irq handler` 不是 PIO 回退，也不是 ttyFIQ0 注册失败。

真正的新异常在启动末尾：

```text
cpu cpu6: _set_opp_voltage: failed to set voltage (...): -110
cpu cpu6: Failed to set regulator voltages: -110
cpufreq: __target_index: Failed to change cpu frequency: -110
cpu cpu4: _set_opp_voltage: failed to set voltage (...): -110
```

同时三路核心电源被错误地显示为 `fan53555-regulator 0/1-0042/43`。

## 根因：主线 fan53555 错误接管 RK860X

TOPEET vendor DTS 的核心电源是：

- I²C0 `0x42`：RK8602，CPU big core + memory rail。
- I²C0 `0x43`：RK8603，NPU + memory rail。
- I²C1 `0x42`：RK8602，另一组 CPU core + memory rail。

vendor 内核用独立 `CONFIG_REGULATOR_RK860X` / `rk860x-regulator.c`，而不是
`fan53555`。主线 v7.1 的 `fan53555` 却会认领 RK8602；旧板级 DTS 还把 RK8603 写成
`"rockchip,rk8603", "rockchip,rk8602"`，使不认识 RK8603 的主线驱动把它伪装成
RK8602。结果是 CPU 调频改压时 I²C transaction 超时，返回 `-ETIMEDOUT (-110)`。

主线 RK3x I²C 驱动还有第二个差异：超时后不会像 vendor 一样检测
`REG_INT_SLV_HDSCL`，也不会同时复位 I²C functional/APB reset domain。一次从设备拉住
SCL 就可能让控制器持续 wedged，外在表现包括调频失败、console 输入失去响应和整机停滞。

## 修复（一次合并，不做多版本试烧）

1. 从 vendor SDK 移植 `drivers/regulator/rk860x-regulator.c` 到 Linux v7.1，只做
   I²C probe API 和已删除头文件的兼容改造。
2. `kernel.config` 设置 `CONFIG_REGULATOR_RK860X=y`，明确关闭
   `CONFIG_REGULATOR_FAN53555`，避免双驱动竞争。
3. DTS 对齐 vendor：RK8602/RK8603 使用精确 compatible、
   `regulator-compatible = "rk860x-reg"`、`rockchip,suspend-voltage-selector`，并区分
   core/memory supply label。
4. I²C0/I²C1 DTS 加入 `i2c` 与 `apb` 两组 reset。
5. RK3x I²C 超时路径移植 vendor 的 IPD/state 日志、`SLV_HDSCL` 检测、双 reset domain
   复位和 bus timing 重算。

持久化补丁：

- `0002-arm64-dts-rk3588-topeet-panel.patch`：板级 DT（含完整 ttyFIQ0 与 RK860X）。
- `0003-soc-rockchip-port-vendor-fiq-debugger.patch`：vendor FIQ debugger 完整移植。
- `0004-regulator-rk860x-and-i2c-timeout-recovery.patch`：RK860X + I²C recovery。

## 构建与静态闸门

- 当前工作树完整 `Image + dtbs` 编译通过。
- 从 upstream v7.1 临时干净树顺序 `git am` 0001–0004，无冲突；完整内核再次编译通过。
- `.config`：`RK860X=y`，`FAN53555` 未设置。
- `vmlinux` 含 `rk860x_regulator_probe`、`rk860x_set_ramp`、新
  `rk3x_i2c_xfer_common`，不含 fan53555 符号。
- 工作树和干净回放树的 `rk3588-topeet.dtb` SHA-256 完全相同。
- FIT 明确封入本次 `Image`/DTB，`update.img` assemble 后通过 round-trip 解包自检。

## 真机结果

候选镜像：

```text
size:    3290329674 bytes
SHA-256: 134228df79b464d400c25bbdb629184260d6bf1f040ae65d361863df2dc9cb29
```

2026-08-01 烧入 eMMC 后用户确认：**系统正常进入，ttyFIQ0 可以持续输入，不再挂死。**
这次板验把日志中的调压/I²C 强信号从“高概率因果”提升为已验证修复；不能只凭一条
`-110` 就跳到结论，仍应保留“日志对齐 → vendor 差异 → 单候选 → 板验”的闭环。

板验后的 `dmesg | grep error` 只剩三条非本故障域信息：FIQ debugger 探测互斥的备用
`fiq` IRQ 和可选 `wakeup` IRQ 时各打印一次 `-ENXIO`，实际 `uart_irq` console 已注册；
另有 cfg80211 早期加载 `regulatory.db` 返回 `-2`，当前回退 world regulatory domain。
关键是 **RK860X/cpufreq 的 `-110` 已完全消失**。前两条保持 vendor IRQ 模式，不为清理
日志而伪造不存在的 IRQ；regdb 留到无线功能适配时连同签名与 built-in 加载时序一起解决。

## 教训

1. console 最后一条日志附近出现挂死，不等于 console 驱动是根因；先验证注册路径和其他
   subsystem 的确定错误。
2. compatible fallback 不是无害兼容：RK8603 fallback 到 RK8602 会让错误驱动成功 probe，
   比 probe 失败更危险。
3. vendor 同板 SDK 的价值不只在 DTS，还包括 timeout/recovery 等低概率硬件状态机处理；
   主线 API 更新可以适配，但不能随意删掉语义。
4. 反复烧板前必须做干净 patch replay、全量链接、FIT hash 和 update.img round-trip，自始至终
   只保留一个有证据的候选。

## 下一步

桌面、GPU、ttyFIQ0 和 DVFS 已稳定，继续对齐 vendor 处理 GT911：当前现象是 Goodix probe
复位后 I²C 读超时 `-110`，但用户态 `i2ctransfer` 能读到 `911`，重点审计 INT/RST GPIO
方向与地址选择时序，而不是继续改 console 或全局 I²C。

## 2026-08-02 后续纠偏

上述“已稳定”只代表 2026-08-01 当轮启动和输入验证，不能再表述为长期稳定结论。后续
0001–0006 救援镜像以及仅 blacklisting `cpufreq_dt_platdev_init` 的启动都出现过间歇性挂死；
同时 blacklisting Goodix + CPUFreq 的短期连续启动测试曾通过，但不足以完成因果归属。
因此 RK860X 移植解决了已观测到的错误绑定和部分 `-110`，却尚未证明消除了所有随机挂死。
后续必须使用 ttyFIQ debugger/lockup/pstore 证据定位，不能继续把触摸 IRQ 故障与系统挂死
合并成同一个已解决问题。
