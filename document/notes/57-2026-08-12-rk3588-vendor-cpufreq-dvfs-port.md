# 57 — RK3588 vendor CPUFreq/DVFS 事务移植（2026-08-12）

接 [51](51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md)、
[53](53-2026-08-02-rk3588-hard-lockup-ramoops-watchdog.md) 和
[54](54-2026-08-02-rk3588-vendor-vop2-handoff-hardlock-fix.md)。此前系统随机 hard lock
伴随 `fd880000.i2c` 超时及 CPU4 调压失败：

```text
cpu cpu4: _set_opp_voltage: failed to set voltage (...): -110
cpu cpu4: Failed to set regulator voltages: -110
cpufreq: __target_index: Failed to change cpu frequency: -110
```

## A/B 结论

最终的无烧录 A/B 结果为：

- `initcall_blacklist=panthor_init,cpufreq_dt_platdev_init`：稳定；
- 只保留 `initcall_blacklist=cpufreq_dt_platdev_init`：Panthor 正常 probe，
  `/dev/dri/renderD128` 存在，桌面和登录稳定；
- CPUFreq 开启时会复现随机挂死。

因此 GPU 不是这个阶段的必要条件，CPUFreq/DVFS 路径才是迁移目标。blacklist 只用于
隔离故障，不进入正式镜像。

## vendor 对齐结果

Rockchip 5.10 SDK 的 RK3588 不是直接依赖通用 `cpufreq-dt` 单电源切换，而是在
`rockchip-cpufreq.c`/vendor OPP helper 中执行完整事务：

1. 每个 cluster 同时配置逻辑 `cpu`、`mem` 两路 supply；
2. 升频顺序为 intermediate clock → mem 电压 → CPU 电压 → SRAM read margin → 目标频率；
3. 降频顺序为 intermediate clock → read margin → 目标频率 → CPU 电压 → mem 电压；
4. 失败时恢复旧频率、read margin 和两路电压；
5. RK3588 通过 litcore/bigcore/DSU GRF 更新 SRAM read margin；
6. 大核达到 2208 MHz 时临时禁止 cluster deep-idle state，降频后恢复；
7. CPU clock 仍由 SCMI 提供，中间频率通过 vendor 定义的 rate 低位标志传递。

Linux 7.1 已删除 vendor 5.10 的一体化 `set_opp` API，所以不能逐行复制。新实现使用
主线 `dev_pm_opp_config` 的 `config_regulators` 和 `config_clks` 回调，把以上语义保持在
同一 OPP 事务中；新驱动先安装回调，再由自身注册 `cpufreq-dt` platform device。
`CPUFREQ_DT_PLATDEV` 被关闭，系统中不存在通用和 Rockchip 两套并行注册路径。

本次没有迁入 vendor 的 PVTM/binning/system-monitor 大框架。当前主线 DTS 已提供保守、
固定的 RK3588 OPP 表，本次故障所缺的是电源/频率/read-margin 的事务语义，而不是根据
芯片 bin 动态扩展超频 OPP；把后者整包移入会扩大故障面。

## 固化内容

- `0011-cpufreq-rockchip-port-rk3588-vendor-dvfs-sequencing.patch`
  - 新增 Linux 7.1 `drivers/cpufreq/rockchip-cpufreq.c`；
  - Kconfig/Makefile 接入 `CONFIG_ARM_ROCKCHIP_CPUFREQ`；
  - DTS 增加 litcore/bigcore0/bigcore1/DSU GRF；
  - 三组 OPP 改为 cpu/mem 双 supply，并加入 read-margin/intermediate/idle threshold；
- `kernel.config`
  - `CONFIG_ARM_ROCKCHIP_CPUFREQ=y`；
  - `CONFIG_CPUFREQ_DT=y`；
  - `CONFIG_CPUFREQ_DT_PLATDEV` 关闭。

Topeet 板上每个 cluster 的 `cpu-supply` 与 `mem-supply` 仍指向同一个物理 RK860X
regulator，这与 vendor Topeet DTS 一致；双 supply 是保持 vendor OPP 事务接口和顺序，
不是虚构第二颗稳压器。

## 构建与静态门禁

- Arm GNU 15.3 单文件编译：`rockchip-cpufreq.o` 通过；
- `rk3588-topeet.dtb` 编译通过；
- 全量 `Image + dtbs` 编译和最终链接通过；
- 从干净 v7.1 树依次重放当前 `series`（0001–0006、0009–0011）通过；
- 重放树的 Kconfig、Makefile、新驱动和最终 DTS 与构建树逐字节一致；
- `vmlinux` 存在 Rockchip driver initcall、clock/regulator callbacks；
- 最终配置不存在 `CPUFREQ_DT_PLATDEV`，boot script 不存在任何 initcall blacklist；
- `boot.img` 的 FIT hash 与本轮 Image/DTB hash 一致；
- RKAF+RKFW assemble 及六分区 round-trip 自检通过。

Ubuntu rootfs 本轮没有变更。当前 WSL 的旧 rootfs/pack 产物由另一 UID 生成，新的
fakeroot stage 在 fake `chown(0:0)` 时返回 `EINVAL`；因此本轮没有使用失败后的不完整
stage，而是逐字节复用上一轮已上板验证的 `rootfs.ext4`，仅重新生成 loader、U-Boot
FIT、含新 Image/DTB 的 boot FIT 和最终 update.img。

## 待烧候选

```text
update.img size:    3290329674 bytes
update.img SHA-256: 063b2670c2676f076e0dc080bc3d8b203ff5af8ec1437c2eddb1e759cbaed114
boot.img SHA-256:   bb3ae6548c9e1f7bb935bcedb70083b0d0fb9e11703b80d95304e393cbb523e7
rootfs.ext4 SHA-256:e432f21de8bead6e647910c90dc319da1e5edb8ac0fe732b21d5186af43660c8
Image SHA-256:      391a7a0a282fb9543d2aeaffde5f8676700953be90ef89ecd0e1b37f92d5882b
DTB SHA-256:        cdbe88a028c33d8e55237a7159456c920c638ba26976d1eccc2e5c2b29cb950e
```

这是 CPUFreq 正式迁移候选，host 静态门禁已经通过，但尚不能在真机板验前写成稳定结论。

## 上板验收

启动参数必须没有 `initcall_blacklist`，三组 policy 必须全部出现：

```sh
cat /proc/cmdline
dmesg | grep -iE 'Rockchip RK3588 CPUFreq|cpufreq|rk3x-i2c|rk860|timeout|voltage|Hard LOCKUP'
find /sys/devices/system/cpu/cpufreq -maxdepth 1 -name 'policy*' -print

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    echo "=== $p ==="
    cat "$p/affected_cpus" "$p/scaling_available_frequencies" \
        "$p/scaling_cur_freq"
done
```

验收重点不是只进一次 login：连续冷启动、热重启及 GNOME 登录后运行期间，都不应再出现
`fd880000.i2c` timeout、`Failed to set regulator voltages`、CPUFreq `-110` 或 hard lock。

