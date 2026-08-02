# 53 RK3588 hard lockup：ramoops + buddy detector + hardware watchdog (2026-08-02)

接 [51](51-2026-08-01-rk3588-ttyfiq-rk860x-i2c-hang-fix.md) 和
[52](52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md)。当前随机挂死不是普通的
systemd/login/TTY 阻塞：挂死时在 `ttyFIQ0` 输入 debugger 触发串也没有任何响应。

## `fiq` 无响应的含义

当前实现按 TOPEET vendor 方式运行在普通 IRQ 模式，内核命令行保留
`irqchip.gicv3_pseudo_nmi=0`。因此名字虽然是 `ttyFIQ0`，debugger 仍依赖 UART IRQ 和
GIC 分发；挂死时连触发串都收不到，说明故障域至少已经进入以下范围之一：

- 某 CPU 长时间关本地中断；
- GIC/UART IRQ 不再投递；
- 全局互锁、总线或 SoC 级硬锁。

这条证据不能区分三者，也不能把问题单独归因给 cpufreq/RK860X。它只排除了“系统仍可
调度、仅 login 或终端卡住”。在要求保持 vendor ttyFIQ IRQ 行为的前提下，不能为了抓栈
重新打开 pseudo-NMI。

## 本次诊断实现

### 1. vendor 内存窗口上的 ramoops

板级 DTS 使用 reference vendor `rk3588-linux.dtsi` 的同一段保留内存：

```dts
reserved-memory {
	ramoops: ramoops@110000 {
		compatible = "ramoops";
		reg = <0x0 0x00110000 0x0 0x000e0000>;
		record-size = <0x00020000>;
		console-size = <0x00080000>;
	};
};
```

`CONFIG_PSTORE_RAM=y` 和 `CONFIG_PSTORE_CONSOLE=y` 将 panic 记录和滚动 printk 保存在
`0x110000..0x1effff`。该区域能跨 watchdog **暖重启**保留；断电后不能依赖它。

### 2. 不依赖 pseudo-NMI 的锁死检测

arm64 当前配置支持 `CONFIG_HAVE_HARDLOCKUP_DETECTOR_BUDDY`，因此启用：

- soft lockup + interrupt-storm detector；
- buddy hard lockup detector；
- 60 秒 hung-task detector；
- workqueue stall watchdog；
- 上述条件触发 panic，10 秒后自动重启；
- panic-on-oops 和 panic-on-RCU-stall。

buddy detector 可由仍在运行的 CPU 检出另一颗 CPU 的硬锁；若所有 CPU、GIC 或整个 SoC
同时停摆，它无法获得执行机会。这是机制边界，不能把“没有 detector 栈”误写成没有挂死。

### 3. 独立 DesignWare watchdog

Ubuntu rootfs 固化：

```ini
[Manager]
RuntimeWatchdogSec=30s
```

systemd 打开 RK3588 `feaf0000` DesignWare watchdog 并持续喂狗。全局停摆时预期在约 30 秒
后暖重启，从 ramoops 读取冻结前最后一段 console；如果 detector 已先触发 panic，则由
`kernel.panic=10` 更早重启。

## 与 GT911 修复合并的候选镜像

该镜像同时包含 [52](52-2026-08-02-rk3588-gt911-vendor-polling-i2c-v5.md) 最终的最小
DT 修复：GPIO3_C0 `pcfg_pull_up` + `IRQ_TYPE_EDGE_FALLING`。没有启用已否决的 Goodix
轮询，也没有重新加入全局 I²C v5 改写。

构建闸门：

- 完整 `Image`/DTB 全量编译通过；
- 干净 v7.1 顺序重放 board patch 后源码一致；
- 反编译 DTB 确认 ramoops 窗口和 GT911 pull-up/falling-edge；
- Ubuntu staged rootfs 重新生成，并强制重建 `rootfs.ext4`；
- 修正 forge `pack-emmc` 指纹：显式依赖 `stage-rootfs.fingerprint`，避免 `/etc/*.conf`
  改动被目录扩展名过滤器漏掉；
- RKAF+RKFW assemble round-trip 通过；
- Linux 与 Windows 目标镜像哈希一致。

```text
size:    3290329674 bytes
SHA-256: 5f479634d378d400705660347f0ae5122b7260536c8d98a3886ab4e895fd7ef2
path:    C:\Users\CharlieChen\Assets\images\RK3588\update.img
```

这是“触摸 IRQ 修复 + 锁死取证”候选，不是已证明稳定的镜像。

## 上板验证与取证

正常启动后先确认机制真的工作：

```sh
dmesg | grep -iE 'ramoops|pstore|watchdog|soft lockup|hard lockup'
zgrep -E 'PSTORE_RAM|PSTORE_CONSOLE|HARDLOCKUP_DETECTOR_BUDDY|SOFTLOCKUP|HUNG_TASK|WQ_WATCHDOG|PANIC_TIMEOUT' /proc/config.gz
systemctl show -p RuntimeWatchdogUSec
ls -l /dev/watchdog*
sysctl kernel.panic kernel.softlockup_panic kernel.hardlockup_panic \
       kernel.hung_task_panic kernel.panic_on_rcu_stall kernel.watchdog_thresh
```

再次挂死时不要断电；等 30–45 秒看它是否自动暖重启。重启后第一时间执行：

```sh
find /sys/fs/pstore /var/lib/systemd/pstore -maxdepth 2 -type f -print 2>/dev/null
for f in /sys/fs/pstore/* /var/lib/systemd/pstore/*; do
	[ -f "$f" ] && { echo "===== $f ====="; cat "$f"; }
done
journalctl -b -1 -k --no-pager | tail -n 300
```

若 45 秒后仍不重启，说明硬件 watchdog 也没有在该冻结状态下复位系统；优先按 reset 做暖
复位，再读取 pstore，不要先拔电。若自动重启但 pstore 只有最后 printk、没有栈，说明冻结
覆盖了所有能运行 detector 的 CPU/IRQ 路径；该结果本身也是对故障域的进一步约束。
